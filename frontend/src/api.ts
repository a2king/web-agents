import axios from "axios";

const client = axios.create({ baseURL: "/api" });

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

export async function api<T = any>(method: string, url: string, data?: any, extra?: any): Promise<T> {
  const resp = await client.request({ method, url, data, ...extra });
  if (resp.data?.ok === false) {
    throw new Error(resp.data.error || "请求失败");
  }
  return resp.data;
}

export async function downloadFile(path: string) {
  const resp = await client.get(`/files/download`, { params: { path }, responseType: "blob" });
  const name = path.split("/").pop() || "download";
  const url = URL.createObjectURL(resp.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export { client };
