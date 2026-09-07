import io
import json
import zipfile
from pathlib import Path

from app.extensions import db
from app.models import ModelConfig, Session, Tenant, User
from app.risk import is_destructive_delete
from app.utils import week_start
from app import quota


def test_login_and_me(client, admin_headers):
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401
    me = client.get("/api/me", headers=admin_headers)
    assert me.status_code == 200
    body = me.get_json()["data"]
    assert body["user"]["role"] == "admin"
    assert body["user"]["tenant"]["name"] == "admin-space"


def test_ldap_reserved(client, app):
    resp = client.post("/api/auth/login", json={"username": "someone", "password": "x", "method": "ldap"})
    assert resp.status_code == 401
    assert "LDAP" in resp.get_json()["error"]


def test_create_tenant_and_quotas(client, admin_headers, app):
    resp = client.post(
        "/api/admin/tenants",
        headers=admin_headers,
        json={
            "username": "alice",
            "password": "Alice@123",
            "name": "alice-space",
            "cpu_limit": 1.5,
            "memory_mb": 512,
            "disk_mb": 1024,
            "max_file_mb": 10,
            "weekly_token_quota": 1000,
            "max_parallel_sessions": 1,
            "max_parallel_automations": 1,
        },
    )
    assert resp.status_code == 200
    tenant_id = resp.get_json()["data"]["tenant"]["id"]
    login = client.post("/api/auth/login", json={"username": "alice", "password": "Alice@123"})
    token = login.get_json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    usage = client.get("/api/usage", headers=headers).get_json()["data"]
    assert usage["weekly_token_quota"] == 1000
    assert usage["remaining"] == 1000
    root = app.runtime.ensure_workspace(tenant_id)
    assert (root / "shared").exists()
    assert (root / "sessions").exists()


def test_files_isolation_and_quota(client, admin_headers, app):
    client.post(
        "/api/admin/tenants",
        headers=admin_headers,
        json={
            "username": "bob",
            "password": "Bob@123",
            "disk_mb": 1,
            "max_file_mb": 1,
        },
    )
    token = client.post("/api/auth/login", json={"username": "bob", "password": "Bob@123"}).get_json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    up = client.post(
        "/api/files/upload",
        headers=headers,
        data={"path": "shared", "file": (io.BytesIO(b"hello-file"), "a.txt")},
        content_type="multipart/form-data",
    )
    assert up.status_code == 200
    listing = client.get("/api/files?path=shared", headers=headers).get_json()["data"]
    assert any(i["name"] == "a.txt" for i in listing["items"])
    huge = client.post(
        "/api/files/upload",
        headers=headers,
        data={"path": "shared", "file": (io.BytesIO(b"x" * 2 * 1024 * 1024), "big.bin")},
        content_type="multipart/form-data",
    )
    assert huge.status_code == 400


def test_skills_zip_and_slash(client, admin_headers, app):
    token = admin_headers
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SKILL.md", "# report\n生成周报")
        zf.writestr("run.sh", "echo ok")
    buf.seek(0)
    resp = client.post(
        "/api/skills",
        headers=token,
        data={"name": "report", "slug": "report", "file": (buf, "report.zip")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    assert resp.get_json()["data"]["slug"] == "report"
    skills = client.get("/api/skills", headers=token).get_json()["data"]
    assert len(skills) == 1


def test_models_mcp_assign(client, admin_headers):
    model = client.post(
        "/api/admin/models",
        headers=admin_headers,
        json={"name": "demo", "model_id": "gpt-4o-mini", "base_url": "https://gateway.example/v1", "api_key": "sk-test"},
    )
    assert model.status_code == 200
    mcp = client.post(
        "/api/admin/mcps",
        headers=admin_headers,
        json={"name": "知识库", "transport": "sse", "url": "https://mcp.example/sse"},
    )
    mcp_id = mcp.get_json()["data"]["id"]
    tenants = client.get("/api/admin/tenants", headers=admin_headers).get_json()["data"]
    tid = tenants[0]["id"]
    assign = client.put(
        f"/api/admin/mcps/{mcp_id}/tenants",
        headers=admin_headers,
        json={"tenant_ids": [tid]},
    )
    assert assign.status_code == 200
    mine = client.get("/api/mcps", headers=admin_headers).get_json()["data"]
    assert mine[0]["name"] == "知识库"


def test_session_queue_when_over_token(client, admin_headers, app):
    client.post(
        "/api/admin/models",
        headers=admin_headers,
        json={"name": "demo", "model_id": "demo", "base_url": "http://localhost/v1", "api_key": "sk"},
    )
    created = client.post("/api/sessions", headers=admin_headers, json={"title": "t"}).get_json()["data"]
    with app.app_context():
        tenant = db.session.get(Tenant, 1)
        tenant.weekly_token_quota = 10
        quota.add_tokens(tenant.id, 1, 20, 0)
        db.session.commit()
    resp = client.post(
        f"/api/sessions/{created['id']}/messages",
        headers=admin_headers,
        json={"content": "hello"},
    )
    body = resp.get_json()
    assert body["queued"] is True
    assert body["data"]["status"] == "queued"


def test_session_delete_removes_artifacts(client, admin_headers, app):
    client.post(
        "/api/admin/models",
        headers=admin_headers,
        json={"name": "demo", "model_id": "demo", "base_url": "http://localhost/v1", "api_key": "sk"},
    )
    created = client.post("/api/sessions", headers=admin_headers, json={"title": "del-me"}).get_json()["data"]
    sid = created["id"]
    path = app.runtime.session_dir(1, sid) / "out.txt"
    path.write_text("artifact")
    assert path.exists()
    resp = client.delete(f"/api/sessions/{sid}", headers=admin_headers)
    assert resp.status_code == 200
    assert not path.exists()


def test_automation_cron_validation(client, admin_headers):
    bad = client.post(
        "/api/automations",
        headers=admin_headers,
        json={"name": "bad", "cron_expr": "not-a-cron", "prompt": "x"},
    )
    assert bad.status_code == 400
    good = client.post(
        "/api/automations",
        headers=admin_headers,
        json={"name": "weekly", "cron_expr": "0 9 * * 1", "prompt": "/report 生成", "skill_slug": "report"},
    )
    assert good.status_code == 200
    assert good.get_json()["data"]["next_run_at"]


def test_destructive_detect():
    assert is_destructive_delete(command="rm -rf /tmp/foo")
    assert is_destructive_delete(path="shared/old", recursive=True)
    assert not is_destructive_delete(command="ls -la")


def test_session_mock_run_and_confirm(client, admin_headers, app):
    client.post(
        "/api/admin/models",
        headers=admin_headers,
        json={"name": "demo", "model_id": "demo", "base_url": "http://localhost/v1", "api_key": "sk"},
    )
    sid = client.post("/api/sessions", headers=admin_headers, json={"title": "run"}).get_json()["data"]["id"]
    resp = client.post(f"/api/sessions/{sid}/messages", headers=admin_headers, json={"content": "/none 写一份说明"})
    assert resp.status_code == 200
    detail = client.get(f"/api/sessions/{sid}", headers=admin_headers).get_json()["data"]
    assert detail["session"]["status"] in {"idle", "running"}
    assert any(m["role"] == "assistant" for m in detail["messages"])
    out = app.runtime.session_dir(1, sid) / "agent_output.txt"
    assert out.exists()

    sid2 = client.post("/api/sessions", headers=admin_headers, json={"title": "risk"}).get_json()["data"]["id"]
    client.post(f"/api/sessions/{sid2}/messages", headers=admin_headers, json={"content": "rm -rf shared/old"})
    detail2 = client.get(f"/api/sessions/{sid2}", headers=admin_headers).get_json()["data"]
    assert detail2["session"]["status"] == "awaiting_confirm"
    client.post(f"/api/sessions/{sid2}/confirm", headers=admin_headers, json={"decision": "reject"})
    detail3 = client.get(f"/api/sessions/{sid2}", headers=admin_headers).get_json()["data"]
    assert detail3["session"]["status"] == "idle"


def test_week_start_monday():
    from datetime import datetime

    assert week_start(datetime(2026, 9, 5)).isoformat() == "2026-08-31"  # Saturday -> Monday
