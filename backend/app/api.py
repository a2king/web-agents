from __future__ import annotations

import json
from pathlib import Path

from flask import Blueprint, Response, current_app, request, send_file
from flask_jwt_extended import create_access_token
from croniter import croniter

from . import filesvc, jobs, quota, risk
from .agent import extract_skill_zip, tenant_mcps
from .extensions import db
from .ldap_client import LdapAuthError, authenticate_ldap
from .models import (
    Automation,
    AutomationRun,
    Message,
    McpServer,
    ModelConfig,
    Session,
    SessionEvent,
    Skill,
    Tenant,
    TenantMcp,
    User,
)
from .utils import admin_required, fail, hash_password, login_required, ok, slugify, verify_password, week_start

bp = Blueprint("api", __name__, url_prefix="/api")


def _quota_fields(data: dict, tenant: Tenant | None = None) -> dict:
    src = tenant
    return {
        "cpu_limit": float(data.get("cpu_limit", src.cpu_limit if src else 1)),
        "memory_mb": int(data.get("memory_mb", src.memory_mb if src else 1024)),
        "disk_mb": int(data.get("disk_mb", src.disk_mb if src else 10240)),
        "max_file_mb": int(data.get("max_file_mb", src.max_file_mb if src else 200)),
        "weekly_token_quota": int(data.get("weekly_token_quota", src.weekly_token_quota if src else 200000)),
        "max_parallel_sessions": int(data.get("max_parallel_sessions", src.max_parallel_sessions if src else 2)),
        "max_parallel_automations": int(
            data.get("max_parallel_automations", src.max_parallel_automations if src else 1)
        ),
    }


@bp.post("/auth/login")
def login():
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    method = data.get("method") or "local"
    if not username or not password:
        return fail("请输入用户名和密码")

    if method == "ldap":
        try:
            authenticate_ldap(current_app, username, password)
        except LdapAuthError as exc:
            return fail(str(exc), 401)
        user = User.query.filter((User.ldap_uid == username) | (User.username == username)).first()
        if not user:
            return fail("LDAP 认证成功，但尚未开通租户，请联系管理员", 403)
    else:
        user = User.query.filter_by(username=username).first()
        if not user or not verify_password(password, user.password_hash):
            return fail("用户名或密码错误", 401)

    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    return ok({"token": token, "user": user.to_dict()})


@bp.get("/me")
@login_required
def me(user: User):
    tenant = user.tenant
    used = filesvc.dir_size_bytes(current_app.runtime.ensure_workspace(tenant.id))
    return ok(
        {
            "user": user.to_dict(),
            "usage": quota.usage_payload(tenant, user.id),
            "disk_used_mb": round(used / 1024 / 1024, 2),
        }
    )


@bp.get("/models")
@login_required
def list_models(user: User):
    rows = ModelConfig.query.filter_by(enabled=True).all()
    return ok([r.to_dict() for r in rows])


@bp.get("/mcps")
@login_required
def list_my_mcps(user: User):
    return ok([s.to_dict() for s in tenant_mcps(user.tenant_id)])


@bp.get("/usage")
@login_required
def my_usage(user: User):
    return ok(quota.usage_payload(user.tenant, user.id))


@bp.get("/sessions")
@login_required
def list_sessions(user: User):
    rows = (
        Session.query.filter_by(tenant_id=user.tenant_id, user_id=user.id, kind="chat")
        .order_by(Session.updated_at.desc())
        .all()
    )
    return ok([r.to_dict() for r in rows])


@bp.post("/sessions")
@login_required
def create_session(user: User):
    data = request.get_json(force=True, silent=True) or {}
    model_id = data.get("model_id")
    model = db.session.get(ModelConfig, model_id) if model_id else ModelConfig.query.filter_by(enabled=True).first()
    if not model:
        return fail("请先让管理员配置模型")
    session = Session(
        tenant_id=user.tenant_id,
        user_id=user.id,
        title=data.get("title") or "新会话",
        model_id=model.id,
        status="idle",
        kind="chat",
    )
    db.session.add(session)
    db.session.commit()
    current_app.runtime.session_dir(user.tenant_id, session.id)
    return ok(session.to_dict())


@bp.get("/sessions/<int:session_id>")
@login_required
def get_session(user: User, session_id: int):
    session = _owned_session(user, session_id)
    if not session:
        return fail("会话不存在", 404)
    messages = Message.query.filter_by(session_id=session.id).order_by(Message.id.asc()).all()
    events = SessionEvent.query.filter_by(session_id=session.id).order_by(SessionEvent.id.asc()).all()
    return ok(
        {
            "session": session.to_dict(),
            "messages": [m.to_dict() for m in messages],
            "events": [e.to_dict() for e in events],
        }
    )


@bp.post("/sessions/<int:session_id>/messages")
@login_required
def send_message(user: User, session_id: int):
    session = _owned_session(user, session_id)
    if not session:
        return fail("会话不存在", 404)
    if session.status in {"running", "awaiting_confirm"}:
        return fail("会话运行中，仅支持旁观或取消", 409)
    data = request.get_json(force=True, silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return fail("请输入任务内容")
    if data.get("model_id"):
        session.model_id = int(data["model_id"])
    if session.title == "新会话":
        session.title = content[:40]
    db.session.add(Message(session_id=session.id, role="user", content=content))
    tenant = user.tenant
    if quota.tokens_over_quota(tenant):
        session.status = "queued"
        session.queue_reason = "token_quota"
        db.session.commit()
        current_app.events.emit(session.id, "queued", {"reason": "token_quota"})
        return ok(session.to_dict(), queued=True, message="Token 已超额，已进入排队，请联系管理员分配额度")
    ok_run, reason = quota.can_start_session(tenant)
    if not ok_run:
        session.status = "queued"
        session.queue_reason = "parallel"
        db.session.commit()
        return ok(session.to_dict(), queued=True, message=reason)
    session.status = "running"
    db.session.commit()
    jobs.enqueue(current_app._get_current_object(), jobs.process_session, session.id, content, False)
    return ok(session.to_dict())


@bp.post("/sessions/<int:session_id>/cancel")
@login_required
def cancel_session(user: User, session_id: int):
    session = _owned_session(user, session_id)
    if not session:
        return fail("会话不存在", 404)
    current_app.cancel_flags[session.id] = True
    session.status = "cancelled"
    db.session.commit()
    current_app.events.emit(session.id, "status", {"status": "cancelled"})
    return ok(session.to_dict())


@bp.post("/sessions/<int:session_id>/confirm")
@login_required
def confirm_session(user: User, session_id: int):
    session = _owned_session(user, session_id)
    if not session:
        return fail("会话不存在", 404)
    data = request.get_json(force=True, silent=True) or {}
    decision = data.get("decision")
    if decision not in {"once", "session", "account", "reject"}:
        return fail("无效的确认选项")
    if decision == "reject":
        session.status = "idle"
        session.error_message = "用户拒绝了高风险操作"
        db.session.commit()
        current_app.events.emit(session.id, "status", {"status": "idle", "rejected": True})
        return ok(session.to_dict())
    risk.add_grant(user.id, session.id, decision)
    last_user = (
        Message.query.filter_by(session_id=session.id, role="user").order_by(Message.id.desc()).first()
    )
    session.status = "running"
    db.session.commit()
    jobs.enqueue(
        current_app._get_current_object(),
        jobs.process_session,
        session.id,
        last_user.content if last_user else "",
        True,
    )
    return ok(session.to_dict())


@bp.delete("/sessions/<int:session_id>")
@login_required
def delete_session(user: User, session_id: int):
    session = _owned_session(user, session_id)
    if not session:
        return fail("会话不存在", 404)
    if session.status == "running":
        return fail("请先取消运行中的会话")
    root = current_app.runtime.ensure_workspace(user.tenant_id)
    try:
        filesvc.remove_path(root, f"sessions/{session.id}")
    except filesvc.PathEscapeError:
        pass
    Message.query.filter_by(session_id=session.id).delete()
    SessionEvent.query.filter_by(session_id=session.id).delete()
    db.session.delete(session)
    db.session.commit()
    return ok(True)


@bp.get("/sessions/<int:session_id>/stream")
@login_required
def stream_session(user: User, session_id: int):
    session = _owned_session(user, session_id)
    if not session:
        return fail("会话不存在", 404)
    after = int(request.args.get("after", 0))
    bus = current_app.bus

    def generate():
        last = after
        idle_rounds = 0
        while idle_rounds < 120:
            events = bus.listen(f"session:{session_id}", after_id=last, timeout=15)
            if not events:
                yield "event: ping\ndata: {}\n\n"
                idle_rounds += 1
                continue
            idle_rounds = 0
            for event in events:
                last = int(event.get("seq") or event.get("id") or last)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if any(
                e.get("event_type") == "status"
                and (e.get("payload") or {}).get("status") in {"idle", "cancelled", "failed"}
                for e in events
            ):
                break

    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@bp.get("/files")
@login_required
def list_files(user: User):
    rel = request.args.get("path") or ""
    root = current_app.runtime.ensure_workspace(user.tenant_id)
    try:
        items = filesvc.list_dir(root, rel)
    except filesvc.PathEscapeError:
        return fail("非法路径", 400)
    used = filesvc.dir_size_bytes(root)
    return ok(
        {
            "path": rel,
            "items": items,
            "disk_used_mb": round(used / 1024 / 1024, 2),
            "disk_mb": user.tenant.disk_mb,
            "max_file_mb": user.tenant.max_file_mb,
        }
    )


@bp.post("/files/mkdir")
@login_required
def mkdir(user: User):
    data = request.get_json(force=True, silent=True) or {}
    root = current_app.runtime.ensure_workspace(user.tenant_id)
    try:
        filesvc.ensure_dir(root, data.get("path") or "shared")
    except filesvc.PathEscapeError:
        return fail("非法路径")
    return ok(True)


@bp.post("/files/upload")
@login_required
def upload_file(user: User):
    rel = request.form.get("path") or "shared"
    file = request.files.get("file")
    if not file:
        return fail("请选择文件")
    tenant = user.tenant
    root = current_app.runtime.ensure_workspace(user.tenant_id)
    used = filesvc.dir_size_bytes(root)
    max_file = tenant.max_file_mb * 1024 * 1024
    if used + max_file > tenant.disk_mb * 1024 * 1024:
        # still allow if remaining space exists; check after write
        pass
    try:
        dest = filesvc.save_upload(root, rel, file.filename, file.stream, max_file)
    except (ValueError, filesvc.PathEscapeError) as exc:
        return fail(str(exc))
    used = filesvc.dir_size_bytes(root)
    if used > tenant.disk_mb * 1024 * 1024:
        dest.unlink(missing_ok=True)
        return fail("磁盘配额不足")
    return ok({"path": str(dest.relative_to(root)).replace("\\", "/")})


@bp.get("/files/download")
@login_required
def download_file(user: User):
    rel = request.args.get("path") or ""
    root = current_app.runtime.ensure_workspace(user.tenant_id)
    try:
        path = filesvc.safe_join(root, rel)
    except filesvc.PathEscapeError:
        return fail("非法路径")
    if not path.exists() or not path.is_file():
        return fail("文件不存在", 404)
    return send_file(path, as_attachment=True, download_name=path.name)


@bp.delete("/files")
@login_required
def delete_file(user: User):
    data = request.get_json(force=True, silent=True) or {}
    rel = data.get("path") or ""
    if not rel or rel in {"sessions", "shared", "skills"}:
        return fail("不能删除根目录")
    root = current_app.runtime.ensure_workspace(user.tenant_id)
    try:
        filesvc.remove_path(root, rel)
    except filesvc.PathEscapeError:
        return fail("非法路径")
    return ok(True)


@bp.get("/skills")
@login_required
def list_skills(user: User):
    rows = Skill.query.filter_by(tenant_id=user.tenant_id, user_id=user.id).order_by(Skill.id.desc()).all()
    return ok([r.to_dict() for r in rows])


@bp.post("/skills")
@login_required
def upload_skill(user: User):
    file = request.files.get("file")
    name = (request.form.get("name") or (file.filename if file else "") or "skill").rsplit(".", 1)[0]
    slug = slugify(request.form.get("slug") or name)
    if not file:
        return fail("请上传 zip 包")
    if not file.filename.lower().endswith(".zip"):
        return fail("仅支持 zip")
    exists = Skill.query.filter_by(tenant_id=user.tenant_id, slug=slug).first()
    runtime = current_app.runtime
    tmp = Path(current_app.config["DATA_DIR"]) / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    zip_path = tmp / f"{user.tenant_id}-{slug}.zip"
    file.save(zip_path)
    desc = extract_skill_zip(runtime, user.tenant_id, slug, zip_path)
    if exists:
        exists.name = name
        exists.description = desc
        skill = exists
    else:
        skill = Skill(
            tenant_id=user.tenant_id,
            user_id=user.id,
            name=name,
            slug=slug,
            description=desc,
        )
        db.session.add(skill)
    db.session.commit()
    return ok(skill.to_dict())


@bp.delete("/skills/<int:skill_id>")
@login_required
def delete_skill(user: User, skill_id: int):
    skill = Skill.query.filter_by(id=skill_id, tenant_id=user.tenant_id, user_id=user.id).first()
    if not skill:
        return fail("Skill 不存在", 404)
    root = current_app.runtime.ensure_workspace(user.tenant_id)
    try:
        filesvc.remove_path(root, f"skills/{skill.slug}")
    except filesvc.PathEscapeError:
        pass
    db.session.delete(skill)
    db.session.commit()
    return ok(True)


@bp.get("/automations")
@login_required
def list_automations(user: User):
    rows = Automation.query.filter_by(tenant_id=user.tenant_id, user_id=user.id).order_by(Automation.id.desc()).all()
    return ok([r.to_dict() for r in rows])


@bp.post("/automations")
@login_required
def create_automation(user: User):
    data = request.get_json(force=True, silent=True) or {}
    expr = data.get("cron_expr") or ""
    if not croniter.is_valid(expr):
        return fail("Cron 表达式无效")
    auto = Automation(
        tenant_id=user.tenant_id,
        user_id=user.id,
        name=data.get("name") or "自动化任务",
        cron_expr=expr,
        prompt=data.get("prompt") or "",
        skill_slug=data.get("skill_slug"),
        model_id=data.get("model_id"),
        enabled=bool(data.get("enabled", True)),
        next_run_at=jobs.next_cron(expr),
    )
    db.session.add(auto)
    db.session.commit()
    return ok(auto.to_dict())


@bp.put("/automations/<int:auto_id>")
@login_required
def update_automation(user: User, auto_id: int):
    auto = Automation.query.filter_by(id=auto_id, tenant_id=user.tenant_id).first()
    if not auto:
        return fail("任务不存在", 404)
    data = request.get_json(force=True, silent=True) or {}
    if "cron_expr" in data:
        if not croniter.is_valid(data["cron_expr"]):
            return fail("Cron 表达式无效")
        auto.cron_expr = data["cron_expr"]
        auto.next_run_at = jobs.next_cron(auto.cron_expr)
    for field in ("name", "prompt", "skill_slug", "model_id", "enabled"):
        if field in data:
            setattr(auto, field, data[field])
    db.session.commit()
    return ok(auto.to_dict())


@bp.delete("/automations/<int:auto_id>")
@login_required
def delete_automation(user: User, auto_id: int):
    auto = Automation.query.filter_by(id=auto_id, tenant_id=user.tenant_id).first()
    if not auto:
        return fail("任务不存在", 404)
    AutomationRun.query.filter_by(automation_id=auto.id).delete()
    db.session.delete(auto)
    db.session.commit()
    return ok(True)


@bp.get("/automations/<int:auto_id>/runs")
@login_required
def automation_runs(user: User, auto_id: int):
    auto = Automation.query.filter_by(id=auto_id, tenant_id=user.tenant_id).first()
    if not auto:
        return fail("任务不存在", 404)
    rows = AutomationRun.query.filter_by(automation_id=auto.id).order_by(AutomationRun.id.desc()).limit(100).all()
    return ok([r.to_dict() for r in rows])


@bp.get("/admin/tenants")
@admin_required
def admin_tenants(user: User):
    rows = Tenant.query.order_by(Tenant.id.desc()).all()
    data = []
    for tenant in rows:
        owner = User.query.filter_by(tenant_id=tenant.id).first()
        item = tenant.to_dict()
        item["owner"] = owner.to_dict() if owner else None
        item["usage"] = quota.usage_payload(tenant)
        data.append(item)
    return ok(data)


@bp.post("/admin/tenants")
@admin_required
def admin_create_tenant(user: User):
    data = request.get_json(force=True, silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return fail("请填写用户名和初始密码")
    if User.query.filter_by(username=username).first():
        return fail("用户名已存在")
    tenant = Tenant(name=data.get("name") or f"{username}-space", **_quota_fields(data))
    db.session.add(tenant)
    db.session.flush()
    new_user = User(
        username=username,
        password_hash=hash_password(password),
        display_name=data.get("display_name") or username,
        role=data.get("role") or "user",
        ldap_uid=data.get("ldap_uid") or username,
        tenant_id=tenant.id,
    )
    db.session.add(new_user)
    db.session.commit()
    current_app.runtime.ensure_workspace(tenant.id)
    return ok({"tenant": tenant.to_dict(), "user": new_user.to_dict()})


@bp.put("/admin/tenants/<int:tenant_id>")
@admin_required
def admin_update_tenant(user: User, tenant_id: int):
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        return fail("租户不存在", 404)
    data = request.get_json(force=True, silent=True) or {}
    if "name" in data:
        tenant.name = data["name"]
    if "status" in data:
        tenant.status = data["status"]
    for key, value in _quota_fields(data, tenant).items():
        setattr(tenant, key, value)
    db.session.commit()
    if not quota.tokens_over_quota(tenant):
        jobs.enqueue(current_app._get_current_object(), jobs.drain_token_queue)
    return ok(tenant.to_dict())


@bp.delete("/admin/tenants/<int:tenant_id>")
@admin_required
def admin_delete_tenant(user: User, tenant_id: int):
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant:
        return fail("租户不存在", 404)
    if tenant.id == user.tenant_id:
        return fail("不能删除自己的租户")
    current_app.runtime.destroy_workspace(tenant.id)
    for model in (
        AutomationRun,
        Automation,
        SessionEvent,
        Message,
        Session,
        Skill,
        TenantMcp,
    ):
        if hasattr(model, "tenant_id"):
            model.query.filter_by(tenant_id=tenant.id).delete()
    User.query.filter_by(tenant_id=tenant.id).delete()
    db.session.delete(tenant)
    db.session.commit()
    return ok(True)


@bp.get("/admin/models")
@admin_required
def admin_models(user: User):
    return ok([r.to_dict() for r in ModelConfig.query.order_by(ModelConfig.id.desc()).all()])


@bp.post("/admin/models")
@admin_required
def admin_create_model(user: User):
    data = request.get_json(force=True, silent=True) or {}
    row = ModelConfig(
        name=data.get("name") or data.get("model_id"),
        model_id=data.get("model_id") or "",
        base_url=data.get("base_url") or "",
        api_key=data.get("api_key") or "",
        enabled=bool(data.get("enabled", True)),
    )
    if not row.model_id or not row.base_url:
        return fail("请填写模型 ID 和中转站 base_url")
    db.session.add(row)
    db.session.commit()
    return ok(row.to_dict())


@bp.put("/admin/models/<int:model_id>")
@admin_required
def admin_update_model(user: User, model_id: int):
    row = db.session.get(ModelConfig, model_id)
    if not row:
        return fail("模型不存在", 404)
    data = request.get_json(force=True, silent=True) or {}
    for field in ("name", "model_id", "base_url", "enabled"):
        if field in data:
            setattr(row, field, data[field])
    if data.get("api_key"):
        row.api_key = data["api_key"]
    db.session.commit()
    return ok(row.to_dict())


@bp.delete("/admin/models/<int:model_id>")
@admin_required
def admin_delete_model(user: User, model_id: int):
    row = db.session.get(ModelConfig, model_id)
    if not row:
        return fail("模型不存在", 404)
    db.session.delete(row)
    db.session.commit()
    return ok(True)


@bp.get("/admin/mcps")
@admin_required
def admin_mcps(user: User):
    rows = McpServer.query.order_by(McpServer.id.desc()).all()
    assigned = TenantMcp.query.all()
    data = []
    for row in rows:
        item = row.to_dict()
        item["tenant_ids"] = [a.tenant_id for a in assigned if a.mcp_id == row.id and a.enabled]
        data.append(item)
    return ok(data)


@bp.post("/admin/mcps")
@admin_required
def admin_create_mcp(user: User):
    data = request.get_json(force=True, silent=True) or {}
    row = McpServer(
        name=data.get("name") or "mcp",
        transport=data.get("transport") or "sse",
        url=data.get("url"),
        command=data.get("command"),
        headers_json=json.dumps(data.get("headers") or {}, ensure_ascii=False)
        if isinstance(data.get("headers"), dict)
        else data.get("headers_json"),
        enabled=bool(data.get("enabled", True)),
    )
    db.session.add(row)
    db.session.commit()
    return ok(row.to_dict())


@bp.put("/admin/mcps/<int:mcp_id>")
@admin_required
def admin_update_mcp(user: User, mcp_id: int):
    row = db.session.get(McpServer, mcp_id)
    if not row:
        return fail("MCP 不存在", 404)
    data = request.get_json(force=True, silent=True) or {}
    for field in ("name", "transport", "url", "command", "enabled"):
        if field in data:
            setattr(row, field, data[field])
    if "headers" in data:
        row.headers_json = json.dumps(data["headers"], ensure_ascii=False)
    if "headers_json" in data:
        row.headers_json = data["headers_json"]
    db.session.commit()
    return ok(row.to_dict())


@bp.put("/admin/mcps/<int:mcp_id>/tenants")
@admin_required
def admin_assign_mcp(user: User, mcp_id: int):
    row = db.session.get(McpServer, mcp_id)
    if not row:
        return fail("MCP 不存在", 404)
    data = request.get_json(force=True, silent=True) or {}
    tenant_ids = set(int(i) for i in data.get("tenant_ids") or [])
    TenantMcp.query.filter_by(mcp_id=mcp_id).delete()
    for tid in tenant_ids:
        db.session.add(TenantMcp(tenant_id=tid, mcp_id=mcp_id, enabled=True))
    db.session.commit()
    return ok(True)


@bp.delete("/admin/mcps/<int:mcp_id>")
@admin_required
def admin_delete_mcp(user: User, mcp_id: int):
    row = db.session.get(McpServer, mcp_id)
    if not row:
        return fail("MCP 不存在", 404)
    TenantMcp.query.filter_by(mcp_id=mcp_id).delete()
    db.session.delete(row)
    db.session.commit()
    return ok(True)


@bp.get("/admin/queue")
@admin_required
def admin_queue(user: User):
    rows = Session.query.filter_by(status="queued").order_by(Session.updated_at.desc()).all()
    auto_rows = AutomationRun.query.filter_by(status="queued").order_by(AutomationRun.id.desc()).all()
    return ok(
        {
            "sessions": [r.to_dict() for r in rows],
            "automations": [r.to_dict() for r in auto_rows],
            "week_start": week_start().isoformat(),
        }
    )


def _owned_session(user: User, session_id: int) -> Session | None:
    session = db.session.get(Session, session_id)
    if not session or session.tenant_id != user.tenant_id:
        return None
    if user.role != "admin" and session.user_id != user.id:
        return None
    return session
