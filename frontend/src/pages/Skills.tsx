import { Button, Card, Table, Typography, Upload, message } from "antd";
import { useEffect, useState } from "react";
import { api, client } from "../api";

export default function Skills() {
  const [rows, setRows] = useState<any[]>([]);
  const load = async () => setRows((await api("get", "/skills")).data);
  useEffect(() => {
    load();
  }, []);

  return (
    <Card
      title="我的 Skills"
      extra={
        <Upload
          accept=".zip"
          showUploadList={false}
          customRequest={async (opt) => {
            const form = new FormData();
            form.append("file", opt.file as File);
            try {
              await client.post("/skills", form);
              message.success("已上传，会话中用 /名称 调用");
              load();
              opt.onSuccess?.({});
            } catch (e: any) {
              message.error(e.response?.data?.error || "上传失败");
              opt.onError?.(e);
            }
          }}
        >
          <Button type="primary">上传 zip</Button>
        </Upload>
      }
    >
      <Typography.Paragraph type="secondary">
        zip 内可包含 md / py / shell。会话输入以 <code>/slug</code> 开头即可指定该 skill。Skill 仅自己可用。
      </Typography.Paragraph>
      <Table
        rowKey="id"
        dataSource={rows}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "调用", dataIndex: "slug", render: (v) => `/${v}` },
          { title: "说明", dataIndex: "description", ellipsis: true },
          {
            title: "操作",
            render: (_, row) => (
              <a
                onClick={async () => {
                  await api("delete", `/skills/${row.id}`);
                  load();
                }}
              >
                删除
              </a>
            ),
          },
        ]}
      />
    </Card>
  );
}
