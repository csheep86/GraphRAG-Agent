# 部署入口（D-1 容器化）

> 规格真源：`docs/deployment-spec.md`。本目录只提供**单机交付的唯一安装入口**（§1.1）。
> 范围：**Sprint 10.3 = compose 能起全套**。
> ✅ **离线镜像包（§4 `docker save`）已于 2026-10-10（P6-D1b）落地** —— 见本文「离线交付」一节。
>
> ⚠️ **本目录有两份 compose，别拿错**：
> `docker-compose.yml` = **开发用**（带 `build:`，从源码起）；
> `docker-compose.delivery.yml` = **交付用**（**无 `build:`**，只认固定 tag 的镜像）——
> 客户现场、以及 §6.4 的**独立演练环境**都用这一份。

## 起停

```bash
cd deploy
cp .env.example .env        # 然后**四个都填**：NEO4J_PASSWORD（≥8 位）+ POSTGRES_PASSWORD
                            #                + APP_OWNER_PASSWORD + APP_RLS_PASSWORD
docker compose up -d        # 首次会构建 backend / frontend 两个镜像
docker compose ps           # 期望 backend / frontend / neo4j / postgres 四个**常驻**服务
                            # healthy；`db-init` 是**一次性**服务，退出码 0 属正常（见下）
docker compose logs -f backend
docker compose down         # 停；数据卷保留
```

### `db-init`：一次性建库服务（**P3-A，2026-10-04 起**）

RLS 生效的前提是「应用账号**不是**表 owner、且 `NOBYPASSRLS`」，而这个前提**只能由
超级用户建立一次**。compose 里干这件事的是 `db-init`：它以 PG 超级用户连进去，建
`app_owner`（建表 / 迁移）与 `app_rls`（受限，应用连库用的就是它）、建受控系统函数、
建表（首次）并对 14 张租户表落 `ENABLE` + `FORCE` + 策略，然后退出。

- **幂等**：每次 `up` 都跑，二次起是 no-op；改 `.env` 里的两个口令即可轮换。
- **`backend` 依赖它是 `service_completed_successfully`** ⇒ init 失败时 backend **不会**起来
  （避免出现"没装 RLS 也在对外服务"）。
- ⚠️ 因此 `docker compose ps` 看到 `db-init` 处于 `Exited (0)` 是**预期状态**，不是故障；
  若是 `Exited (1)`，看 `docker compose logs db-init`。

⚠️ **`docker compose build` 也需要 `.env`**（2026-10-04 实测踩到）：
compose 里 `POSTGRES_PASSWORD` / `NEO4J_PASSWORD` 写作 `${VAR:?}` 必填形式，
而 compose 在**解析阶段**就校验 ⇒ 没填的话**连构建都起不来**，报错是
`required variable POSTGRES_PASSWORD is missing a value`。
只想构建不想建 `.env` 时，可用临时环境变量顶上（**勿把真密钥写进命令行历史**）：

```bash
POSTGRES_PASSWORD=build-only NEO4J_PASSWORD=build-only docker compose build backend
```

## 起的服务（四个常驻 + 一个一次性）

| 服务 | 宿主端口 | 说明 |
|---|---|---|
| `neo4j` | `127.0.0.1:7474` / `127.0.0.1:7687` | 图存储；只绑回环（§2：不暴露业务网） |
| `postgres` | **不映射**（内部 5432） | PG 16.x（**DR-B1**）；§2「禁止暴露业务网络」⇒ 不映射端口。需直连：`docker compose exec postgres psql -U graphrag -d graphrag` |
| `db-init` | — | **一次性**（`restart: "no"`）：建 RLS 角色 / 受控函数 / 建表 / 落策略。复用 backend 镜像（P3-A） |
| `backend` | `127.0.0.1:8000` | FastAPI + uvicorn；契约健康端点 **`/api/v1/health`**。**以受限角色 `app_rls` 连库** |
| `frontend` | `127.0.0.1:3000` | `next start`（**非** `next dev`） |

**PG 已就位——裁决 D-L 已于 2026-10-01 作废**（以下为历史记述，**保留不删**，当前事实以
`docker compose ps` 与 `backend/app/core/config.py` 为准）：

> 原裁决 D-L：不引入 PG 容器，理由是「起一个没有任何组件连接的 PG 就是**假组件**」
> （PRD §7.2 零假数据 + A16 诚实可核）；当时后端实际连的是 SQLite，PG 切换在 S11。
>
> **该前提已被 DR-B1 推翻**：**开发 / 测试 / 生产一律 PostgreSQL 16.x**，不再用 SQLite 作替身。
> 切换严格按 D-L 当年防的那个顺序完成——**先**让 backend 默认连 PG 并实测跑通
> （`config.py` + `.env.example`），**才**在本文件引入 PG 服务 ⇒
> 这个 PG 是**真有应用连的**，不是假组件。SQLite 配置与 `sqlite_data` 卷已一并清除。

## 本机端口冲突（**必读**）

7687 / 7474 常已被开发用容器（如 `kg-poc-neo4j`）占用 ⇒ `compose up` 会报端口占用。
**处置**：先停掉那个容器，再起 compose——**不要**靠改宿主端口绕开，绕开等于没验证默认配置（裁决 D-M）。

```bash
docker ps --format '{{.Names}}\t{{.Ports}}'   # 谁占了 7687/7474
docker stop <那个容器>
```

## 冒烟边界（**不伪装**）

compose 起的是**全新空 Neo4j + 空 PostgreSQL**，无演示数据；LLM 需出网 ⇒ 本批冒烟**止于**：

- `docker compose ps` **四服务** `healthy`（含 `postgres`）
- `curl -i http://127.0.0.1:8000/api/v1/health` = 200
- `curl -i http://127.0.0.1:3000` = 200

`deployment-spec.md` §10 的第 4~7 项（上传建图 / 问答溯源 / 审计留痕 / RLS）依赖 **数据 + License + RLS**，属**安装验收**，本批不碰、不宣称。
（📌 **2026-10-04 订正**：PG 本身已就位并真被 backend 连接，此处缺的是 **RLS**——归 **P3**，不再笼统写成"依赖 PG"。）

## 前端 Mock 红线

`NEXT_PUBLIC_USE_MOCK` 默认即 `true`（`frontend/src/api/client.ts:25`）⇒ 构建时已在 compose 里置 **`false`**。
改这个值、或自建镜像时漏传该 build-arg，前端会**静默走 Mock**：看起来能跑、数据全是假的（R18 同类红线）。

## 离线交付（**P6-D1b，2026-10-10**）

**出包（我方）**：

```bash
cd backend
uv run python scripts/build_delivery_images.py --dry-run --save   # 先看完整命令（含 --build-arg）
uv run python scripts/build_delivery_images.py --save              # 构建 + docker save + 写清单
uv run python scripts/build_delivery_images.py --verify            # 重算 SHA-256 + 核 image id + 比对 tag
```

产物落在 `backend/reports/delivery/`（已被 gitignore ⇒ **绝不入库**）：

- `graphrag-agent-offline-<版本>.tar` —— **默认只打自研**（backend + frontend，实测 496,524,288 字节）；
- `delivery-manifest.json` —— tar 的 SHA-256 / 大小 + 每个镜像的 image id。

需要**全离线**（断网）的客户现场：出包时加 `--include-third-party`（把 neo4j / postgres 一并打入，
≈919 MB），**U 盘拷**上服务器。

**到货（客户现场）**：

```bash
docker load -i graphrag-agent-offline-<版本>.tar     # 导入自研镜像
cp .env.example .env                                  # 四个口令都要填
docker compose -f docker-compose.delivery.yml up -d   # 第三方两个 tag 已固定，联网现场自动拉取
```

> 交付 compose 的 `name:` 是 `${COMPOSE_PROJECT_NAME:-graphrag-agent}`：
> 同一台宿主机上要跑**独立**的演练环境时，设 `COMPOSE_PROJECT_NAME=graphrag-drill`
> 即可隔离项目名与数据卷（§6.4② 要求"独立 compose 项目 + 独立数据卷"）。
>
> ⚠️ **未演练**：以上只到"包已产出 + 可解析"。**独立环境的完整 `up` + 冒烟**属 **P6-X**
> （一人执行、一人见证，`docs/drills/restore-drill-<日期>.md`），缺它不得宣称"可交付"。

## 与 `deployment-spec.md` 的对应

| 本文 | 规格 |
|---|---|
| `docker-compose.yml` + `.env.example` | §1.1 编排文件（唯一安装入口） |
| 只绑回环的 7474 / 7687 | §2 注：PG / Neo4j 禁止暴露业务网络 |
| 依赖 baked、非 root、无 `.env` 入镜像 | §1.2 禁现场编译；§3 密钥禁入镜像 |
| `docker-compose.delivery.yml` + 出包脚本 + tar 清单 | §4 离线安装；§6.4①「从交付物部署（无 `build:`）」；§11 D-1b 行 |
| 备份 / 恢复脚本、验收脚本化 | §11（P6-W 已部分落地；**演练仍属 P6-X**） |
