import { PlusOutlined } from "@ant-design/icons";
import { Button, Card, Empty, Modal, Select, Space, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";

const STATUS_LABEL: Record<string, string> = {
  running: "运行中",
  confirm: "待确认",
  queued: "排队中",
  idle: "空闲",
};

export default function Sessions() {
  const [rows, setRows] = useState<any[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [modelId, setModelId] = useState<number>();
  const nav = useNavigate();

  const load = async () => {
    const [s, m] = await Promise.all([api("get", "/sessions"), api("get", "/models")]);
    setRows(s.data);
    setModels(m.data);
    if (!modelId && m.data[0]) setModelId(m.data[0].id);
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const create = async () => {
    const resp = await api("post", "/sessions", { model_id: modelId, title: "新会话" });
    setOpen(false);
    nav(`/sessions/${resp.data.id}`);
  };

  const remove = (row: any) => {
    Modal.confirm({
      title: "删除会话？",
      content: "将同时删除该会话目录下的产物文件，且不可恢复。",
      okType: "danger",
      onOk: async () => {
        await api("delete", `/sessions/${row.id}`);
        message.success("已删除");
        load();
      },
    });
  };

  return (
    <Card
      title="会话"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          新建会话
        </Button>
      }
    >
      {rows.length === 0 ? (
        <Empty description="还没有会话" />
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
          {rows.map((row) => (
            <div
              key={row.id}
              className={`session-card ${row.border_status}`}
              onClick={() => nav(`/sessions/${row.id}`)}
            >
              <Typography.Title level={5} style={{ marginTop: 0 }}>
                {row.title}
              </Typography.Title>
              <Space direction="vertical" size={4}>
                <Typography.Text type="secondary">模型：{row.model_name || "-"}</Typography.Text>
                <Typography.Text>状态：{STATUS_LABEL[row.border_status] || row.status}</Typography.Text>
                {row.queue_reason === "token_quota" && (
                  <Typography.Text type="warning">Token 超额排队，请联系管理员</Typography.Text>
                )}
              </Space>
              <div style={{ marginTop: 12 }}>
                <Button
                  danger
                  size="small"
                  onClick={(e) => {
                    e.stopPropagation();
                    remove(row);
                  }}
                >
                  删除
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
      <Modal title="新建会话" open={open} onOk={create} onCancel={() => setOpen(false)}>
        <Select
          style={{ width: "100%" }}
          placeholder="选择模型"
          value={modelId}
          onChange={setModelId}
          options={models.map((m) => ({ value: m.id, label: m.name }))}
        />
      </Modal>
    </Card>
  );
}
