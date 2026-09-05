import { Button, Card, Input, Modal, Radio, Select, Space, Tag, Typography, message } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";

export default function SessionDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [detail, setDetail] = useState<any>(null);
  const [models, setModels] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [events, setEvents] = useState<any[]>([]);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [decision, setDecision] = useState("once");
  const boxRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    const [d, m] = await Promise.all([api("get", `/sessions/${id}`), api("get", "/models")]);
    setDetail(d.data);
    setModels(m.data);
    setEvents(d.data.events || []);
    if (d.data.session.status === "awaiting_confirm") setConfirmOpen(true);
  };

  useEffect(() => {
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
        /* fallback below */
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
  }, [events]);

  const running = detail?.session?.status === "running" || detail?.session?.status === "awaiting_confirm";
  const log = useMemo(() => {
    return (events || [])
      .map((e: any) => {
        const p = typeof e.payload_json === "string" ? JSON.parse(e.payload_json || "{}") : e.payload || {};
        return `[${e.event_type}] ${p.text || p.content || p.message || p.reason || JSON.stringify(p)}`;
      })
      .join("\n");
  }, [events]);

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

  const cancel = async () => {
    await api("post", `/sessions/${id}/cancel`);
    message.success("已取消");
    load();
  };

  const confirm = async () => {
    await api("post", `/sessions/${id}/confirm`, { decision });
    setConfirmOpen(false);
    load();
  };

  if (!detail) return null;
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
            onChange={async (v) => {
              s.model_id = v;
              setDetail({ ...detail, session: { ...s } });
            }}
          />
          {running && (
            <Button danger onClick={cancel}>
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
      <div className="stream-box" ref={boxRef}>
        {(detail.messages || []).map((m: any) => (
          <div key={`m-${m.id}`} style={{ marginBottom: 8 }}>
            <b>{m.role === "user" ? "用户" : "Agent"}：</b>
            {m.content}
          </div>
        ))}
        <div style={{ opacity: 0.75, marginTop: 12 }}>{log}</div>
      </div>
      <Space.Compact style={{ width: "100%", marginTop: 16 }}>
        <Input.TextArea
          disabled={running}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={running ? "运行中只读旁观" : "输入任务，可用 /report 指定 skill"}
          autoSize={{ minRows: 2, maxRows: 6 }}
        />
      </Space.Compact>
      <Button type="primary" disabled={running} onClick={send} style={{ marginTop: 12 }}>
        提交任务
      </Button>

      <Modal title="高风险操作确认" open={confirmOpen} onOk={confirm} onCancel={() => setConfirmOpen(false)}>
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
