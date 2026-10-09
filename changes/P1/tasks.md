# P1 任务清单

> 与 [`proposal.md`](./proposal.md) 配套。**批次边界以 proposal §5 Non-goals 为准**。
> 每批收尾都要跑：`uv run python scripts/check_startup_readiness.py`，确认对应护栏**真的从「挂起」变「已生效」**。
> 只删 xfail、测试没真通过 —— **不算转正**（proposal 所引行动指引第 2 条）。

**状态（2026-10-01 完成）**：P1-A / P1-0 / P1-B / **P1-C 全部完成**。
收尾三件套实测：`pytest` **707 passed / 3 skipped / 8 xfailed**、ruff 双绿、
`check_startup_readiness.py` 已生效 **8 条**（新增 **G-8 / G-9**）。
事后实测证据与遗留事项记 [`integration-log.md`](./integration-log.md)
（本文件是事前计划，两者不可互相替代）。

---

## P1-A — DR-A6 版本化镜像 ✅ 已完成（2026-10-01）

- [x] compose 的 `backend` 补 `image:` + 固定 tag（`graphrag-agent/backend:1.6.0`）
- [x] compose 的 `frontend` 补 `image:` + 固定 tag（`graphrag-agent/frontend:1.6.0`）
- [x] 确认 neo4j 的 `neo4j:5.26-community` 未被误改
- [x] 出口：`test_g19_compose_uses_versioned_images` 转正（`check_startup_readiness.py` 报 G-19 `[OK]`）
- [x] 决策点 1 **已裁决采纳 (a)**（阶段 0 落地）：新增
      `test_g19_own_image_tags_track_app_version` —— 有 `build:` 的服务，image tag 必须
      等于当前 `app_version`；**负向验证已做**（把 tag 改成 1.5.9 ⇒ 该用例 FAIL）

## P1-0 — PG 驱动 ✅ 已完成（2026-10-01）

- [x] `backend/pyproject.toml` 加 `psycopg[binary]>=3.3.6`
- [x] **同步更新 `uv.lock`**（`psycopg` 3.3.6 + `psycopg-binary` 均已入库，CI 的 `--frozen` 不红）
- [x] 出口：`python -c "import psycopg"` 通过（且 P1-C 探测已用它真连上 PG 16）

## P1-B — DR-B1 + DR-B3（合并）✅ 已完成（2026-10-01）

- [x] `app/core/config.py` 默认 `database_url` 改 postgresql（`_guard_production_sqlite` **保留**）
- [x] `app/core/config.py` 注释口径更正
- [x] `backend/.env.example` 的 `DATABASE_URL` 同步
- [x] `app/db/session.py` 删 SQLite 方言特判
- [x] `app/db/__init__.py` 模块文档口径更正
- [x] `app/schemas/health.py` 描述更正（仅剩「不代表 RLS 已生效」，属实）
- [x] 本地起 PG 跑通 `create_all`（P1-C 探测阶段复核：**12 张表，列与类型全对**）
- [x] compose 加 PG 服务（`postgres:16-alpine`，固定 tag）
- [x] compose 删 `sqlite_data` 卷
- [x] 出口：`test_g20_postgres_is_in_place` 与 `test_g21_no_sqlite_fallback_in_code` **同时**转正
- [x] 反向守卫 `test_g21_production_sqlite_guard_still_present` 仍绿（**未删除**）

---

## P1-C — DR-B2 / G-8（依赖 P1-B）

### C0 开工前实测（2026-10-01，**已完成**，结论直接决定下面怎么写）

起 `postgres:16-alpine` 容器真跑，不靠推断：

| 探测量 | 实测结果 |
|---|---|
| PG 16 上 `create_all` vs `Base.metadata` | 12 表；表名 / 列名 / **列类型** 三者全一致 |
| PG 16 上 `alembic upgrade head` vs 元数据 | 12 表；与 `create_all` 的产物**类型零差异** |
| PG 16 上 `alembic downgrade base` | 仅剩 `alembic_version`，无残留（第二条判据可用） |
| 全量 pytest 切 PG（第 1 次，全新库） | **705 passed / 3 skipped / 8 xfailed** |
| 全量 pytest 切 PG（第 2、3 次，**同一脏库**） | 同上；`documents` 已累积到 87 行 ⇒ 脏库场景真被覆盖 |
| 切 PG 后的 `XPASS(strict)` | **2 条**：`test_g8_...`、`test_g9_t1_...` |

**两条结论（把 RK-2 的缓冲从"不可预估"压成"已量过"）**：

1. **测试基建切 PG 不需要逐条改用例** —— 705 条与 SQLite 基线同数，无一条因方言差异而红。
2. **不需要会话级 schema 重置** —— 原来 SQLite 是"每跑一次换一个临时目录"，现在换成持久库；
   实测脏库连跑 3 次结论不变（CI 的 PG 容器每次更是全新的），故**不引入** `drop_all/create_all`。
   代价：本地开发者的测试库会缓慢累积数据。若日后出现"跑第二遍就红"的用例，再补重置。

⚠️ **遗留物**：探测用的容器 `graphrag-pg-probe`（`--rm -d`，`postgres:16-alpine`，5432）仍在跑，P1-C 期间继续用它；收尾时我会停掉。

### C1 测试库固定为 PG —— `backend/tests/conftest.py` ✅

- [x] `DATABASE_URL` 由「硬编码 sqlite 临时文件」改为
      `os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag_test")`
      - 用 **`setdefault`** 而非直接赋值：CI / 本地显式注入优先；未注入时回落固定测试库
        ⇒ **不会误用开发者 `.env` 里的开发库**（直接赋值会盖掉外部注入，不赋值会被 `.env` 带偏）
      - 库名固定 `graphrag_test`，与开发库 `graphrag` 分离，保住原有「测试库独立」语义
- [x] `graphrag_test` 不存在时自动建（`tests/pg_scratch.py::ensure_database`，须 `CREATEDB`；
      CI 的 `POSTGRES_USER` 是 superuser ✅）。建不动就抛**带 `docker run` 一行命令**的明确报错
- [x] `_TMP_DIR` **保留**，仍只服务 `STORAGE_ROOT`（存储隔离不受影响）
- [x] 验证：`uv run pytest -q` 全绿（707 passed）；`psql -d graphrag_test -c '\dt'` 见 12 张表

### C2 迁移基线测试改 PG —— `backend/tests/test_migrations_baseline.py` ✅

- [x] 新增 `backend/tests/pg_scratch.py`：封装 `create_database` / `drop_database` / `ensure_database` /
      `scratch_database` 上下文 / `database_url_for`
      （`isolation_level="AUTOCOMMIT"`；drop 前先 `pg_terminate_backend`，否则报 "being accessed by other users"）
      —— C1 与 C2 共用，避免两处各写一遍建库逻辑
- [x] `_make_config(db_path)` → 改接**连接串**；alembic 的 `sqlalchemy.url` 指向临时库 `graphrag_mig_<uuid12>`
- [x] 两个用例各自建 / 删临时库（`with scratch_database(...)`，`finally` 必删）
- [x] `_schema_of` 判据不变（表名 + 列名）—— C0 实测类型已零差异，**不**顺手升级成类型比对
- [x] 验证：`uv run pytest tests/test_migrations_baseline.py -q` ⇒ 2 passed；
      `psql -Atc '\l'` 只剩 `graphrag` / `graphrag_test`，**无 `graphrag_mig_*` 残留**

### C3 G-8 转正 —— `backend/tests/test_guardrails.py` ✅

- [x] 摘掉 `test_g8_test_database_is_postgres` 的 `@pytest.mark.xfail(strict=True)`
- [x] docstring 由「当前跑在 SQLite 上」改写为常驻门禁口径
- [x] **（已裁决采纳）** 追加 **16.x** 断言：真连一次取 `SHOW server_version`，首段须为 `16`
      —— DR-B2 要的是「PostgreSQL **16.x**」，而原判据只看 URL 前缀，CI 换 15 / 17 照样绿
- [x] 验证：`pytest tests/test_guardrails.py::test_g8_test_database_is_postgres -q` 由 `XPASS` 变 `PASSED`

### C4 G-9 连带转正（切 PG 的必然产物，**不是**把 P3 提前做）✅

- [x] 摘掉 `test_g9_t1_cross_org_read_returns_empty` 的 `xfail(strict=True)`
      —— 它在 PG 上 XPASS ⇒ CI 必红，**必须**处理；留着就是让 CI 一直是红的
- [x] 边界已写进 `integration-log.md` §7：本次转正**只**代表
      「**应用层 org 过滤在 PG 上拦住了跨 org 读**（当前覆盖 `audit_log`）」；
      **不代表** RLS 落地（DR-B4 仍归 P3），`documents` / `qa_logs` / `storage_key` 与**图谱侧**仍待 P3
      （与需求基线 G-9 那行的注一致：图谱侧 CI 无 Neo4j，不得声称已由 CI 验证）
- [x] 验证：`pytest tests/test_guardrails.py -q` 全绿；`check_startup_readiness.py` 里 G-9 由 `[--]` 进 `[OK]`

### C5 CI 起 PostgreSQL —— `.github/workflows/ci.yml` ✅

- [x] `backend` job 加 `services.postgres`：
      `image: postgres:16-alpine`（**与 compose 同 tag**）、
      `POSTGRES_USER/PASSWORD=graphrag`、`POSTGRES_DB=graphrag_test`、
      `ports: ["5432:5432"]`、`options: --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5`
- [x] `backend` job **级** `env:` 注入 `DATABASE_URL`（放 job 级，不要只塞进 Pytest 那一个 step
      ——「本地独占用例」那一步也要连库）
- [x] 不动 `timeout-minutes: 15`（实测全量 16s 级，余量充足）
- [x] `contract` / `frontend` job **不动**（`export_openapi` 只 `create_engine` 不真连，无需 PG 服务）
- [x] 验证：`yaml.safe_load` 通过且 `services=['postgres']` / `image=postgres:16-alpine` /
      `env={'DATABASE_URL': '…/graphrag_test'}` / `steps=12`
      （**已验**：services 块缩进写错会让整个 workflow 静默失效）。GH Actions 上的结果待推送后看

### C6 口径注释更正（同类漂移；**不在** G-21 扫描范围内）✅

- [x] `tests/conftest.py`（「测试库是空 SQLite」）、`tests/test_task_recovery.py`、
      `tests/test_domain_events.py`、`tests/test_kg_versioning.py`、`tests/test_migrations_baseline.py` 的 docstring
- [x] `migrations/env.py`（「dev 默认 SQLite、生产 PG」）
- [x] `app/services/documents.py:7`（「读 PostgreSQL / SQLite 返回」）
- [x] ⚠️ **未动** `app/db/session.py` / `app/db/__init__.py` —— G-21 按**字样**扫描这两个文件，
      连「已删除 / 不是 SQLite」的说明都会判命中（本阶段已实踩两次）
- [x] ⚠️ **未动** `tests/test_guardrails_db.py` 里的判据字样 —— 那是**护栏本体**（它就是要扫出 sqlite），不是漂移
- [x] 验证：`uv run ruff check .` ✅ + `uv run ruff format --check .` ✅（186 files）

### C7 收尾三件套 + 留证 ✅

- [x] `uv run pytest -q` ⇒ **707 passed / 3 skipped / 8 xfailed**
      （passed 由 705 → **707**，skipped 仍 3；xfailed 由 10 降至 8 —— 差值正是 C3 / C4 转正的 2 条）
- [x] `uv run ruff check .` + `uv run ruff format --check .`（行宽 88）
- [x] `uv run python scripts/check_startup_readiness.py` ⇒ G-8 / G-9 进 `[OK]` 区（已生效合计 **8** 条）；
      `test_g21_production_sqlite_guard_still_present` 仍在 `[SG]` 且绿
- [x] 实测证据写入 `changes/P1/integration-log.md`（含 C0 那张表、三次全量跑的数字与 7 个坑）
- [x] 探测容器 `graphrag-pg-probe` **已停**（2026-10-01 收尾）
      —— ⚠️ **之后本地跑 `uv run pytest` 需要 PG 在 `localhost:5432`**，`graphrag_test` 库
      由 `tests/pg_scratch.py::ensure_database` 自动建，但**母库要先有**。一行复现：

      ```bash
      docker run --rm -d --name graphrag-pg \
        -e POSTGRES_USER=graphrag -e POSTGRES_PASSWORD=graphrag \
        -e POSTGRES_DB=graphrag -p 5432:5432 postgres:16-alpine
      ```

      （CI 侧不受影响：`ci.yml` 的 backend job 自带 `services.postgres`。）

### C-出口判据（一句话）

`ci.yml` 的 `backend` job **真的**起 PG 16 容器、`pytest` **真的**连它跑完 705 条，
`test_g8_test_database_is_postgres` **由 xfail 转常驻通过**（G-8 在 `check_startup_readiness.py` 里进 `[OK]` 区）。

### C-Non-goals（边界提醒，改到这些就是越界）

- **不**做 RLS（DR-B4）、**不**补 T1 的 `documents` / `qa_logs` / `storage_key` 与图谱侧、**不**做 T2 并发（DR-B7）—— 归 P3
- **不**碰 `users` 表 / RBAC / SSO（P2）、License（P4）、插件运行期装配
- **不**改 `deploy/docker-compose.yml`（PG 服务 P1-B 已加）
- **不**回退切 PG 后暴露的任何缺陷（ADR-0003 §3.6.2 已裁决为预期代价）—— 本次实测**没有**暴露任何缺陷
- 在途批次 `changes/P6-U/` 已冻结，不接

---

## 🔽 P1-E / P1-F —— **已裁决：整批推到 P2 之后（记为 `P2.5`）**

裁决日期：2026-10-01 ｜ 依据：`proposal.md` §6 决策点 2 ｜ 实证：ORM 12 张表里**没有 `users`**、
`plugins/` 与 `deploy/variants/` **均不存在**。

**为什么推后**（三条都过不去的现实）：

1. E 组做完也**转不了正** —— G-12 启用条件写死 `variant ≥ 2`，当前 0 个、且**不凑**第二个客户变体；
2. G-22 / G-14 的「恒绿失效」要等**变体 / 插件真的落地**才可能解除；
3. 同一份人力投到 `users` 表（P2 第一步）能同时解除 RK-1 并给 SSO / RBAC / License 开门，
   而 E 组在插件数为 0 时**既不能转正、也无法验证**。

**P2.5 的执行顺序**（届时直接照搬，不要再重排）：

- [ ] **E1 / DR-A2**：`plugins/<id>/plugin.yaml`，含 id / version / entry_point / seam / base_version
      ⇒ 出口：`test_g22_plugin_manifests_are_valid` 脱离恒绿失效
- [ ] **E2 / DR-A1**：`deploy/variants/<客户>.yaml` ⇒ **G-12 仍挂起**（需 ≥2 变体），不凑第二个
- [ ] **E3 / DR-A3**：Dockerfile 构建期烘焙（COPY 插件）；运行期动态装配**不在范围**
- [ ] **F / G-14**：随首个插件并入启用 `test_g14_base_contract_has_no_customer_specific_fields` 转正

---

## 三个裁决点：你均已确认采纳 ✅

1. ✅ **`check_startup_readiness.py` 的两条永久误报已修**。
   判据由 `"sqlite" not in cfg.lower()` 改为：取 `config.py` 的 `database_url` **字段默认值** +
   `.env.example` 的 **`DATABASE_URL=` 赋值行**来判（`_CFG_DB_URL_RE` / `_ENV_DB_URL_RE`）。
   理由：`config.py` 里的 `_guard_production_sqlite` 是 G-21 **反向守卫本体，必须保留**，
   按子串判会让它**永远 NG**。**未改任何门禁结论**，只修报告口径。
   修复后两条均由 `[NG]` 变 `[OK]`，剩余 4 项地雷（plugins / variants / License / users）是真缺口，属 P2~P4。
2. ✅ **G-8 已追加 16.x 断言**（见 C3）：真连一次取 `SHOW server_version`，首段须为 `16`。
3. ✅ **`docs/delivery-requirements-and-guardrails.md` 已同步**：G-8 / G-9 两行、§3 的 B 组行、
   §3.1 的 B1 / B2 / B3 / B6 行、§5 状态清单（新增「已解除最高 blocker」一条）、§6.3 第 4 条。

---

---

## 阶段 0 — 流水线修绿（**计划外的救火**，2026-10-01，✅ 已完成）

起因：排全局计划时发现 **HEAD 本来就是红的**（与 P1 无关，是更早的债）。
不修的话，P1-C 的 707 passed 是跑在红底上的，后续每批"收尾三件套"也无从验。
明细与实测证据见 `integration-log.md` §8。

- [x] **契约同步**（按 CODEBUDDY「契约同步铁律」四步）：`export_openapi.py --check` 零漂移 →
      `frontend/` 下 `npm run gen:api`（+18 / −1，补进 `as_of` / `valid_from` / `valid_to`）→
      Mock 核对 → `npm run typecheck` ✅ / `npm run lint` ✅
- [x] **`check_seams.py` 误报修正**：新增 `_collect_settings_self_reads()`，把 `Settings` 自己
      方法里的 `self.<字段>` 读取并入消费者 ⇒ **ERROR 1 → ERROR 0 / WARN 0 / OK 10**
      （并补两条回归测试）
- [x] **`check_session_drift.py` 批次识别修正**：目录 glob 覆盖 `changes/P*`（原来只认
      `changes/Sprint*`）＋ 活跃度改按"`*.md` 最大 mtime"＋多份 md 时 `proposal.md` 优先
      ⇒ S1 由报 `Sprint10.5`（5 条边界）变为报 `changes/P1/proposal.md`（**9 条**）
- [x] **决策点 1 采纳 (a)**：G-19 补 tag ↔ `app_version` 断言（含负向验证）

## 待你决策 ✅ 全部已裁决（2026-10-01）

1. ✅ `check_seams.py` 的 ERROR ⇒ 确认为**门禁误报**，按建议**改判据**（非放宽），已修。
2. ✅ `api.d.ts` 过期 ⇒ 按建议**同步掉**（它本来就属于 HEAD 的红，不是 P1 引入的 diff）。
3. ✅ 决策点 1 ⇒ 采纳 **(a) 补断言**（已落地，见 P1-A 行与阶段 0）。
4. ✅ 决策点 2 ⇒ E / F 组**整批推到 P2 之后**（记为 `P2.5`），本阶段只保留 A / 0 / B / C。
