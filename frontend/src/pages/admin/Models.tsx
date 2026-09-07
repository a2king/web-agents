import { Button, Card, Form, Input, Modal, Switch, Table, message } from "antd";
import { useEffect, useState } from "react";
import { api } from "../../api";

export default function Models() {
  const [rows, setRows] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const load = async () => setRows((await api("get", "/admin/models")).data);
  useEffect(() => {
    load();
  }, []);

  return (
    <Card
      title="模型（OpenAI 兼容中转）"
      extra={
        <Button type="primary" onClick={() => setOpen(true)}>
          接入模型
        </Button>
      }
    >
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "显示名", dataIndex: "name" },
          { title: "模型 ID", dataIndex: "model_id" },
          { title: "Base URL", dataIndex: "base_url" },
          { title: "Key", dataIndex: "api_key" },
          {
            title: "启用",
            render: (_, r) => (
              <Switch
                checked={r.enabled}
                onChange={async (v) => {
                  await api("put", `/admin/models/${r.id}`, { enabled: v });
                  load();
                }}
              />
            ),
          },
          {
            title: "操作",
            render: (_, r) => (
              <a
                onClick={async () => {
                  await api("delete", `/admin/models/${r.id}`);
                  load();
                }}
              >
                删除
              </a>
            ),
          },
        ]}
      />
      <Modal
        title="接入模型"
        open={open}
        onOk={async () => {
          await api("post", "/admin/models", await form.validateFields());
          message.success("已保存");
          setOpen(false);
          form.resetFields();
          load();
        }}
        onCancel={() => setOpen(false)}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="显示名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="model_id" label="模型 ID" rules={[{ required: true }]}>
            <Input placeholder="gpt-4o" />
          </Form.Item>
          <Form.Item name="base_url" label="中转站 Base URL" rules={[{ required: true }]}>
            <Input placeholder="https://gateway.company.com/v1" />
          </Form.Item>
          <Form.Item name="api_key" label="API Key">
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
