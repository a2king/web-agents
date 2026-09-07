import { Button, Card, Drawer, Form, Input, Select, Switch, Table, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Automations() {
  const [rows, setRows] = useState<any[]>([]);
  const [models, setModels] = useState<any[]>([]);
  const [skills, setSkills] = useState<any[]>([]);
  const [open, setOpen] = useState(false);
  const [runs, setRuns] = useState<any[]>([]);
  const [current, setCurrent] = useState<any>(null);
  const [form] = Form.useForm();

  const load = async () => {
    const [a, m, s] = await Promise.all([api("get", "/automations"), api("get", "/models"), api("get", "/skills")]);
    setRows(a.data);
    setModels(m.data);
    setSkills(s.data);
  };

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    const values = await form.validateFields();
    await api("post", "/automations", values);
    message.success("已创建");
    setOpen(false);
    form.resetFields();
    load();
  };

  return (
    <Card
      title="自动化任务"
      extra={
        <Button type="primary" onClick={() => setOpen(true)}>
          新建定时任务
        </Button>
      }
    >
      <Typography.Paragraph type="secondary">
        仅支持 Cron 定时。执行历史在此查看，不进入普通会话列表。并行数由管理员单独配置。
      </Typography.Paragraph>
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "Cron", dataIndex: "cron_expr" },
          { title: "Skill", dataIndex: "skill_slug" },
          { title: "下次执行", dataIndex: "next_run_at" },
          {
            title: "启用",
            render: (_, row) => (
              <Switch
                checked={row.enabled}
                onChange={async (v) => {
                  await api("put", `/automations/${row.id}`, { enabled: v });
                  load();
                }}
              />
            ),
          },
          {
            title: "操作",
            render: (_, row) => (
              <>
                <a
                  onClick={async () => {
                    const resp = await api("get", `/automations/${row.id}/runs`);
                    setCurrent(row);
                    setRuns(resp.data);
                  }}
                >
                  执行历史
                </a>
                <a
                  style={{ marginLeft: 12 }}
                  onClick={async () => {
                    await api("delete", `/automations/${row.id}`);
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
      <Drawer title="新建自动化" open={open} onClose={() => setOpen(false)} extra={<Button onClick={save}>保存</Button>}>
        <Form form={form} layout="vertical" initialValues={{ cron_expr: "0 9 * * 1", enabled: true }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="cron_expr" label="Cron" rules={[{ required: true }]}>
            <Input placeholder="0 9 * * 1" />
          </Form.Item>
          <Form.Item name="prompt" label="任务内容" rules={[{ required: true }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="skill_slug" label="指定 Skill">
            <Select allowClear options={skills.map((s) => ({ value: s.slug, label: `/${s.slug}` }))} />
          </Form.Item>
          <Form.Item name="model_id" label="模型">
            <Select options={models.map((m) => ({ value: m.id, label: m.name }))} />
          </Form.Item>
        </Form>
      </Drawer>
      <Drawer title={current ? `${current.name} 执行历史` : "执行历史"} open={!!current} onClose={() => setCurrent(null)} width={640}>
        <Table
          rowKey="id"
          dataSource={runs}
          columns={[
            { title: "状态", dataIndex: "status" },
            { title: "开始", dataIndex: "started_at" },
            { title: "结束", dataIndex: "finished_at" },
            { title: "错误", dataIndex: "error_message", ellipsis: true },
          ]}
        />
      </Drawer>
    </Card>
  );
}
