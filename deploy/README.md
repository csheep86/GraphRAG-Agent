# 部署入口（D-1 容器化）

> 规格真源：`docs/deployment-spec.md`。本目录只提供**单机交付的唯一安装入口**（§1.1）。
> 范围：**Sprint 10.3 = compose 能起全套**。**离线镜像包（§4 `docker save`）属 S11 CP-D1，本批不做**。

## 起停

```bash
cd deploy
cp .env.example .env        # 然后填 NEO4J_PASSWORD（≥8 位）
docker compose up -d        # 首次会构建 backend / frontend 两个镜像
docker compose ps           # 期望三个服务全 healthy
docker compose logs -f backend
docker compose down         # 停；数据卷保留
```

## 起的三个服务

| 服务 | 宿主端口 | 说明 |
|---|---|---|
| `neo4j` | `127.0.0.1:7474` / `127.0.0.1:7687` | 图存储；只绑回环（§2：不暴露业务网） |
| `backend` | `127.0.0.1:8000` | FastAPI + uvicorn；契约健康端点 **`/api/v1/health`** |
| `frontend` | `127.0.0.1:3000` | `next start`（**非** `next dev`） |

**为什么没有 PG**（裁决 D-L）：CP-D0 字面要求「起全套 Neo4j / PG / backend / frontend」，但当前后端实际连的是 **SQLite**（`backend/.env`），PG 切换在 S11。起一个没人连接的 PG 就是**假组件**（PRD §7.2 零假数据 + A16 诚实可核）。宁可 3/4 显式登记待补，不凑满容器冒充全套。**S11 切 PG 时在此补 `pg_data` 卷与服务。**

## 本机端口冲突（**必读**）

7687 / 7474 常已被开发用容器（如 `kg-poc-neo4j`）占用 ⇒ `compose up` 会报端口占用。
**处置**：先停掉那个容器，再起 compose——**不要**靠改宿主端口绕开，绕开等于没验证默认配置（裁决 D-M）。

```bash
docker ps --format '{{.Names}}\t{{.Ports}}'   # 谁占了 7687/7474
docker stop <那个容器>
```

## 冒烟边界（**不伪装**）

compose 起的是**全新空 Neo4j**，无演示数据；LLM 需出网 ⇒ 本批冒烟**止于**：

- `docker compose ps` 三服务 `healthy`
- `curl -i http://127.0.0.1:8000/api/v1/health` = 200
- `curl -i http://127.0.0.1:3000` = 200

`deployment-spec.md` §10 的第 4~7 项（上传建图 / 问答溯源 / 审计留痕 / RLS）依赖 **PG + 数据 + License**，属 **S11 安装验收**，本批不碰、不宣称。

## 前端 Mock 红线

`NEXT_PUBLIC_USE_MOCK` 默认即 `true`（`frontend/src/api/client.ts:25`）⇒ 构建时已在 compose 里置 **`false`**。
改这个值、或自建镜像时漏传该 build-arg，前端会**静默走 Mock**：看起来能跑、数据全是假的（R18 同类红线）。

## 与 `deployment-spec.md` 的对应

| 本文 | 规格 |
|---|---|
| `docker-compose.yml` + `.env.example` | §1.1 编排文件（唯一安装入口） |
| 只绑回环的 7474 / 7687 | §2 注：PG / Neo4j 禁止暴露业务网络 |
| 依赖 baked、非 root、无 `.env` 入镜像 | §1.2 禁现场编译；§3 密钥禁入镜像 |
| 缺离线镜像包 / 备份脚本 / 验收脚本化 | §11：均属 S11 |
