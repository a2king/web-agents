import { Card, Table, Typography } from "antd";
import { useEffect, useState } from "react";
import { api } from "../../api";

export default function Queue() {
  const [data, setData] = useState<any>({ sessions: [] });
  const load = async () => setData((await api("get", "/admin/queue")).data);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  return (
    <Card title="排队任务">
      <Typography.Paragraph type="secondary">
        Token 超额或并行打满的会话会进入排队。上调租户周额度后会自动尝试恢复。
      </Typography.Paragraph>
      <Table
        rowKey="id"
        dataSource={data.sessions}
        columns={[
          { title: "会话", dataIndex: "title" },
          { title: "原因", dataIndex: "queue_reason" },
          { title: "更新时间", dataIndex: "updated_at" },
        ]}
      />
    </Card>
  );
}
