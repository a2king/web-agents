from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from . import filesvc, quota, risk
from .extensions import db
from .models import McpServer, Message, Session, Skill, TenantMcp


SKILL_PREFIX = re.compile(r"^/([A-Za-z0-9_\-\u4e00-\u9fff]+)\b")


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: int
    tenant_id: int
    user_id: int
    workdir: str
    pending_confirm: dict | None
    cancelled: bool
    tokens: int


def parse_skill_slug(text: str) -> str | None:
    match = SKILL_PREFIX.match(text.strip())
    return match.group(1) if match else None


def load_skill_context(runtime, tenant_id: int, slug: str) -> str:
    skill = Skill.query.filter_by(tenant_id=tenant_id, slug=slug).first()
    if not skill:
        return f"未找到 skill `/{slug}`。"
    skill_dir = runtime.skills_dir(tenant_id) / slug
    if not skill_dir.exists():
        return f"Skill `/{slug}` 文件不存在。"
    parts = [f"已启用 Skill `/{slug}`（{skill.name}）。"]
    if skill.description:
        parts.append(skill.description)
    for md in sorted(skill_dir.rglob("*.md")):
        try:
            parts.append(f"\n# {md.name}\n{md.read_text(encoding='utf-8', errors='ignore')}")
        except OSError:
            continue
    scripts = [p.name for p in skill_dir.rglob("*") if p.suffix in {".py", ".sh"}]
    if scripts:
        parts.append("可执行脚本: " + ", ".join(scripts))
    return "\n".join(parts)


def extract_skill_zip(runtime, tenant_id: int, slug: str, zip_path: Path) -> str:
    dest = runtime.skills_dir(tenant_id) / slug
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    description = ""
    for md in dest.rglob("*.md"):
        description = md.read_text(encoding="utf-8", errors="ignore")[:2000]
        break
    return description


def tenant_mcps(tenant_id: int) -> list[McpServer]:
    rows = (
        db.session.query(McpServer)
        .join(TenantMcp, TenantMcp.mcp_id == McpServer.id)
        .filter(TenantMcp.tenant_id == tenant_id, TenantMcp.enabled.is_(True), McpServer.enabled.is_(True))
        .all()
    )
    return rows


def call_mcp(server: McpServer, tool_name: str, arguments: dict) -> str:
    if server.transport not in {"sse", "streamable_http", "http"}:
        return f"暂不支持的 MCP 传输类型: {server.transport}"
    if not server.url:
        return "MCP 未配置 URL"
    try:
        import httpx

        headers = json.loads(server.headers_json or "{}")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        resp = httpx.post(server.url, json=payload, headers=headers, timeout=30)
        return resp.text[:8000]
    except Exception as exc:  # noqa: BLE001
        return f"MCP 调用失败: {exc}"


def build_tools(app, session: Session, workdir: Path, emit, cancel_flag):
    runtime = app.runtime
    tenant_id = session.tenant_id
    user_id = session.user_id
    root = runtime.ensure_workspace(tenant_id)

    @tool
    def list_files(path: str = ".") -> str:
        """列出当前工作目录或租户空间中的文件。path 相对会话目录或以 sessions/、shared/ 开头。"""
        target = _resolve(path)
        items = filesvc.list_dir(root, str(target.relative_to(root)) if target != root else "")
        return json.dumps(items, ensure_ascii=False)

    @tool
    def read_file(path: str) -> str:
        """读取文本文件内容。"""
        target = _resolve(path)
        if not target.exists() or not target.is_file():
            return "文件不存在"
        data = target.read_text(encoding="utf-8", errors="ignore")
        return data[:20000]

    @tool
    def write_file(path: str, content: str) -> str:
        """写入文本文件，自动创建目录。"""
        target = _resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        emit("tool", {"name": "write_file", "path": path})
        return f"已写入 {path}"

    @tool
    def run_shell(command: str) -> str:
        """在租户工作目录执行 shell 命令。高风险删除操作需要用户确认。"""
        if cancel_flag["cancelled"]:
            return "任务已取消"
        if risk.is_destructive_delete(command=command) and not risk.has_grant(user_id, session.id):
            cancel_flag["pending_confirm"] = {
                "action_type": "destructive_delete",
                "command": command,
                "reason": "检测到破坏性删除命令",
            }
            return "__NEED_CONFIRM__"
        code, out, err = runtime.run_command(tenant_id, command, workdir)
        emit("tool", {"name": "run_shell", "command": command, "code": code})
        return f"exit={code}\nstdout:\n{out[-6000:]}\nstderr:\n{err[-2000:]}"

    @tool
    def run_python(code: str) -> str:
        """在工作目录执行一段 Python 代码。"""
        if cancel_flag["cancelled"]:
            return "任务已取消"
        if risk.is_destructive_delete(command=code) and not risk.has_grant(user_id, session.id):
            cancel_flag["pending_confirm"] = {
                "action_type": "destructive_delete",
                "command": code,
                "reason": "Python 代码包含破坏性删除",
            }
            return "__NEED_CONFIRM__"
        script = workdir / ".agent_tmp.py"
        script.write_text(code, encoding="utf-8")
        rc, out, err = runtime.run_command(tenant_id, "python3 .agent_tmp.py", workdir)
        emit("tool", {"name": "run_python", "code": rc})
        return f"exit={rc}\nstdout:\n{out[-6000:]}\nstderr:\n{err[-2000:]}"

    @tool
    def delete_path(path: str, recursive: bool = False) -> str:
        """删除文件或目录。删除目录属于高风险操作，默认需要确认。"""
        target = _resolve(path)
        rel = str(target.relative_to(root))
        if (recursive or target.is_dir()) and not risk.has_grant(user_id, session.id):
            cancel_flag["pending_confirm"] = {
                "action_type": "destructive_delete",
                "path": rel,
                "reason": "删除目录需要确认",
            }
            return "__NEED_CONFIRM__"
        filesvc.remove_path(root, rel)
        emit("tool", {"name": "delete_path", "path": rel})
        return f"已删除 {rel}"

    @tool
    def call_tenant_mcp(mcp_name: str, tool_name: str, arguments_json: str = "{}") -> str:
        """调用管理员分配给本租户的 MCP 工具。"""
        servers = {s.name: s for s in tenant_mcps(tenant_id)}
        server = servers.get(mcp_name)
        if not server:
            return f"租户未分配 MCP: {mcp_name}，可用: {', '.join(servers) or '无'}"
        try:
            arguments = json.loads(arguments_json or "{}")
        except json.JSONDecodeError:
            arguments = {"raw": arguments_json}
        result = call_mcp(server, tool_name, arguments)
        emit("tool", {"name": "mcp", "mcp": mcp_name, "tool": tool_name})
        return result

    def _resolve(path: str) -> Path:
        raw = (path or ".").lstrip("./")
        if raw.startswith(("sessions/", "shared/", "skills/")):
            return filesvc.safe_join(root, raw)
        return filesvc.safe_join(workdir, raw)

    return [list_files, read_file, write_file, run_shell, run_python, delete_path, call_tenant_mcp]


def _chat_model(model_row):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model_row.model_id,
        api_key=model_row.api_key or "sk-placeholder",
        base_url=model_row.base_url,
        temperature=0.2,
        stream_usage=True,
    )


def build_graph(llm, tools):
    tool_node = ToolNode(tools)
    model = llm.bind_tools(tools)

    def chatbot(state: AgentState):
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: AgentState):
        if state.get("cancelled") or state.get("pending_confirm"):
            return END
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", chatbot)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")
    return graph.compile()


def system_prompt(session: Session, skill_context: str, mcps: list[McpServer]) -> str:
    mcp_names = ", ".join(s.name for s in mcps) or "无"
    return (
        "你是企业内部运维与办公 Agent，运行在租户独立空间中。\n"
        "可以读写文件、执行 Python/Shell、调用已分配的 MCP。\n"
        "工作目录为当前会话目录，公共文件在 shared/。\n"
        f"可用 MCP: {mcp_names}\n"
        "高风险删除目录或 rm -rf 会触发确认，不要绕过。\n"
        "默认自动执行普通操作，简洁汇报结果。\n"
        f"{skill_context}"
    )


def _mock_turn(app, session: Session, user_text: str, workdir, emit, cancel_flag):
    from langchain_core.messages import AIMessage

    if risk.is_destructive_delete(command=user_text):
        raise NeedConfirm({"action_type": "destructive_delete", "command": user_text, "reason": "检测到破坏性删除命令"})
    slug = parse_skill_slug(user_text)
    note = ""
    if slug:
        note = load_skill_context(app.runtime, session.tenant_id, slug)
        emit("skill", {"slug": slug})
    (workdir / "agent_output.txt").write_text(f"任务：{user_text}\n{note}", encoding="utf-8")
    emit("tool", {"name": "write_file", "path": "agent_output.txt"})
    text = f"已在独立租户空间完成任务（本地演示模式）。产物：sessions/{session.id}/agent_output.txt"
    if slug:
        text += f"\n已加载 skill /{slug}"
    return {
        "messages": [
            AIMessage(
                content=text,
                usage_metadata={"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
            )
        ]
    }


class NeedConfirm(Exception):
    def __init__(self, payload: dict):
        super().__init__(payload.get("reason") or "需要确认")
        self.payload = payload


class Cancelled(Exception):
    pass


def run_agent_turn(app, session_id: int, user_text: str, resume: bool = False):
    session = db.session.get(Session, session_id)
    if not session:
        return
    emit = lambda event_type, payload=None: app.events.emit(session_id, event_type, payload or {})
    if app.cancel_flags.get(session_id):
        raise Cancelled()

    model_row = session.model
    if not model_row or not model_row.enabled:
        raise RuntimeError("未配置可用模型")

    workdir = app.runtime.session_dir(session.tenant_id, session.id)
    skill_slug = parse_skill_slug(user_text)
    skill_context = ""
    if skill_slug:
        skill_context = load_skill_context(app.runtime, session.tenant_id, skill_slug)
        emit("skill", {"slug": skill_slug})

    cancel_flag = {"cancelled": False, "pending_confirm": None}
    emit("status", {"status": "running"})

    tokens = 0
    use_mock = (
        os.getenv("MOCK_LLM") == "1"
        or (model_row.base_url or "").startswith("http://localhost")
        or model_row.model_id == "demo"
    )
    try:
        if use_mock:
            result = _mock_turn(app, session, user_text, workdir, emit, cancel_flag)
        else:
            tools = build_tools(app, session, workdir, emit, cancel_flag)
            llm = _chat_model(model_row)
            graph = build_graph(llm, tools)
            history = []
            from .models import Message as MessageModel

            rows = MessageModel.query.filter_by(session_id=session.id).order_by(MessageModel.id.asc()).all()
            for row in rows:
                if row.role == "user":
                    history.append(HumanMessage(content=row.content))
                elif row.role == "assistant":
                    history.append(AIMessage(content=row.content))
                elif row.role == "system":
                    history.append(SystemMessage(content=row.content))
            if not resume:
                history.append(HumanMessage(content=user_text))
            mcps = tenant_mcps(session.tenant_id)
            messages = [SystemMessage(content=system_prompt(session, skill_context, mcps)), *history]
            result = graph.invoke(
                {
                    "messages": messages,
                    "session_id": session.id,
                    "tenant_id": session.tenant_id,
                    "user_id": session.user_id,
                    "workdir": str(workdir),
                    "pending_confirm": None,
                    "cancelled": bool(app.cancel_flags.get(session_id)),
                    "tokens": 0,
                }
            )
    except NeedConfirm:
        raise
    except Exception as exc:  # noqa: BLE001
        emit("error", {"message": str(exc)})
        raise

    if cancel_flag["pending_confirm"]:
        raise NeedConfirm(cancel_flag["pending_confirm"])
    if app.cancel_flags.get(session_id):
        raise Cancelled()

    final_text = ""
    for msg in result.get("messages", []):
        usage = getattr(msg, "usage_metadata", None) or {}
        tokens += int(usage.get("total_tokens") or 0)
        if isinstance(msg, AIMessage) and msg.content:
            final_text = msg.content if isinstance(msg.content, str) else str(msg.content)
            emit("token", {"text": final_text})

    if tokens:
        quota.add_tokens(session.tenant_id, session.user_id, tokens, 0)
        db.session.commit()
        emit("usage", {"total_tokens": tokens})

    if final_text:
        db.session.add(Message(session_id=session.id, role="assistant", content=final_text))
        db.session.commit()
        emit("assistant", {"content": final_text})
    emit("status", {"status": "idle"})
    return final_text
