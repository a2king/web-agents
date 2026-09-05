import { ArrowUpOutlined } from "@ant-design/icons";
import { Select, message } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

export default function ChatHome() {
  const nav = useNavigate();
  const [models, setModels] = useState<any[]>([]);
  const [modelId, setModelId] = useState<number>();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    api("get", "/models").then((r) => {
      setModels(r.data || []);
      if (r.data?.[0]) setModelId(r.data[0].id);
    });
  }, []);

  const send = async () => {
    const content = text.trim();
    if (!content || sending) return;
    if (!modelId) {
      message.warning("请先让管理员配置模型");
      return;
    }
    setSending(true);
    try {
      const created = await api("post", "/sessions", { model_id: modelId, title: content.slice(0, 40) });
      await api("post", `/sessions/${created.data.id}/messages`, { content, model_id: modelId });
      nav(`/sessions/${created.data.id}`);
    } catch (e: any) {
      message.error(e.response?.data?.error || e.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="gpt-empty">
      <div className="gpt-empty-inner">
        <h1>有什么可以帮忙的？</h1>
        <p className="gpt-empty-sub">提交后后台执行，关闭页面也能继续。用 /skill 指定技能。</p>
        <div className="gpt-composer">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="询问任何问题"
            rows={1}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <div className="gpt-composer-bar">
            <Select
              size="small"
              bordered={false}
              value={modelId}
              onChange={setModelId}
              placeholder="模型"
              options={models.map((m) => ({ value: m.id, label: m.name }))}
              style={{ minWidth: 140 }}
            />
            <button
              type="button"
              className={`gpt-send ${text.trim() ? "ready" : ""}`}
              disabled={!text.trim() || sending}
              onClick={send}
              aria-label="发送"
            >
              <ArrowUpOutlined />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
