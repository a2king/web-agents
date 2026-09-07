# Web Agents

企业内部多租户 Web Agent 平台：一人一租户独立空间，后台执行任务，关闭页面后仍可继续，二次打开可回看进度。

## 第一期能力

- **租户隔离**：独立文件空间（`shared/`、`sessions/{id}/`、`skills/`），删除租户释放全部文件
- **会话**：多轮、一会话一 Agent；运行中只读旁观、可取消；删除会话同时删除产物
- **状态边框**：运行中（蓝）/ 待确认（橙）/ 排队（紫）/ 空闲（灰）
- **Skills**：用户上传 zip（md / py / shell），会话中用 `/slug` 指定
- **MCP**：管理员统一录入并按租户勾选
- **模型**：管理员接入公司 OpenAI 兼容中转站，用户下拉选择
- **Token**：按周刷新额度，超额进入排队并提示管理员分配
- **高风险确认**：破坏性删除需确认（本次 / 本会话 / 本账号 / 拒绝）；装包等默认自动执行
- **自动化**：Cron 定时任务，独立列表与执行历史，单独并行数
- **运行时**：默认单机本地目录隔离；`RUNTIME_BACKEND=docker` 预留容器限额；多机免密 SSH 预留
- **登录**：本地账号先行，OpenLDAP 接口已预留

## 技术栈

- 前端：React + TypeScript + Ant Design Pro 组件（简化布局）
- 后端：Python Flask + SQLAlchemy
- 数据：现有 MySQL、Redis（任务队列 RQ + 事件流）
- Agent：LangGraph + langchain-openai（兼容 OpenAI 协议）

## 快速开始

1. 复制环境变量并指向现有 MySQL / Redis：

```bash
cp .env.example .env
# 修改 DATABASE_URL、REDIS_URL
```

2. 创建数据库（MySQL）：

```sql
CREATE DATABASE webagent DEFAULT CHARSET utf8mb4;
```

3. 启动后端：

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export $(grep -v '^#' ../.env | xargs)
python wsgi.py
```

4. 启动 Worker（后台执行会话 / 定时自动化）：

```bash
cd backend && source .venv/bin/activate
python worker.py
```

本地调试可不跑 Worker，设置 `WORKER_INLINE=1` 则在请求线程内执行。

5. 启动前端：

```bash
cd frontend
npm install
npm run dev
```

默认管理员：`admin` / `Admin@123`（可用环境变量修改）。管理员本身也拥有租户空间。

未配置真实中转站时，可添加 `model_id=demo` 且 `base_url` 以 `http://localhost` 开头的模型，走本地演示 Agent，便于联调文件空间与会话流。

## 配置说明

| 变量 | 含义 |
| --- | --- |
| `DATABASE_URL` | 现有 MySQL，例如 `mysql+pymysql://user:pass@host:3306/webagent` |
| `REDIS_URL` | 现有 Redis |
| `DATA_DIR` | 租户文件根目录 |
| `RUNTIME_BACKEND` | `local` / `docker` / `ssh` |
| `LDAP_ENABLED` | 第一期保持 `0`，接口已预留 |

## 开发测试

```bash
cd backend
WORKER_INLINE=1 pytest
```

## 部署

`docker-compose.yml` 可一键拉起 MySQL/Redis/API/Worker。若使用公司现成 MySQL/Redis，只需运行 `backend` 与 `worker`，并把连接串写入 `.env`。
