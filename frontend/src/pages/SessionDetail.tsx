import { ArrowUpOutlined, StopOutlined } from "@ant-design/icons";
import { Modal, Radio, Select, Space, Spin, Typography, message } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";

function payloadOf(e: any) {
  if (e.payload) return e.payload;
  if (typeof e.payload_json === "string") {
    try {
      return JSON.parse(e.payload_json || "{}");
    } catch {
      return {};
    }
  }
  return {};
}

function eventLine(e: any) {
  const p = payloadOf(e);
  switch (e.event_type) {
    case "status":
      return `状态：${p.status || ""}${p.rejected ? "（已拒绝高风险操作）" : ""}`;
    case "tool":
      return `工具：${p.name || ""}${p.path ? ` ${p.path}` : ""}${p.command ? ` ${p.command}` : ""}`;
    case "skill":
      return `已加载 Skill /${p.slug || ""}`;
    case "usage":
      return `消耗 Token：${p.total_tokens || 0}`;
    case "queued":
      return `已排队：${p.reason === "token_quota" ? "Token 超额，请联系管理员" : p.reason || ""}`;
    case "confirm":
      return `等待确认：${p.reason || "高风险删除"}`;
    case "error":
      return `错误：${p.message || ""}`;
    default:
      return "";
  }
}

export default function SessionDetail() {
  const { id } = useParams();
  const [detail, setDetail] = useState<any>(null);
  const [models, setModels] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [events, setEvents] = useState<any[]>([]);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [decision, setDecision] = useState("once");
  const [loading, setLoading] = useState(true);
  const boxRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    const [d, m] = await Promise.all([api("get", `/sessions/${id}`), api("get", "/models")]);
    setDetail(d.data);
    setModels(m.data);
    setEvents(d.data.events || []);
    if (d.data.session.status === "awaiting_confirm") setConfirmOpen(true);
    setLoading(false);
  };

  useEffect(() => {
    setLoading(true);
    load();
  }, [id]);

  useEffect(() => {
    if (!id) return;
    let stopped = false;
    const token = localStorage.getItem("token");
    const readStream = async () => {
      try {
        const resp = await fetch(`/api/sessions/${id}/stream`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        const reader = resp.body?.getReader();
        if (!reader) return;
        const decoder = new TextDecoder();
        let buf = "";
        while (!stopped) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const chunks = buf.split("\n\n");
          buf = chunks.pop() || "";
          for (const chunk of chunks) {
            const line = chunk.split("\n").find((l) => l.startsWith("data:"));
            if (!line) continue;
            try {
              const event = JSON.parse(line.slice(5).trim());
              setEvents((prev) => [...prev, event]);
              if (event.event_type === "confirm") setConfirmOpen(true);
            } catch {
              /* ignore */
            }
          }
        }
      } catch {
        /* polling */
      }
    };
    readStream();
    const timer = setInterval(() => {
      api("get", `/sessions/${id}`).then((d) => {
        setDetail(d.data);
        if (d.data.session.status === "awaiting_confirm") setConfirmOpen(true);
      });
    }, 2000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [id]);

  useEffect(() => {
    boxRef.current?.scrollTo(0, boxRef.current.scrollHeight);
  }, [detail, events]);

  const running = detail?.session?.status === "running" || detail?.session?.status === "awaiting_confirm";
  const logs = useMemo(() => (events || []).map(eventLine).filter(Boolean), [events]);

  const send = async () => {
    if (!text.trim() || running) return;
    try {
      const resp = await api("post", `/sessions/${id}/messages`, {
        content: text,
        model_id: detail.session.model_id,
      });
      if (resp.queued) message.warning(resp.message);
      setText("");
      load();
    } catch (e: any) {
      message.error(e.response?.data?.error || e.message);
    }
  };

  if (loading || !detail) {
    return (
      <div className="gpt-loading">
        <Spin />
      </div>
    );
  }
  const s = detail.session;
  const messages = detail.messages || [];

  return (
    <div className="gpt-chat">
      <header className="gpt-topbar">
        <Select
          bordered={false}
          value={s.model_id}
          disabled={running}
          options={models.map((m) => ({ value: m.id, label: m.name }))}
          onChange={(v) => setDetail({ ...detail, session: { ...s, model_id: v } })}
        />
        <span className={`gpt-status ${s.border_status}`}>{s.status}</span>
      </header>

      <div className="gpt-thread" ref={boxRef}>
        {messages.length === 0 && (
          <div className="gpt-empty-mini">
            <h2>{s.title === "新对话" ? "有什么可以帮忙的？" : s.title}</h2>
          </div>
        )}
        {messages.map((m: any) => (
          <div key={m.id} className={`gpt-turn ${m.role}`}>
            {m.role !== "user" && <div className="gpt-mini-avatar">A</div>}
            <div className="gpt-bubble">{m.content}</div>
          </div>
        ))}
        {logs.length > 0 && (
          <details className="gpt-logs">
            <summary>运行日志</summary>
            <pre>{logs.join("\n")}</pre>
          </details>
        )}
      </div>

      <div className="gpt-dock">
        <div className="gpt-composer">
          <textarea
            disabled={running}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={running ? "运行中，可旁观或停止" : "询问任何问题，可用 /skill 指定技能"}
            rows={1}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <div className="gpt-composer-bar">
            <span className="gpt-hint">Enter 发送 · Shift+Enter 换行</span>
            {running ? (
              <button
                type="button"
                className="gpt-send ready stop"
                onClick={async () => {
                  await api("post", `/sessions/${id}/cancel`);
                  message.success("已取消");
                  load();
                }}
                aria-label="停止"
              >
                <StopOutlined />
              </button>
            ) : (
              <button
                type="button"
                className={`gpt-send ${text.trim() ? "ready" : ""}`}
                disabled={!text.trim()}
                onClick={send}
                aria-label="发送"
              >
                <ArrowUpOutlined />
              </button>
            )}
          </div>
        </div>
      </div>

      <Modal
        title="高风险操作确认"
        open={confirmOpen}
        onOk={async () => {
          await api("post", `/sessions/${id}/confirm`, { decision });
          setConfirmOpen(false);
          load();
        }}
        onCancel={() => setConfirmOpen(false)}
      >
        <Typography.Paragraph>检测到破坏性删除操作，请选择授权范围：</Typography.Paragraph>
        <Radio.Group value={decision} onChange={(e) => setDecision(e.target.value)}>
          <Space direction="vertical">
            <Radio value="once">仅本次</Radio>
            <Radio value="session">本会话</Radio>
            <Radio value="account">本账号</Radio>
            <Radio value="reject">拒绝</Radio>
          </Space>
        </Radio.Group>
      </Modal>
    </div>
  );
}
