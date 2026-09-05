import { Card, Progress, Statistic } from "antd";
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Usage() {
  const [data, setData] = useState<any>(null);
  useEffect(() => {
    api("get", "/usage").then((r) => setData(r.data));
  }, []);
  if (!data) return null;
  const percent = data.weekly_token_quota ? Math.min(100, Math.round((data.total_tokens / data.weekly_token_quota) * 100)) : 0;
  return (
    <Card title="本周 Token 用量">
      <Statistic title="本周起始（周一）" value={data.week_start} />
      <div style={{ marginTop: 24 }}>
        <Progress percent={percent} status={data.over_quota ? "exception" : "active"} />
        <p>
          已用 {data.total_tokens} / {data.weekly_token_quota}，剩余 {data.remaining}
        </p>
        {data.over_quota && <p>已超额，新任务将排队，请联系管理员上调额度。</p>}
      </div>
    </Card>
  );
}
