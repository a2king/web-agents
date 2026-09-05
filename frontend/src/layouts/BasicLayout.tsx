import {
  CloudServerOutlined,
  DashboardOutlined,
  FileOutlined,
  LogoutOutlined,
  RobotOutlined,
  ScheduleOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  UnorderedListOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { ProLayout } from "@ant-design/pro-components";
import { Dropdown } from "antd";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function BasicLayout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const location = useLocation();

  const routes = {
    path: "/",
    routes: [
      { path: "/sessions", name: "对话", icon: <RobotOutlined /> },
      { path: "/files", name: "文件空间", icon: <FileOutlined /> },
      { path: "/skills", name: "Skills", icon: <ThunderboltOutlined /> },
      { path: "/automations", name: "自动化任务", icon: <ScheduleOutlined /> },
      { path: "/usage", name: "Token 用量", icon: <DashboardOutlined /> },
      ...(user?.role === "admin"
        ? [
            {
              path: "/admin",
              name: "管理后台",
              icon: <SettingOutlined />,
              routes: [
                { path: "/admin/tenants", name: "租户", icon: <UserOutlined /> },
                { path: "/admin/models", name: "模型", icon: <CloudServerOutlined /> },
                { path: "/admin/mcps", name: "MCP", icon: <CloudServerOutlined /> },
                { path: "/admin/queue", name: "排队任务", icon: <UnorderedListOutlined /> },
              ],
            },
          ]
        : []),
    ],
  };

  return (
    <div style={{ height: "100vh" }}>
      <ProLayout
        title="Web Agents"
        logo={false}
        location={location}
        route={routes}
        layout="mix"
        contentWidth="Fluid"
        avatarProps={{
          src: undefined,
          title: user?.display_name,
          size: "small",
          render: (_props, dom) => (
            <Dropdown
              menu={{
                items: [{ key: "logout", icon: <LogoutOutlined />, label: "退出登录" }],
                onClick: ({ key }) => {
                  if (key === "logout") {
                    logout();
                    nav("/login");
                  }
                },
              }}
            >
              {dom}
            </Dropdown>
          ),
        }}
        menuItemRender={(item, dom) => <Link to={item.path || "/"}>{dom}</Link>}
        token={{
          header: { colorBgHeader: "#fff" },
          sider: { colorMenuBackground: "#fff" },
        }}
      >
        <Outlet />
      </ProLayout>
    </div>
  );
}
