import { Button, Card, Form, Input, Modal, Select, Table, message } from "antd";
import { useEffect, useState } from "react";
import { api } from "../../api";

export default function Mcps() {
  const [rows, setRows] = useState<any[]>([]);
  const [tenants, setTenants] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [assign, setAssign] = useState<any>(null);
  const [tenantIds, setTenantIds] = useState<number[]>([]);
  const [form] = Form.useForm();

  const load = async () => {
    const [m, t] = await Promise.all([api("get", "/admin/mcps"), api("get", "/admin/tenants")]);
    setRows(m.data);
    setTenants(t.data);
  };
  useEffect(() => {
    load();
  }, []);

  return (
    <Card
      title="MCP 目录"
      extra={
        <Button type="primary" onClick={() => setOpen(true)}>
          录入 MCP
        </Button>
      }
    >
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "传输", dataIndex: "transport" },
          { title: "URL", dataIndex: "url" },
          { title: "已分配租户", dataIndex: "tenant_ids", render: (v) => (v || []).join(", ") },
          {
            title: "操作",
            render: (_, r) => (
              <>
                <a
                  onClick={() => {
                    setAssign(r);
                    setTenantIds(r.tenant_ids || []);
                  }}
                >
                  分配租户
                </a>
                <a
                  style={{ marginLeft: 12 }}
                  onClick={async () => {
                    await api("delete", `/admin/mcps/${r.id}`);
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
      <Modal
        title="录入 MCP"
        open={open}
        onOk={async () => {
          await api("post", "/admin/mcps", await form.validateFields());
          message.success("已保存");
          setOpen(false);
          form.resetFields();
          load();
        }}
        onCancel={() => setOpen(false)}
      >
        <Form form={form} layout="vertical" initialValues={{ transport: "sse" }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="transport" label="传输">
            <Select
              options={[
                { value: "sse", label: "SSE" },
                { value: "streamable_http", label: "Streamable HTTP" },
                { value: "stdio", label: "stdio（预留）" },
              ]}
            />
          </Form.Item>
          <Form.Item name="url" label="URL">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title="按租户分配"
        open={!!assign}
        onOk={async () => {
          await api("put", `/admin/mcps/${assign.id}/tenants`, { tenant_ids: tenantIds });
          setAssign(null);
          load();
        }}
        onCancel={() => setAssign(null)}
      >
        <Select
          mode="multiple"
          style={{ width: "100%" }}
          value={tenantIds}
          onChange={setTenantIds}
          options={tenants.map((t) => ({ value: t.id, label: t.name }))}
        />
      </Modal>
    </Card>
  );
}
