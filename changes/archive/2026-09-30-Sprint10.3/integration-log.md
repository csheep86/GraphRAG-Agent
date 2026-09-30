# Sprint 10.3 集成日志 — D-1 容器化（CP-D0）

> 范围：`deployment-spec.md` **D-1** 的 CP-D0 前半。**D-2a 迁移基线已于 Sprint 9.7 完成，本批不做**。
> 红线保持：不改契约、不动业务代码。**PG 位留空**（D-L）。

## 1. 开工前复核（实测，非转述）

| 项 | 实测 |
|---|---|
| 容器化产物 | `Dockerfile*` / `docker-compose*` 全仓命中 **0**（唯一命中 `backend/alembic.ini`） |
| 迁移基线 | `backend/migrations/versions/` **5 个**脚本（基线 `00f44b912817` + 4）⇒ D-2a 已完成 |
| 后端实际依赖 | SQLite（`DATABASE_URL=sqlite:///./dev.db`）+ Neo4j bolt 7687；开发端口 8002 |
| 无 compose 的代价 | 本机曾有两个手工 `docker run` 的 Neo4j，7687/7474 互占，无用镜像+卷 ≈ 2.6GB（本批开工前已清理） |

**更正一处文档笔误**：契约健康端点是 **`/api/v1/health`**（`app/api/v1/routes/health.py`），**不是** `/health`；提案与任务初稿已同步更正。

## 2. 落地

| 文件 | 要点 |
|---|---|
| `backend/Dockerfile` | `python:3.11-slim` + `uv:0.12.14` 固定版本；`uv sync --frozen --no-dev --no-install-project`；非 root；`/data` 承载 SQLite |
| `backend/.dockerignore` | `.env` / `dev.db` / `tests` / `scripts` 不进镜像 |
| `frontend/Dockerfile` | `node:22-slim`；`npm ci` → `next build` → **`next start`**；runtime 阶段 `--omit=dev` |
| `frontend/.dockerignore` | `node_modules` / `.next` / `.env*` |
| `deploy/docker-compose.yml` | 三服务 + 3 个 named volume + healthcheck + `depends_on: service_healthy`；Neo4j 只绑 `127.0.0.1` |
| `deploy/.env.example` | `NEO4J_PASSWORD` 必填（`${VAR:?}` 强校验）；`PRIVATE_DEPLOY_ENABLED=true` |
| `deploy/README.md` | 起停、端口冲突处置、**冒烟边界**、与规格的条目对应 |

## 3. 踩坑（三条，均可复用）

1. **compose `context` 与 `COPY` 路径不匹配**：初版 `context: ..`（仓库根）而 Dockerfile 写 `COPY app ./app` ⇒ 构建报 `"/alembic.ini": not found`。
   ⇒ 改为**各服务目录作 context**（`../backend` / `../frontend`），Dockerfile 与 `.dockerignore` 所见即所得。
2. **后台构建会被取消**：`Start-Process docker compose build` 随父会话终止 ⇒ buildx `CANCELED`。
   ⇒ 改**同步执行**（基础镜像预 `docker pull` 缓存后，backend 23.9s / frontend 26.1s）。
3. **匿名卷不是"没写就没事"**：`neo4j` 镜像自带 `VOLUME /data /logs`，只挂 `/data` ⇒ Docker 自建**匿名卷**（排障时不知谁创建、备份漏项）。
   ⇒ 显式 `neo4j_logs:/logs`，实测**匿名卷归零**。

**顺带钉死一条红线**：`NEXT_PUBLIC_USE_MOCK` 默认即 `true`（`frontend/src/api/client.ts:25` `!== "false"`，且 `NEXT_PUBLIC_*` **build 时内联**）
⇒ 容器化产物若漏传该 build-arg，前端会**静默走 Mock**：看起来能跑、数据全是假的（R18 同类）。已在 compose `args` 置 `false` 并写入 README。

## 4. 结果（真机）

| 项 | 结果 |
|---|---|
| `docker compose config` | 退出码 0 |
| `docker compose up -d` | backend / frontend / neo4j **三服务全 `healthy`** |
| `GET 127.0.0.1:8000/api/v1/health` | **200** `{"status":"ok","checks":{"database":"up"}}` |
| `GET 127.0.0.1:3000` | **200**（43,785 字节） |
| 端口暴露面 | Neo4j 仅 `127.0.0.1:7474 / 7687`（§2 不对外） |
| 镜像卫生 | 镜像内 **无 `.env`**、无 `dev.db`（`ls -a /app` 实测） |
| 卷 | 3 个 named volume；**匿名卷 0** |
| 收尾 | `compose down` 后无悬空容器；验证期间停掉的 `kg-poc-neo4j` 已 `docker start` 恢复 |

**本机端口冲突处置（D-M）**：7687/7474 常态被开发容器 `kg-poc-neo4j` 占用 ⇒ 验证时**停它再 up**，**不靠改宿主端口绕开**（绕开等于没验证默认配置）；验证后恢复。

## 5. 门禁

| 项 | 数字 |
|---|---|
| pytest | **640 passed / 3 skipped**（与批次前基线一致 ⇒ 本批零回归） |
| ruff check / format | All checks passed / 171 files already formatted |
| 契约零漂移 | `export_openapi --check` OK |
| `check_seams` | ERROR 0 / WARN 0 / OK 10 |
| 前端 | `typecheck` + `lint` 全绿 |

## 6. 未证 / 遗留（**不伪装**）

| # | 项 | 状态 |
|---|---|---|
| 1 | **离线镜像包**（`docker save`）/ 私有 registry | ⏳ **S11 CP-D1**；本批只证"能起来"，未证"能打包带走" |
| 2 | **PG 位空着** | D-L 显式登记：当前后端连 SQLite，PG 切换在 S11。**是 3/4，不写成"起全套"** |
| 3 | §10 安装验收 4~7 项（上传建图 / 问答溯源 / 审计 / RLS） | 依赖 **PG + 数据 + License**，属 S11；compose 起的是**空 Neo4j**，本批冒烟止于 health + 页面 200 |
| 4 | 备份恢复脚本 / 验收清单脚本化 | ⏳ S11 |
| 5 | `/health` 与 `/ready` 分离 | ⏳ TBD-D5，S11 立项 |
| 6 | Sprint10 §4-1 / Sprint10.1 §4-1「需 PG + LLM 的真机补验」 | compose 已就绪，但**仍缺 PG** ⇒ 继续挂，随 S11 切 PG 一并补 |

## 7. 文档同步（三处，口径一致）

- `docs/deployment-spec.md` §0：D-1 标「🔀 部分兑现（S10.3）+ 镜像包未做 + PG 留空」；导语补 2026-09-30 进展，并保留「镜像包补齐前不得承诺可私有化交付」；
- `docs/deployment-spec.md` §11：D-1 拆为 **D-1a ✅（S10.3）** / **D-1b ⏳（S11）** 两行；
- `docs/sprint-calendar.md` CP-D0 行：D-2a ✅ / D-1 ✅ 部分达成（3/4，不凑数）/ 镜像包属 S11。
