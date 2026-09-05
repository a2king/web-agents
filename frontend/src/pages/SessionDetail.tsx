import { Button, Card, Input, Modal, Radio, Select, Space, Spin, Tag, Typography, message } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
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
    case "assistant":
    case "token":
      return "";
    default:
      return p.message || p.reason || "";
  }
}

export default function SessionDetail() {
  const { id } = useParams();
  const nav = useNavigate();
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
              /* ignore heartbeat */
            }
          }
        }
      } catch {
        /* polling fallback */
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
    if (!text.trim()) return;
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
      <Card>
        <Spin tip="加载会话..." />
      </Card>
    );
  }
  const s = detail.session;

  return (
    <Card
      title={s.title}
      extra={
        <Space>
          <Tag color={s.border_status === "running" ? "blue" : s.border_status === "confirm" ? "orange" : "default"}>
            {s.status}
          </Tag>
          <Select
            value={s.model_id}
            disabled={running}
            style={{ width: 200 }}
            options={models.map((m) => ({ value: m.id, label: m.name }))}
            onChange={(v) => setDetail({ ...detail, session: { ...s, model_id: v } })}
          />
          {running && (
            <Button
              danger
              onClick={async () => {
                await api("post", `/sessions/${id}/cancel`);
                message.success("已取消");
                load();
              }}
            >
              取消任务
            </Button>
          )}
          <Button onClick={() => nav("/sessions")}>返回列表</Button>
        </Space>
      }
    >
      <Typography.Paragraph type="secondary">
        运行中仅支持旁观。使用 <code>/skill名</code> 指定已上传的 Skill。关闭页面后任务仍在后台执行。
      </Typography.Paragraph>
      <div ref={boxRef} style={{ maxHeight: 420, overflow: "auto", marginBottom: 16 }}>
        {(detail.messages || []).map((m: any) => (
          <div
            key={`m-${m.id}`}
            style={{
              marginBottom: 12,
              padding: "10px 14px",
              borderRadius: 8,
              background: m.role === "user" ? "#e6f4ff" : "#f6ffed",
              whiteSpace: "pre-wrap",
            }}
          >
            <Typography.Text strong>{m.role === "user" ? "你" : "Agent"}</Typography.Text>
            <div>{m.content}</div>
          </div>
        ))}
        {(detail.messages || []).length === 0 && <Typography.Text type="secondary">还没有消息，提交任务后会在此回放。</Typography.Text>}
      </div>
      {logs.length > 0 && (
        <details style={{ marginBottom: 16 }}>
          <summary style={{ cursor: "pointer", color: "#667085" }}>运行日志（可回放）</summary>
          <div className="stream-box" style={{ minHeight: 80, maxHeight: 200, marginTop: 8 }}>
            {logs.join("\n")}
          </div>
        </details>
      )}
      <Input.TextArea
        disabled={running}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={running ? "运行中只读旁观" : "输入任务，可用 /report 指定 skill"}
        autoSize={{ minRows: 2, maxRows: 6 }}
      />
      <Button type="primary" disabled={running} onClick={send} style={{ marginTop: 12 }}>
        提交任务
      </Button>

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
    </Card>
  );
}
