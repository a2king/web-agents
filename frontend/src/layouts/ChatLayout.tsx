import {
  DashboardOutlined,
  DeleteOutlined,
  FileOutlined,
  LogoutOutlined,
  PlusOutlined,
  ScheduleOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Dropdown, Modal, message } from "antd";
import { useEffect, useState } from "react";
import { Link, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

const STATUS_DOT: Record<string, string> = {
  running: "#10a37f",
  confirm: "#f59e0b",
  queued: "#8b5cf6",
  idle: "transparent",
};

export default function ChatLayout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const { id } = useParams();
  const location = useLocation();
  const [rows, setRows] = useState<any[]>([]);

  const load = async () => {
    const resp = await api("get", "/sessions");
    setRows(resp.data || []);
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [location.pathname]);

  const create = async () => {
    const models = await api("get", "/models");
    const modelId = models.data?.[0]?.id;
    const resp = await api("post", "/sessions", { model_id: modelId, title: "新对话" });
    nav(`/sessions/${resp.data.id}`);
  };

  const remove = (row: any) => {
    Modal.confirm({
      title: "删除对话？",
      content: "将同时删除该会话目录下的产物，且不可恢复。",
      okType: "danger",
      onOk: async () => {
        await api("delete", `/sessions/${row.id}`);
        message.success("已删除");
        if (String(row.id) === String(id)) nav("/sessions");
        load();
      },
    });
  };

  return (
    <div className="gpt-shell">
      <aside className="gpt-sidebar">
        <button className="gpt-newchat" type="button" onClick={create}>
          <PlusOutlined />
          <span>新对话</span>
        </button>
        <div className="gpt-history-label">对话</div>
        <div className="gpt-history">
          {rows.map((row) => (
            <div
              key={row.id}
              className={`gpt-history-item ${String(row.id) === String(id) ? "active" : ""} ${row.border_status}`}
            >
              <Link to={`/sessions/${row.id}`} className="gpt-history-link">
                <span className="gpt-dot" style={{ background: STATUS_DOT[row.border_status] || "transparent" }} />
                <span className="gpt-history-title">{row.title}</span>
              </Link>
              <button
                type="button"
                className="gpt-history-del"
                onClick={(e) => {
                  e.preventDefault();
                  remove(row);
                }}
              >
                <DeleteOutlined />
              </button>
            </div>
          ))}
          {rows.length === 0 && <div className="gpt-history-empty">还没有对话</div>}
        </div>
        <div className="gpt-side-foot">
          <Link to="/files">
            <FileOutlined /> 文件空间
          </Link>
          <Link to="/skills">
            <ThunderboltOutlined /> Skills
          </Link>
          <Link to="/automations">
            <ScheduleOutlined /> 自动化
          </Link>
          <Link to="/usage">
            <DashboardOutlined /> Token 用量
          </Link>
          {user?.role === "admin" && (
            <Link to="/admin/tenants">
              <SettingOutlined /> 管理后台
            </Link>
          )}
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
            <button type="button" className="gpt-user">
              <span className="gpt-avatar">{(user?.display_name || "U").slice(0, 1)}</span>
              <span>{user?.display_name}</span>
            </button>
          </Dropdown>
        </div>
      </aside>
      <main className="gpt-main">
        <Outlet />
      </main>
    </div>
  );
}
