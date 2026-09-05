import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import BasicLayout from "./layouts/BasicLayout";
import ChatLayout from "./layouts/ChatLayout";
import Login from "./pages/Login";
import ChatHome from "./pages/ChatHome";
import SessionDetail from "./pages/SessionDetail";
import Files from "./pages/Files";
import Skills from "./pages/Skills";
import Automations from "./pages/Automations";
import Usage from "./pages/Usage";
import Tenants from "./pages/admin/Tenants";
import Models from "./pages/admin/Models";
import Mcps from "./pages/admin/Mcps";
import Queue from "./pages/admin/Queue";

function Private({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AdminOnly({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  if (user?.role !== "admin") return <Navigate to="/sessions" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/sessions"
          element={
            <Private>
              <ChatLayout />
            </Private>
          }
        >
          <Route index element={<ChatHome />} />
          <Route path=":id" element={<SessionDetail />} />
        </Route>
        <Route
          path="/"
          element={
            <Private>
              <BasicLayout />
            </Private>
          }
        >
          <Route index element={<Navigate to="/sessions" replace />} />
          <Route path="files" element={<Files />} />
          <Route path="skills" element={<Skills />} />
          <Route path="automations" element={<Automations />} />
          <Route path="usage" element={<Usage />} />
          <Route
            path="admin/tenants"
            element={
              <AdminOnly>
                <Tenants />
              </AdminOnly>
            }
          />
          <Route
            path="admin/models"
            element={
              <AdminOnly>
                <Models />
              </AdminOnly>
            }
          />
          <Route
            path="admin/mcps"
            element={
              <AdminOnly>
                <Mcps />
              </AdminOnly>
            }
          />
          <Route
            path="admin/queue"
            element={
              <AdminOnly>
                <Queue />
              </AdminOnly>
            }
          />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
