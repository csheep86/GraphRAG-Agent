# P1 实测集成日志

> **定位**：事后实测证据。事前计划见 [`proposal.md`](./proposal.md)、任务清单见 [`tasks.md`](./tasks.md)。
> 三者不可互相替代——**计划写"打算怎么做"，日志写"实际发生了什么"**。
>
> 批次：P1-A（DR-A6）/ P1-0（PG 驱动）/ P1-B（DR-B1 + DR-B3）/ **P1-C（DR-B2 / G-8）**
> 日期：2026-10-01 ｜ 环境：Windows 11 + Docker Desktop 29.7.2 + `postgres:16-alpine` + Python 3.11 / uv

---

## 0. 起跑状态（`check_startup_readiness.py` 实测）

已生效 6 条（G-11 / G-15 / G-17 / G-19 / G-20 / G-21）；挂起 7 条；地雷 6 项。

**地雷里有 2 项是脚本自身的误报**（不是代码没做），已在 P1-C 修正：

| 地雷 | 误报原因 |
|---|---|
| 「已切 PostgreSQL」NG | 判据是 `"sqlite" not in config.py.lower()`，而 `_guard_production_sqlite` 是 **G-21 反向守卫本体**，删不得 ⇒ 永久 NG |
| 「`.env.example` 非 SQLite」NG | 同上：注释里回顾口径历史也会被算成命中 |

修法：改为只取 `config.py` 的 `database_url` **字段默认值** 与 `.env.example` 的 **`DATABASE_URL=` 赋值行**来判。
**未改任何门禁结论**，只修报告口径。

---

## 1. P1-A / P1-0 / P1-B（已完成，复核）

| 批次 | 复核结论 |
|---|---|
| P1-A | compose 的 `backend` / `frontend` 均已 `image: graphrag-agent/{backend,frontend}:1.6.0`；neo4j 仍 `neo4j:5.26-community`；**G-19 已 `[OK]`** |
| P1-0 | `pyproject.toml` 有 `psycopg[binary]>=3.3.6`；`uv.lock` 已入库（psycopg 3.3.6 + psycopg-binary 全平台 wheel） |
| P1-B | `config.py` 默认 `postgresql+psycopg://…`；`.env.example` 同步；`session.py` / `db/__init__.py` / `health.py` 口径更正；compose 加 `postgres:16-alpine`、删 `sqlite_data`；**G-20 / G-21 已 `[OK]`，反向守卫仍绿** |

---

## 2. P1-C：开工前实测（**先跑，再写方案**）

### 2.1 方法

不是"推断切 PG 会怎样"，而是**起一个真容器**把未知量测出来：

```bash
docker run --rm -d --name graphrag-pg-probe \
  -e POSTGRES_USER=graphrag -e POSTGRES_PASSWORD=graphrag \
  -e POSTGRES_DB=graphrag -p 5432:5432 postgres:16-alpine
```

### 2.2 结论

| 探测量 | 实测结果 |
|---|---|
| PG 16 上 `create_all` vs `Base.metadata` | 12 表；**表名 / 列名 / 列类型三者全一致** |
| PG 16 上 `alembic upgrade head` vs 元数据 | 12 表；与 `create_all` 的产物**类型零差异** |
| PG 16 上 `alembic downgrade base` | 仅剩 `alembic_version`，无残留（第二条判据可用） |
| 全量 pytest 切 PG（第 1 次，全新库） | **705 passed / 3 skipped / 8 xfailed** |
| 全量 pytest 切 PG（第 2、3 次，**同一脏库**） | 同上。`documents` 累积到 87 行 ⇒ 脏库场景确实被覆盖了 |
| 切 PG 后的 `XPASS(strict)` | **2 条**：`test_g8_…`、`test_g9_t1_…` |

**两条把 RK-2 从「不可预估」压成「已量过」的结论**：

1. **测试基建切 PG 不需要逐条改用例** —— 705 条与 SQLite 基线同数，**没有一条**因方言差异而红。
   `test_guardrails_db.py` 里那 29 处 sqlite 字样几乎全是 **G-21 护栏本体的扫描判据**（必须保留），
   不是"测试跑在 SQLite 上"的证据——当初按数量估的工作量是被这个名字误导了。
2. **不引入会话级 schema 重置** —— 原 SQLite 是"每跑一次换一个临时目录"，切 PG 后库变持久；
   实测脏库连跑 3 次结论不变，CI 的容器更是每次全新 ⇒ 不为此加 `drop_all/create_all`。
   代价：本地开发者的测试库会缓慢累积数据。**若日后出现"跑第二遍才红"的用例，再补重置。**

---

## 3. P1-C：落地清单

| # | 文件 | 改动 |
|---|---|---|
| C1 | `backend/tests/pg_scratch.py`（新增） | PG 临时库工具：`create_database` / `drop_database` / `ensure_database` / `scratch_database` 上下文 / `database_url_for`。AUTOCOMMIT + `pg_terminate_backend` 两个坑都写进注释 |
| C1 | `backend/tests/conftest.py` | `DATABASE_URL` 由 SQLite 临时文件改为 `setdefault` 指向 `graphrag_test`；调用 `ensure_database()` 确保存在 |
| C2 | `backend/tests/test_migrations_baseline.py` | 临时 SQLite 文件 → PG 临时库 `graphrag_mig_<uuid12>`，`with scratch_database(...)` 保证必删 |
| C3 | `backend/tests/test_guardrails.py` | G-8 摘 xfail 转常驻门禁；**追加 `SHOW server_version` 必须 16.x** |
| C4 | 同上 | G-9 摘 xfail（留在 strict xfail 里 CI 会一直红） |
| C5 | `.github/workflows/ci.yml` | backend job 加 `services.postgres:16-alpine` + health check；**job 级** `DATABASE_URL` |
| C6 | 5 个测试 docstring + `migrations/env.py` + `app/services/documents.py` | SQLite 口径更正 |
| D1 | `backend/scripts/check_startup_readiness.py` | 修正上述 2 条地雷误报 |
| D3 | `docs/delivery-requirements-and-guardrails.md` | G-8 / G-9 行、§3.1 的 B1/B2/B3/B6 行、§3 B 组行、§5 状态清单、§6.3 第 4 条同步 |

### 关于 `setdefault` 而不是"直接赋值 / 完全不设"

| 写法 | 后果 |
|---|---|
| 直接赋值（旧写法） | 盖掉 CI 的显式注入 ⇒ CI 指哪都没用 |
| 完全不设 | 被开发者 `.env` 里的**开发库**带偏 ⇒ 测试写脏真实数据 |
| **`setdefault`** | 显式注入优先，未注入时回落固定测试库 `graphrag_test` |

---

## 4. 收尾三件套（实测输出）

```
uv run pytest -q
  707 passed, 3 skipped, 8 xfailed, 1 warning in ~16s
  （基线 705 / 3 / 10；差值 = G-8 与 G-9 由 xfail 转为 passed）

uv run ruff check .            All checks passed!
uv run ruff format --check .   186 files already formatted

uv run python scripts/check_startup_readiness.py
  [OK] 已生效：8 条  = G-11 / G-15 / G-17 / G-19 / G-20 / G-21 / **G-8** / **G-9**
  [~~] 部分生效：2 条 = G-14 / G-22（恒绿失效：plugins/ 与 deploy/variants/ 均不存在）
  [--] 挂起：5 条     = G-10 / G-12 / G-18 / G-23 / G-24
  [SG] 反向守卫       = test_g21_production_sqlite_guard_still_present ✅
  地雷 4 项           = plugins/ / deploy/variants/ / License / users（均属 P2~P4，本阶段不动）
```

YAML 结构已用 `yaml.safe_load` 校验（抗战 YAML 静默失效那条老坑）：

```
jobs:     ['backend', 'frontend', 'contract', 'ci-summary']
services: ['postgres']  image: postgres:16-alpine  ports: ['5432:5432']
env:      {'DATABASE_URL': 'postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag_test'}
```

孤儿库检查：跑完 `psql -Atc "\l"` 只剩 `graphrag` / `graphrag_test`，**无 `graphrag_mig_*` 残留**。

---

## 5. 遇到的坑（按本文上述顺序排）

1. **`CREATE DATABASE` 不能在自己身上执行** —— 想建 `graphrag_test` 却拿 `graphrag_test` 当跳板，
   报 `FATAL: database "graphrag_test" does not exist`。解法：一律挂到 maintenance 库 `postgres`。
2. **`CREATE DATABASE` 不能在事务里跑** —— 必须 `isolation_level="AUTOCOMMIT"`。
3. **`DROP DATABASE` 报 "being accessed by other users"** —— 先 `pg_terminate_backend`。
4. **库名要拼进 DDL 文本**（绑定参数对标识符无效）—— 用正则把它限制成 `[A-Za-z_][A-Za-z0-9_]*`。
5. **`https://` 之类的 URL 用 `rpartition("/")` 切库名必错** —— 改用 `make_url(...).set(database=…)`。
6. **`SHOW server_version` 形如 `16.9 (Debian 16.9-1…)`** —— 取 `.split(".", 1)[0]` 才是大版本。
7. **`import pg_scratch` 被 ruff 归到第三方组** —— CI 的 ruff 会挡；照它的排序放。

---

## 6. 遗留（**不在本批次边界内**，已报告待裁决）

| # | 事项 | 状态 |
|---|---|---|
| 1 | `check_seams.py` 报 `settings.allow_agent_fail_open 无消费者`（ERROR） | ✅ **已修（阶段 0，2026-10-01）**：确认为**门禁误报**（见 §8.2）。现 `check_seams.py` 为 **ERROR 0 / WARN 0 / OK 10** |
| 2 | `frontend/src/types/api.d.ts` 相对 `contracts/openapi.yaml` **已过期** | ✅ **已修（阶段 0，2026-10-01）**：HEAD 上就红 3 个字段（`as_of` / `valid_from` / `valid_to`）⇒ 已重新生成 + 按「契约同步铁律」核过 Mock（见 §8.1） |
| 3 | `contracts/openapi.yaml` 已重新导出 1 行 | P1-B 改了 `health.py` 的「SQLite 兜底期间」描述却没导出契约；本次补导出（**仅此 1 行**，已核对不含其他内容） |
| 4 | 决策点 1：G-19 是否补 tag↔`app_version` 一致性断言 | ✅ **已采纳 (a) 并落地（阶段 0）**：新增 `test_g19_own_image_tags_track_app_version`，**负向验证已做**（见 §8.3） |
| 5 | 探测容器 `graphrag-pg-probe` | 仍在跑（`-p 5432`），收尾可停 |

---

## 7. 边界声明（写在最后，防止被日后外推）

- **G-9 转正 ≠ RLS 落地**。本次只证明「**应用层 `org_id` 过滤**在 PostgreSQL 上拦住了跨 org 读
  （当前覆盖 `audit_log`）」。DR-B4（RLS）、`documents` / `qa_logs` / `storage_key`、
  以及**图谱侧**（DR-B11，CI 无 Neo4j）**仍全部归 P3**，不得因 G-9 转正而宣称完成。
- **G-8 转正 ≠ 租户隔离已验证**。它证明的是"测试跑在 PG 16.x 上"；
  T2 并发串租户（G-10 / DR-B7）仍是 xfail 挂起。

---

## 8. 阶段 0：流水线修绿（2026-10-01）

**缘起**：排全局计划时发现 **HEAD 本来就是红的** —— 与 P1 无关，是更早的债。
先列事实，再给处置：

| # | 事实（实测） | 处置 |
|---|---|---|
| ① | `contract` job 的前端侧检查在 HEAD 上必红：已提交的 `openapi.yaml` 里有 Sprint10.5 的三个字段，但 `api.d.ts` 从未重新生成 ⇒ `npm run gen:api` 产出 **+18 / −1** | §8.1 |
| ② | `check_seams.py` 报 `allow_agent_fail_open 无消费者`（ERROR）⇒ 接缝门禁红 | §8.2 |
| ③ | `check_session_drift.py` 的批次 glob 只认 `changes/Sprint*` ⇒ 整个 P1 期间 **S1 一直在拿 Sprint10.5 的边界对照本批改动**（报告长得像正常，对照的是错边界） | §8.4 |

### 8.1 契约同步（按 CODEBUDDY「契约同步铁律」四步）

1. `uv run python scripts/export_openapi.py --check` ⇒ **零漂移**（模型与契约一致）；
2. `frontend/` 下 `npm run gen:api` ⇒ `api.d.ts` **+18 / −1**：补进 `AgentQueryRequest.as_of`
   与推理链每一跳的 `valid_from` / `valid_to`（均来自 Sprint10.5 的 L2-③），
   并同步 P1-B 改过的 health 描述；
3. Mock 核对：`mock/compliance.ts` **本来就有** `as_of`（"2026-10-31"）⇒ 无需改；
   `mock/policy-qa.ts` 的 `reasoning_path` 是 **2026-09-28 的真机快照**，早于时效字段
   进契约 ⇒ **不补造假日期**，改为在文件头注明「这两跳没有 `valid_from` / `valid_to`，
   缺省按 ADR-0005 §6 读作不可判定」（造假数据比缺数据更坏）；
4. `npm run typecheck` ✅ / `npm run lint` ✅。

### 8.2 `check_seams.py` 误报修正

**根因**：`SKIP_FILES` 把 `config.py` 整个排除 ⇒ `Settings` **自己方法体里**的
`self.<字段>` 读取一个也进不了消费者清单。守卫类配置的消费者恰恰就是它自己的校验器
（`allow_agent_fail_open` 由 `_guard_agent_fail_open` 在 `config.py:218` 读取，
**读了还会抛错**——G-17 逃生阀围栏，货真价实的消费）。

修法（不是放宽判据）：新增 `_collect_settings_self_reads()`，把类内 `self.<字段>` 读取
并入消费者集合。**实测**：修复前 ERROR 1 ⇒ 修复后 **ERROR 0 / WARN 0 / OK 10**
（49 个 Settings 字段全部有消费者）。

并加两条回归测试锁住：`test_settings_self_read_counts_as_consumption`
（单元级：同一个字段，传 internal 则 OK、不传则 ERROR）与
`test_guard_setting_is_not_false_positive_on_real_repo`（在真实 `config.py` 上复核）。

### 8.3 G-19 决策点 1 采纳 (a)

新增 `test_g19_own_image_tags_track_app_version`：凡**声明了 `build:`**（即本仓库构建）
的服务，其 image tag 必须等于当前 `app_version`；第三方镜像（neo4j / postgres）无
`build:`，不参与。

**负向验证（不做这些测试就不算数）**：把 compose 的 backend tag 临时改成 `1.5.9`
⇒ 该用例 **FAIL**；改回 `1.6.0` ⇒ PASS。compose 与测试文件里「此缺口无人管」的旧注释
已同步更正。

### 8.4 `check_session_drift.py` 的批次识别

- 目录 glob 由 `changes/Sprint*` 扩为 `("changes/Sprint*", "changes/P*")`
  —— 否则 `changes/P1/` 永远匹配不到；
- 「最近批次」的判据由**目录 mtime** 改为**目录 + 其下 `*.md` 的最大 mtime**
  —— 目录 mtime 只在文件**增删**时变，改既有 md 不变 ⇒ 一直在推进的批次会被判成不活跃；
- 批次内多份 md 都有边界节时 **`proposal.md` 优先**（纯按文件名排序会先命中
  `integration-log.md` ⇒ 对照的是二手边界）。

**实测**：修复前 S1 报 `Sprint10.5/proposal.md`（5 条边界）⇒ 修复后报
`changes/P1/proposal.md`（**9 条**边界）。
