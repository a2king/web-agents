import { Card, Table, Typography } from "antd";
import { useEffect, useState } from "react";
import { api } from "../../api";

export default function Queue() {
  const [data, setData] = useState<any>({ sessions: [], automations: [] });
  const load = async () => setData((await api("get", "/admin/queue")).data);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <Card title="排队任务">
      <Typography.Paragraph type="secondary">
        Token 超额或并行打满的任务会进入排队。上调租户周额度后会自动尝试恢复。
      </Typography.Paragraph>
      <Typography.Title level={5}>会话排队</Typography.Title>
      <Table
        rowKey="id"
        dataSource={data.sessions}
        columns={[
          { title: "会话", dataIndex: "title" },
          { title: "原因", dataIndex: "queue_reason" },
          { title: "更新时间", dataIndex: "updated_at" },
        ]}
      />
      <Typography.Title level={5}>自动化排队</Typography.Title>
      <Table
        rowKey="id"
        dataSource={data.automations}
        columns={[
          { title: "任务", dataIndex: "automation_id" },
          { title: "状态", dataIndex: "status" },
          { title: "说明", dataIndex: "error_message" },
        ]}
      />
    </Card>
  );
}
