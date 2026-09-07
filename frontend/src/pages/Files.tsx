import { Button, Card, Input, Space, Table, Upload, message } from "antd";
import { useEffect, useState } from "react";
import { api, client, downloadFile } from "../api";

export default function Files() {
  const [path, setPath] = useState("");
  const [data, setData] = useState<any>({ items: [], disk_used_mb: 0, disk_mb: 0 });

  const load = async (p = path) => {
    const resp = await api("get", `/files?path=${encodeURIComponent(p)}`);
    setData(resp.data);
    setPath(p);
  };

  useEffect(() => {
    load("");
  }, []);

  return (
    <Card
      title="租户文件空间"
      extra={
        <span>
          已用 {data.disk_used_mb} / {data.disk_mb} MB，单文件上限 {data.max_file_mb} MB
        </span>
      }
    >
      <Space style={{ marginBottom: 12 }} wrap>
        <Button onClick={() => load("")}>租户根目录</Button>
        <Button onClick={() => load("shared")}>/shared</Button>
        <Button onClick={() => load("sessions")}>/sessions</Button>
        <Input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          onPressEnter={() => load(path)}
          style={{ width: 320 }}
        />
        <Button
          onClick={async () => {
            await api("post", "/files/mkdir", { path });
            message.success("已创建目录");
            load(path);
          }}
        >
          新建当前目录
        </Button>
        <Upload
          showUploadList={false}
          customRequest={async (opt) => {
            const form = new FormData();
            form.append("path", path || "shared");
            form.append("file", opt.file as File);
            try {
              await client.post("/files/upload", form);
              message.success("上传成功");
              load(path);
              opt.onSuccess?.({});
            } catch (e: any) {
              message.error(e.response?.data?.error || "上传失败");
              opt.onError?.(e);
            }
          }}
        >
          <Button type="primary">上传到当前目录</Button>
        </Upload>
      </Space>
      <Table
        rowKey="path"
        dataSource={data.items}
        columns={[
          {
            title: "名称",
            dataIndex: "name",
            render: (v: string, row: any) =>
              row.is_dir ? (
                <a onClick={() => load(row.path)}>{v}/</a>
              ) : (
                v
              ),
          },
          { title: "大小", dataIndex: "size" },
          {
            title: "操作",
            render: (_: any, row: any) => (
              <Space>
                {!row.is_dir && <a onClick={() => downloadFile(row.path)}>下载</a>}
                {row.is_dir && (
                  <a onClick={() => load(row.path)}>打开</a>
                )}
                {!["sessions", "shared", "skills"].includes(row.path) && (
                  <a
                    onClick={async () => {
                      await api("delete", "/files", { path: row.path });
                      load(path);
                    }}
                  >
                    删除
                  </a>
                )}
              </Space>
            ),
          },
        ]}
      />
    </Card>
  );
}
