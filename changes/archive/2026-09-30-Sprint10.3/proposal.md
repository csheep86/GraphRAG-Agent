# Sprint 10.3 — 部署前置 D-1：容器化（Dockerfile + compose 起全套）

> **批次**：Sprint 10 批次 F（收尾批次 E 之后）
> **范围**：`deployment-spec.md` **D-1**（容器化）的 **CP-D0 前半**；**D-2a 迁移基线已于 Sprint 9.7 完成**，不在本批
> **关联**：`docs/deployment-spec.md` §0 D-1 / §1 交付形态 / §2 组件清单 / §11 排期；`docs/sprint-calendar.md` **CP-D0**
> **性质**：与业务**完全解耦**——不动契约、不动问答 / 建图链路，只补"可交付形态"

---

## 1. 缺口与实测（2026-09-30 复核，非转述旧文档）

| # | 项 | 实测 | 出处 |
|---|---|---|---|
| 1 | **全仓无容器化产物** | `Dockerfile*` / `docker-compose*` 全仓命中 = **0**（唯一命中是 `backend/alembic.ini`） | 本批开工前复核，与 `deployment-spec.md` §0 D-1 一致 |
| 2 | **D-2a 已完成**（本批不再做） | `backend/migrations/versions/` 下 **5 个**迁移脚本：基线 `00f44b912817` + 4 个后续；`alembic.ini` / `env.py` 就位 | Sprint 9.7；`sprint-calendar.md` S9.7 行 |
| 3 | **后端实际依赖** | `DATABASE_URL=sqlite:///./dev.db`（**尚未切 PG**，PG 切换在 S11）+ `NEO4J_URI=bolt://localhost:7687` + CORS 允许 `:3000`；开发端口 **8002** | `backend/.env` |
| 4 | **无 compose 的真实代价（今日活证据）** | 本机曾存在**两个手工 `docker run` 出来的 Neo4j**（一个匿名、一个 `kg-poc-neo4j`），7687/7474 端口互占；无用镜像 `neo4j:latest` 1.14GB + 匿名卷 1.45GB ≈ **2.6GB** 白占，今日已清理 | 见 §2 |

### 2. 为什么现在做（不是"等 S11 一起"）

`sprint-calendar.md` **CP-D0** 的原始理由已写明：容器化与业务功能解耦，提前做可提前暴露离线打包问题，**S11 因此降载**。
今日实测给了第二条理由：**没有 compose ⇒ 环境来源不可复现**。两个 Neo4j 都是谁手工跑起来的、连的是哪个、密码是什么，全靠记忆；清理时只能靠"连得上的是哪个"反推。这不是洁癖问题——它是**私有化交付的同一类病**：客户现场装出来的环境，也不会有人记得住。

---

## 3. 裁决

| # | 裁决 | 判据 |
|---|---|---|
| **D-L** | **本次不引入 PG 容器**：compose 只起 **Neo4j + backend + frontend** 三件，SQLite 落 named volume；compose 内留注释标注「PG 位：S11 切 PG 时加入」 | CP-D0 字面要求「起全套 Neo4j / PG / backend / frontend」，但**当前后端实际连的是 SQLite**（实测 3）。起一个**没有任何组件连接**的 PG，就是**假组件**——违反 PRD §7.2 零假数据 + A16 诚实可核（R19「屏幕上的已完成必须由后端给出」同源纪律）。宁可 **3/4 显式登记待补**，不可凑满 4 个容器冒充"全套" |
| **D-M** | 端口取 `deployment-spec` §2 默认（backend **8000** / frontend **3000** / Neo4j **7687+7474**），**全部可经 `.env` 覆盖**；且 **PG / Neo4j 只绑 `127.0.0.1`**（§2「端口不对外」） | 本机 8002 是开发端口，交付形态按规格走 8000；本机 7687/7474 现被 `kg-poc-neo4j` 占用 ⇒ **验证前须先停该容器**，不靠改宿主端口绕开（绕开等于没验证默认配置） |
| **D-N** | 镜像：backend 用 **`uv`** 按 `pyproject.toml` 装依赖并 **baked 进镜像**；frontend `npm ci` + `next build` + **`next start`**（**非** `next dev`）；Neo4j 镜像 tag **固定 `5.26-community`**，**禁用 `:latest`** | §1.2「不做客户现场编译 / 禁现场 `pip install`」；§2「frontend 用 `next start`」。禁用 latest 的判据是今日实测：本机曾同时存在 `neo4j:latest` 与 `5.26-community` 两份近 1GB 镜像，而**只有后者真在用**——latest 是不可复现的同义词 |
| **D-O** | **离线镜像包（`docker save`）本次不做**（属 S11 **CP-D1**）；但要求：① 所有镜像 tag 固定；② 建 `deploy/` 目录放 compose + `.env.example`，为 S11 打包留唯一入口 | §11 排期表：D-1 容器化 = S11（镜像包含）；CP-D0 只要求「Dockerfile + compose 起全套」。本批把"能起来"证掉，S11 只补"能打包带走" |
| **D-P** | **不改契约、不动业务代码**；确需改动仅限启动配置（host / port 从 env 读） | 容器化与业务解耦（CP-D0 原文）。契约零漂移是每批硬门禁 |

---

## 4. 落地范围（文件清单）

| 文件 | 内容 |
|---|---|
| `backend/Dockerfile` | 多阶段或单阶段 slim；`uv sync` 装依赖；非 root 用户；`uvicorn app.main:app --host 0.0.0.0 --port ${PORT}` |
| `backend/.dockerignore` | 排除 `.venv` / `dev.db` / `__pycache__` / `.env`（**密钥禁入镜像**，§3） |
| `frontend/Dockerfile` | `node:<ver>-slim`；`npm ci` → `next build` → `next start` |
| `frontend/.dockerignore` | 排除 `node_modules` / `.next` 缓存 |
| `deploy/docker-compose.yml` | 三服务 + named volumes + `healthcheck` + `depends_on: condition: service_healthy`；Neo4j 仅绑 127.0.0.1 |
| `deploy/.env.example` | 端口 / Neo4j 密码 / `PRIVATE_DEPLOY_ENABLED=true`（§3 生产默认值）/ LLM 配置位；**不含任何真密钥** |
| `deploy/README.md` | 起停命令 + 本机端口冲突处置（先停 `kg-poc-neo4j`）+ 与 `deployment-spec.md` 的对应关系 |

---

## 5. 不做

- **不做** K8s / Helm（`TBD-D2`，v2.0 后再评估）；
- **不做**离线镜像包 / 私有 registry（S11 CP-D1）；
- **不做**备份恢复脚本、安装验收清单脚本化（S11）；
- **不做** PG 切换与 RLS（S11，ADR-0003）；
- **不动** Alembic 迁移基线（Sprint 9.7 已完成；PG 实测与升级演练留 S11，需 compose 就绪后做——**本批正是为其铺路**）；
- **不改**契约、不新增业务接口；
- **不做** `/health` 与 `/ready` 分离（`TBD-D5`，S11 立项）。

---

## 6. 验收（真机，本机执行）

| # | 项 | 判据 |
|---|---|---|
| 1 | compose 可解析 | `docker compose -f deploy/docker-compose.yml config` 退出码 0 |
| 2 | **起全套** | `docker compose up -d` ⇒ `docker compose ps` 三个服务全 `healthy` |
| 3 | 后端可达 | `GET http://127.0.0.1:8000/api/v1/health` = **200**（契约路径如此，**不是** `/health`） |
| 4 | 前端可达 | `GET http://127.0.0.1:3000` = **200**（且是 `next start` 产物，非 dev） |
| 5 | 端口未越界 | `docker compose ps` 确认 Neo4j 宿主绑定为 `127.0.0.1`，未裸暴露到业务网 |
| 6 | 无假组件 | compose 中**不存在**无人连接的容器（D-L 自证） |
| 7 | 门禁 | pytest / ruff check+format / `check_seams` / 契约零漂移（`export_openapi --check`）/ 前端 `gen:api`+`typecheck`+`lint` 全绿 |
| 8 | 不留垃圾 | 验证结束 `docker compose down` 后无悬空容器 / 匿名卷（今日清理教训） |

**冒烟边界（不伪装）**：compose 起的是**全新空 Neo4j**，无演示数据、LLM 需出网 ⇒ 本次冒烟**止于 3~5 项**（health + 页面可达）。
`deployment-spec.md` §10 的第 4~7 项（上传建图 / 问答溯源 / 审计 / RLS）**依赖 PG + 数据 + License**，属 S11 安装验收，本批**不碰、不宣称**。

---

## 7. 遗留承接

| # | 项 | 承接 |
|---|---|---|
| 1 | Sprint10 §4-1「`kg_qa_v4` 端到端问答真机未证（需 PG + LLM）」 | 日志原文写明"或并入**批次 F 容器化后的联调**" ⇒ 本批 compose 就绪后，这是**第一批可补验**的项（仍需 PG，S11） |
| 2 | Sprint10.1 §4-1「多跳答对率实测（≥0.80）」 | 同上 |
| 3 | PG 位空着 | D-L 已显式登记，S11 切 PG 时补 |
| 4 | `as-of` 文案泄漏 / 悬空边 19 条 | 与本批无关，继续挂 |
