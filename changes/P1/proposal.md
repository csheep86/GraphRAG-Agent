# Proposal: P1 —— 交付骨架 + 数据底座

> 依据：[`docs/delivery-plan.md`](../../docs/delivery-plan.md) §3 / §4
>
> **定位**：事前计划；事后实测证据记同目录 `integration-log.md`，两者不可互相替代。
>
> **需求**：DR-A1 / A2 / A3 / A6（交付骨架）+ DR-B1 / B2 / B3（数据底座）。
>
> **起跑状态**（2026-10-01 `check_startup_readiness.py` 实测）：已生效 3 条（G-11 / G-15 / G-17）、部分生效 3 条、挂起 9 条、开工地雷 6 项。
>
> **冻结的在途批次**：`changes/P6-U/`（已冻结，移交 P5 / D4，本阶段不接）。

---

## 1. 开工前可行性核查（2026-10-01）

**本节的结论已经改写了下面的批次表。排期时不查这一类东西，写出来的就是一张不可执行的表。**

### 1.1 逐项结果

| 批次 | 核查项 | 结果 | 证据 |
|---|---|---|---|
| B | PG 驱动是否就位 | **缺失** | `backend/pyproject.toml` 主依赖 15 项无 psycopg；`uv.lock` 搜 psycopg / asyncpg 为空 |
| B | 是否需要向量扩展 | 不需要 | 全 backend 搜 pgvector / JSONB / ARRAY 为空，可用裸 `postgres:16.x` |
| A | G-19 断言什么 | 每个 service 须有 `image:`，且 tag 非 `latest` / 缺省 | `test_guardrails_delivery.py:136-171` |
| A | neo4j 是否已合规 | 已是 `neo4j:5.26-community` | `docker-compose.yml:29`，缺口只在 backend / frontend |
| A | tag 与版本号是否联动 | **不联动** | `app_version = "1.6.0"` 硬编码于 `config.py:92`，G-19 不校验两者一致 |
| C | CI 有无 PG service | **无任何 services 块** | `ci.yml` 搜不到 services 或 postgres |
| C | CI 依赖安装模式 | `uv sync --all-groups --frozen` | 加依赖必须同步 `uv.lock`，否则 CI 红 |
| D | G-21 查哪几处 | 5 条判据 | `test_guardrails_db.py:103-140` |
| D | 当前命中位置 | `session.py:23-25` / `config.py:96` / `.env.example` / `app/db/__init__.py:1` | 同上 |
| E | G-12 能否达成 | 不能 | 启用条件写死 variant ≥ 2，当前 0 个 |
| E | G-22 需要的字段 | id / version / entry_point / seam / base_version | `test_guardrails_delivery.py:25` |
| -- | G-11 是否真没做 | **已达成** | 自检已生效，测试与快照均已入库 |

### 1.2 暴露的三个问题

**① 缺第一步。** `delivery-plan.md` §4 从「DR-B1：compose 加 PG 服务」起排，但**驱动根本没装**。
先把 `database_url` 改成 `postgresql://…`，第一步就是 `ModuleNotFoundError`。原表少了这一项。

**② DR-B1 与 DR-B3 是同一批代码，不该分成两批。**
`config.py:96` 那一行既满足 G-20 的「默认值须为 postgresql」，又是 G-21 的判据之一；
`session.py:23-25` 删掉 check_same_thread 是切 PG 的必然结果，也正是 G-21 判据；
`.env.example` 同为两者共用。
分两批等于同一行改两次、两次 review、两次 CI。**合并**。

**③ P1-A 能转正，但可能只是假防御。** 详见 §3.1。

### 1.3 修正对照

| 原计划（delivery-plan.md §4） | 修正后 | 原因 |
|---|---|---|
| （无） | **新增 P1-0 装 PG 驱动** | 硬阻塞 |
| 第 2 项 DR-B1 与 第 4 项 DR-B3 | **合并为 P1-B** | 同一批代码 |
| 第 8 项 G-11 接缝签名快照 | **划掉** | 已生效 |
| 第 6 项 DR-A1 出口含 G-12 | 出口**不含** G-12 | 需 ≥2 变体，本阶段至多 1 个 |

---

## 2. Why

交付能力是**签单路径的前置**，当前形态两件事都做不到：

1. **客户拿不到可升级的东西** —— compose 的 backend / frontend 只有 `build:`、没有 `image:`
   ⇒ 现场无法 pull 升级、也无法改 tag 回滚 ⇒ 离线包（DR-A7）与补丁流程（DR-C2）都不存在（G-19）。
2. **数据底座撑不住隔离** —— 默认库是 SQLite（`config.py:96`），不支持 RLS，
   后续全部租户隔离断言（G-9 / G-10）在其上都无意义（G-20）。

经济账：切 PG 越晚，方言债越多（Uuid 无连字符格式已踩过一次；当前 `test_guardrails_db.py` 有 29 处 sqlite 引用，测试基建本身也建在 SQLite 上）。

---

## 3. What Changes

单人执行顺序（A 与 P1-0 均极低成本、互不依赖；A 先行是因它解锁签单路径）：

| 序 | 批次 | 动作 | 出口判据 |
|---|---|---|---|
| 1 | **P1-A**：DR-A6 版本化镜像 | compose 的 backend / frontend 补 `image:` + 固定 tag | G-19 转正 |
| 2 | **P1-0**：PG 驱动 | `pyproject.toml` 加 psycopg，并同步更新 `uv.lock` | 可导入 且 CI 的 uv sync --frozen 不红 |
| 3 | **P1-B**：DR-B1 + DR-B3（合并） | ① `config.py:96` 默认改 PG ② `.env.example` 同步 ③ `session.py:23-25` 删方言特判 ④ `app/db/__init__.py:1` 口径更正 ⑤ compose 加 PG 服务（固定 tag，G-20 也查） ⑥ 删 `sqlite_data` 卷 | **G-20 + G-21 同时转正** |
| 4 | **P1-C**：DR-B2 / G-8 | ci.yml 加 postgres service + DATABASE_URL | G-8 转正 |
| 5 | **P1-E1**：DR-A2 | `plugins/<id>/plugin.yaml`，最小五字段 | 解除 G-22 恒绿失效 |
| 6 | **P1-E2**：DR-A1 | `deploy/variants/<客户>.yaml` | 仅让 G-12 非空转；因需 ≥2 变体，**仍挂起** |
| 7 | **P1-E3**：DR-A3 | Dockerfile 构建期烘焙 | -- |
| 8 | **P1-F**：G-14 | 随首个插件并入并启用 | G-14 转正 |

**P1-B 的顺序不能反**：先把 backend 改成连 PG 并**本地跑通** `create_all`，再改 compose。
反过来会得到「一个没有任何应用连接的 PG 服务」——正是当年裁决 D-L 要防的假组件（该裁决已被 DR-B1 推翻，但其判据仍成立）。

**P1-B 中不得删除的东西**：`config.py` 的 `_guard_production_sqlite`（生产禁 SQLite）。
它长得像残留，实则是 G-21 **反向守卫**的唯一依托，删它等于拆护栏。

### 3.1 P1-A 的假防御缺口（待裁决，见 §6 决策点 1）

G-19 只校验「有无 `image:`」+「tag 非 `latest` / 缺省」。
而 `app_version = "1.6.0"` 是**硬编码**的，与 compose 里的 tag **没有任何关联**。

现在填 `:1.6.0` 能立刻转正；半年后 bump 到 `1.7.0` 而 compose 忘了改，G-19 依然绿。
护栏会在它最该响的时候沉默。

---

## 4. Impact

**契约（`contracts/openapi.yaml`）** —— 无。
注意：G-15 补丁期契约冻结已生效，版本号第三位变更必须保证契约零 diff。

**前端（`frontend/`）** —— 无直接改动；但 compose 的 frontend 服务需补 `image:` + tag（P1-A）。

**后端（`backend/`）**

- `app/core/config.py`：默认 `database_url` 改 PG；`_guard_production_sqlite` **保留**
- `app/db/session.py`：删 SQLite 方言特判
- `app/db/__init__.py` / `app/schemas/health.py`：口径文字（后者「SQLite 兜底期间」的字段描述不在 G-21 扫描范围内，但属同类漂移，顺手订正）
- `app/core/config.py:95` 注释「Sprint 1 临时兜底」同上
- `pyproject.toml` + `uv.lock`：新增 psycopg

**Prompt** —— 无。

**测试基建（工作量不可精确预估，需缓冲）**

`test_guardrails_db.py`（29 处）/ `test_migrations_baseline.py`（4 处）/ `conftest.py` 均建立在 SQLite 之上，切 PG 时需同步迁移。

**基础设施** —— `deploy/docker-compose.yml`（加 PG、删 `sqlite_data`）、`.github/workflows/ci.yml`（加 postgres service）。

---

## 5. Non-goals

`check_session_drift.py` 会逐条读本节做会话漂移对照，改本节即改边界。

- **不做** RLS（DR-B4）/ T1 跨租户越权（DR-B6）/ T2 并发串租户（DR-B7）—— 归 P3
- **不做** `users` 表（DR-B13）/ RBAC 三粒度（DR-B9）/ SSO（DR-D9）—— 归 P2
- **不做** License 子系统（DR-C1）—— 归 P4
- **不做** 插件**运行期动态装配** —— 本阶段止于构建期烘焙（DR-A3）
- **不做** `deploy/variants` 矩阵构建（G-12）—— 启用条件为 ≥2 变体，本阶段至多 1 个，**不为其凑第二个客户变体**
- **不做** 离线镜像包（DR-A7 已降级 P2）
- **不做** 插件契约分片合并（DR-A4，已废）/ 动态表单引擎（DR-A5，已降级）
- **不做** M6 / 时效 / Sprint10.5 遗留 —— 归 P5
- **不回退** 切 PG 后暴露的任何 SQLite 缺陷（见下方 RK-2）

---

## 6. 风险与待裁决点

### RK-2（已知且已在基线段裁决）—— 切 PG 暴露缺陷

ADR-0003 §3.6.2 已声明为**预期代价**。本节给出**具体预测项**，便于提前预留缓冲：

- `test_guardrails_db.py` 有 **29 处** sqlite 引用（护栏自身建立在 SQLite 上）
- `test_migrations_baseline.py` 有 **4 处**（迁移等价性是在 SQLite 上验证的）

处置：**不得以「以前都好好的」为由回退**。

### RK-3 —— 只有 1 个客户时定插件规范

规范只定**最小字段集**（已裁决），不提前猜测后续客户需求。

### 决策点 1（需你裁决）：要不要为 G-19 补 tag 一致性断言？

| 选项 | 做法 | 评价 |
|---|---|---|
| (a) 补断言 | 加一条 tag 与 `app_version` 一致的检查（约 10 行） | **推荐** —— 防的是已确知的漂移，成本极低 |
| (b) 不补，登记缺口 | 靠 release checklist 人工盯 | 可接受，但依赖人记得住 |
| (c) tag 抽成变量与 config 联动 | 引入构建期耦合 | 不推荐，属过度设计 |

> ✅ **裁决（2026-10-01，用户确认采纳建议）**：**选 (a)**。
> 已落地 `test_g19_own_image_tags_track_app_version`（有 `build:` 的服务，tag 必须等于
> `app_version`；第三方镜像无 `build:` 不参与），**负向验证已做**（tag 改错 ⇒ FAIL）。
> 联动**仍**是手工的——但漏改不再沉默。

### 决策点 2：P1-E 组是否本阶段做？

E（插件交付形态）在 `delivery-plan.md` 中属 P1，但**当前插件数为 0、变体数为 0**，做完仍无法让 G-12 转正。
若优先解锁签单，可先把 E 组整批推到后续，只保留 A / B / C。

> ✅ **裁决（2026-10-01，用户确认采纳建议）**：**E1 / E2 / E3 / F 整批推到 P2 之后**
> （记为 `P2.5`），本阶段只保留 A / 0 / B / C。理由（实测支撑）：
>
> 1. **做完也转不了正** —— G-12 启用条件写死 `variant ≥ 2`，而本阶段至多 1 个客户，
>    且不为它凑第二个客户；G-22 的守卫条 `test_g14_customer_token_source_exists`
>    同理要在变体落地后才可能解除恒绿失效。
> 2. **投人力到 `users` 表收益更高** —— 实测 ORM 里 12 张表**没有 `users`**（RK-1 正是
>    预警这个）。`users` 是 SSO / RBAC / License 席位的**共同前置**，先做它能同时解锁
>    签单路径与 P4；而 E 组在插件数为 0 时既转不了正、也无法验证。
> 3. "签单优先"是重排原则第 1 条，两者排序由此确定。
