import { Button, Card, Form, Input, InputNumber, Modal, Table, message } from "antd";
import { useEffect, useState } from "react";
import { api } from "../../api";

export default function Tenants() {
  const [rows, setRows] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<any>(null);
  const [form] = Form.useForm();

  const load = async () => setRows((await api("get", "/admin/tenants")).data);
  useEffect(() => {
    load();
  }, []);

  const submit = async () => {
    const values = await form.validateFields();
    if (editing) {
      await api("put", `/admin/tenants/${editing.id}`, values);
    } else {
      await api("post", "/admin/tenants", values);
    }
    message.success("已保存");
    setOpen(false);
    setEditing(null);
    form.resetFields();
    load();
  };

  return (
    <Card
      title="租户管理"
      extra={
        <Button
          type="primary"
          onClick={() => {
            setEditing(null);
            form.resetFields();
            setOpen(true);
          }}
        >
          开通租户
        </Button>
      }
    >
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "空间", dataIndex: "name" },
          { title: "用户", render: (_, r) => r.owner?.username },
          { title: "CPU", dataIndex: "cpu_limit" },
          { title: "内存MB", dataIndex: "memory_mb" },
          { title: "磁盘MB", dataIndex: "disk_mb" },
          { title: "周Token", dataIndex: "weekly_token_quota" },
          { title: "并行会话", dataIndex: "max_parallel_sessions" },
          { title: "并行自动化", dataIndex: "max_parallel_automations" },
          { title: "已用Token", render: (_, r) => r.usage?.total_tokens },
          {
            title: "操作",
            render: (_, r) => (
              <>
                <a
                  onClick={() => {
                    setEditing(r);
                    form.setFieldsValue({ ...r, username: r.owner?.username });
                    setOpen(true);
                  }}
                >
                  配额
                </a>
                <a
                  style={{ marginLeft: 12 }}
                  onClick={async () => {
                    await api("delete", `/admin/tenants/${r.id}`);
                    load();
                  }}
                >
                  删除
                </a>
              </>
            ),
          },
        ]}
      />
      <Modal title={editing ? "调整配额" : "开通租户"} open={open} onOk={submit} onCancel={() => setOpen(false)} width={640}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            cpu_limit: 1,
            memory_mb: 1024,
            disk_mb: 10240,
            max_file_mb: 200,
            weekly_token_quota: 200000,
            max_parallel_sessions: 2,
            max_parallel_automations: 1,
          }}
        >
          {!editing && (
            <>
              <Form.Item name="username" label="用户名 / LDAP uid" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="password" label="初始本地密码" rules={[{ required: true }]}>
                <Input.Password />
              </Form.Item>
              <Form.Item name="name" label="租户空间名">
                <Input />
              </Form.Item>
            </>
          )}
          <Form.Item name="cpu_limit" label="CPU">
            <InputNumber min={0.1} step={0.5} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="memory_mb" label="内存 MB">
            <InputNumber min={128} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="disk_mb" label="磁盘 MB">
            <InputNumber min={100} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="max_file_mb" label="单文件上限 MB">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="weekly_token_quota" label="周 Token 额度">
            <InputNumber min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="max_parallel_sessions" label="最大并行会话">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="max_parallel_automations" label="最大并行自动化">
            <InputNumber min={1} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
