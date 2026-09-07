import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { Button, Card, Form, Input, Radio, Typography, message } from "antd";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export default function Login() {
  const nav = useNavigate();
  const { refresh } = useAuth();

  const onFinish = async (values: any) => {
    try {
      const resp = await api<{ data: { token: string } }>("post", "/auth/login", values);
      localStorage.setItem("token", resp.data.token);
      await refresh();
      message.success("登录成功");
      nav("/sessions");
    } catch (e: any) {
      message.error(e.response?.data?.error || e.message || "登录失败");
    }
  };

  return (
    <div className="login-wrap">
      <Card className="login-card" bordered={false}>
        <Typography.Title level={3} style={{ textAlign: "center" }}>
          Web Agents
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ textAlign: "center" }}>
          企业内部多租户 Agent 平台
        </Typography.Paragraph>
        <Form layout="vertical" onFinish={onFinish} initialValues={{ method: "local" }}>
          <Form.Item name="method">
            <Radio.Group>
              <Radio.Button value="local">本地账号</Radio.Button>
              <Radio.Button value="ldap">LDAP（预留）</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
