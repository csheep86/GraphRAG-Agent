# Sprint 10.3 任务清单 — D-1 容器化（CP-D0）

> 前置：**D-2a 迁移基线已完成**（Sprint 9.7），本批不做。
> 红线：**不改契约、不动业务代码**（D-P）；**不引入无人连接的容器**（D-L）。
> 裁决编号沿用 `proposal.md` D-L ~ D-P。

---

## T1 — backend 镜像

- [ ] 写 `backend/Dockerfile`：官方 slim 基础镜像；`uv sync` 按 `pyproject.toml` 装依赖（**baked，禁现场 pip install**，D-N）
- [ ] 非 root 用户运行；`CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`
- [ ] 写 `backend/.dockerignore`：排除 `.venv` / `dev.db` / `__pycache__` / `.env` / `*.log`
- [ ] 判据：`docker build` 成功；镜像内**无** `.env`（`docker run --rm <img> ls -a | grep -c '^\.env$'` = 0，§3 密钥禁入镜像）

## T2 — frontend 镜像

- [ ] 写 `frontend/Dockerfile`：`node:<.nvmrc>-slim`；`npm ci` → `next build` → **`next start`**（D-N，禁止 `next dev`）
- [ ] 写 `frontend/.dockerignore`：排除 `node_modules` / `.next`
- [ ] 判据：`docker build` 成功；启动日志出现 `next start`（非 `ready in development`）

## T3 — compose 编排

- [ ] 写 `deploy/docker-compose.yml`：服务 = **Neo4j + backend + frontend**（D-L，**不含 PG**）
- [ ] Neo4j 镜像 tag 固定 **`neo4j:5.26-community`**，**禁用 `:latest`**（D-N）
- [ ] named volumes：`neo4j_data`（图）、`sqlite_data`（`dev.db` 落卷）
- [ ] `healthcheck`：backend 用 `/health`；Neo4j 用 7474 或 `cypher-shell`；`depends_on: condition: service_healthy`
- [ ] Neo4j 宿主绑定 **`127.0.0.1`**（D-M，§2 端口不对外）
- [ ] 写 `deploy/.env.example`：端口 / Neo4j 密码占位 / `PRIVATE_DEPLOY_ENABLED=true` / LLM 配置位；**不含真密钥**
- [ ] compose 内注释标注「PG 位：S11 切 PG 时加入（当前后端为 SQLite）」
- [ ] 判据：`docker compose config` 退出码 0；compose 中**无**无人连接的容器

## T4 — 部署入口文档

- [ ] 写 `deploy/README.md`：起停命令、与 `deployment-spec.md` 的条目对应、**本机端口冲突处置**（先停 `kg-poc-neo4j`）
- [ ] 判据：照 README 从零可复现（T5 实跑验证）

## T5 — 本机真机验证

- [ ] **先停 `kg-poc-neo4j`**（7687/7474 现被占用；不靠改宿主端口绕开，D-M）
- [ ] `docker compose -f deploy/docker-compose.yml up -d`
- [ ] `docker compose ps` 三服务全 `healthy`
- [ ] `GET 127.0.0.1:8000/api/v1/health` = 200（契约路径是 `/api/v1/health`，**不是** `/health`）；`GET 127.0.0.1:3000` = 200
- [ ] 确认 Neo4j 宿主绑定仅 `127.0.0.1`
- [ ] 验证完 `docker compose down` ⇒ **无悬空容器 / 匿名卷**（今日清理教训）
- [ ] 判据：`proposal.md` §6 中 1~6、8 项全过；7 项见 T6

## T6 — 门禁

- [ ] `pytest` 全绿（基线 **640 passed / 3 skipped**，本批应无增减——不改业务代码）
- [ ] `ruff check` + `ruff format` 通过
- [ ] 契约零漂移：`export_openapi --check` OK（**本批契约路径数不变**）
- [ ] `check_seams` ERROR 0 / WARN 0
- [ ] 前端：`gen:api` → `typecheck` → `lint` 全绿

## T7 — 文档同步（三处）

- [ ] `docs/deployment-spec.md` §0 D-1 行：状态改「**compose 起全套已完成（2026-09-30，Sprint 10.3）**；离线镜像包留 S11」
- [ ] `docs/deployment-spec.md` §11 排期表：D-1 拆成「容器化 ✅ / 镜像包 ⏳ S11」两行
- [ ] `docs/sprint-calendar.md` **CP-D0** 行：标注 D-2a ✅（S9.7）/ D-1 ✅（S10.3，PG 位待 S11）
- [ ] 判据：三处口径一致，无「已完成」冒充（**不把 3/4 写成起全套**）

---

## 不做（写入以防范围膨胀）

K8s/Helm（TBD-D2）· 离线镜像包（S11 CP-D1）· 备份恢复脚本（S11）· PG 切换与 RLS（S11）· 契约变更 · Alembic 改动 · `/health` 与 `/ready` 分离（TBD-D5）
