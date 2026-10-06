# P6-P1 · 清偿三项遗留（**R28** 本地有图口径 / **R29** `users` 主体锚点 / **Sprint10.5** 处置）

> **日期**：2026-10-06 ｜ **上游**：`changes/P6-P0/`（users 缺口量化，已结）
> **关联**：DR-B13（`users` 主体）/ DR-C1 / G-23（License，下游）/ DR-B4 / DR-B8（G-26 RLS）
> **定位**：**清偿遗留**，不是新功能 —— 把「开放（已登记未处理）」的两条 + 一个悬空批次收成有结论的状态
> ⚠️ **草案**（2026-10-06 由执行代理起草），每条都带实测坐标

---

## 1. 为什么做（三项遗留的 Triage 结论，**只读实测**）

| 项 | 依据 | Triage 结论 |
|---|---|---|
| **R28** 本地有图口径与 CI 不等价 | `dev-doc-status.md` §8 R28 行 | ⚠️ **已被环境自愈大半**：本地 `app_rls` / `app_owner` 已存在（`rolbypassrls = f`）、`graphrag_test` 库已存在、**本地 pytest 已是受限角色口径**（`test_g26_1/3/4` 单独跑 **6 passed**）⇒ **P6-O 推断的「需中和 `.env`」被推翻**。剩两件事：① 本地 Neo4j 口令 ≠ CI 的 `ci-graph-pw-2026`（实测 `cypher-shell` 认证失败）；② 本地图未导入 `affiliation-demo-v2` 受控语料 |
| **R29** `users` 有表无主体 | `dev-doc-status.md` §8 R29 行 | 其**既定处置**就是要做的事 —— 该行明写「下一步坐标见 `P6-P0` §3.2 ⇒ **P6-P1 先补主体锚点**」⇒ 「收 R29」= **执行 users 主体锚点方案** |
| **Sprint10.5** 归档？ | `delivery-plan.md:198` | **文档已有既定处置**：「D4 承接 `changes/Sprint10.5/` **并改指本阶段编号**」⇒ **不归档**（归档会让 P5 失去承接对象）。且它带一笔**未了债务**：演示库被不可逆改动，`G3` 受控题集**必须重跑**（`changes/Sprint10.5/proposal.md:16-19`），该债务**不在任何 CI 门禁里** ⇒ 本批**只登记** |

⇒ **本批要回答的唯一问题**：遗留能不能用**零 / 极小改动**闭环，而不是再开一个"顺手做"的口子。

## 2. 三项怎么收

### 2.1 R28（零代码，纯环境）

>证据链：`postgres:16-alpine` / `neo4j:5.26-community`（**与 `deploy/docker-compose.yml` 同 tag**）本地 Up 8h；
`test_guardrails_graph.py:99-117` 的 tag / 口令比对**只盯 CI 声明**（不约束本地口令）⇒ 本地可自由用本机口令。

步骤（幂等、可回滚）：
1. 注入 `GRAPH_REAL_NEO4J_URI/USER/PASSWORD`（口令取**本地** `.env` 的 `NEO4J_PASSWORD`）；
2. 导入受控语料：`scripts/ingest_affiliation_sources.py --purge --corpus-dir ../demo/affiliation/generated --kg-version affiliation-demo-v2`
   —— ⚠️ **`--purge` 安全**：`ingest_affiliation_sources.py:1172` 只删 `kg_version` 匹配的节点，**不碰**本地演示图（`attendance-demo-v1` 等）；
3. 跑全量 ⇒ **期望 `997 passed / 5 skipped / 2 xfailed / 0 failed`**（= CI 口径）。

⚠️ **不能做一半**：只注入 env 而不导语料 ⇒ G-25 3 条 + sentinel 1 条 + G-9 1 条会从 **skip 转 fail**
（`test_guardrails_graph.py:136-141`、`test_evidence_window_sentinel.py:327-341` 的 skip/fail 语义）。

### 2.2 R29（= P6-P0 §3.2 的最小真接线）

照 `changes/P6-P0/integration-log.md` §3.2 执行，**三条边界不动**：
- 造的第一条 user **主键 = `DEFAULT_ACTOR_ID`**（`app/core/config.py:27`）⇒ `user_roles` 孤儿 **2→0**、`documents` 33 行脱孤，**零业务代码改动**；
- **注册端点 / schema / 注册流程一律不做**（命中 ⇒ 按 P6-P0 的 P0-D4 停下升级）；
- `activated_at` / `disabled_at` **不预置**（`ADR-0006:123`：MVP 内只有 License 一处消费者）⇒ 随 **P4** 同批补。

### 2.3 Sprint10.5（只登记，不动目录）

在 `dev-doc-status.md` 补一条：冻结中 / 归 **P5-D4** 承接 / **未了债务 = `G3` 受控题集须重跑**，并指出该债务无门禁兜。

## 3. 决策点（文档已有建议 ⇒ 无人值守下默认采纳）

| # | 决策 | 采纳 | 依据 |
|---|---|---|---|
| **P1-D1** | R28 修法 | **不写代码、不改 `.env`、不改 CI** —— 只用「注入本地口令 env + 导入受控语料」两件环境动作补齐，达成 997 口径闭环 | subagent triage (C)：纯环境配置；且实测 pytest **已在受限口径**（`g26_1/3/4` 6 passed）⇒ 无需中和 `.env` |
| **P1-D2** | Sprint10.5 | **不归档**，只登记 | `delivery-plan.md:198` 既定处置 = P5 承接 |
| **P1-D3** | R29 的 users 怎么造 | **seed 脚本**（不是端点 / SSO） | P6-P0 §3.2 已定 |
| **P1-D4** | 命中「需新建端点 / schema / 注册流程」 | **升级用户**，不自行开工 | P6-P0 的 P0-D4 |

## 4. Non-goals（**编号列表**，S1 必须读到）

1. **不改 `contracts/openapi.yaml`**（`test_guardrails.py:281-284` 断言守着）
2. **不新增或修改 `settings.*` 配置项**
3. **不新建端点 / schema / 注册流程**（`/auth/register` 之类 ⇒ 属新批次，按 P1-D4 升级）
4. **不动认证链路**（`LocalAuthProvider` / `core/auth.py` / RBAC 取角色逻辑）
5. **不改 `ci.yml`、不新增 CI job**
6. **不修改本地 `backend/.env`**（实测 pytest 已在受限角色口径，动了反而引入未知）
7. **不动 RLS 政策 / 迁移**
8. **不摘任何 `xfail`**（G-23 仍挂起，R-9「先建真子系统再摘标记」）
9. **不预置 `users.activated_at` / `disabled_at`**（属 P4 License 同批）
10. **不归档 Sprint10.5**（`delivery-plan.md:198` 既定 = P5 承接）
11. **不顺手修其它遗留登记** —— 含新发现的 `ci.yml:280` 笔误（`POSTGRES_DB=graphrag` 应为 `graphrag_test`）：**只登记不修**
12. **不得宣称「账号体系已落地」** —— `users` 补了行也仍是 **0 真实读者**

## 5. 任务

- **T1** R28 闭环（零代码）：注入本地口令 env → 导入 `affiliation-demo-v2` 语料（`--purge`）→ 跑全量 ⇒ **997 passed / 5 skipped / 2 xfailed**
- **T2** R29 闭环：seed 造第一条 user（主键 = `DEFAULT_ACTOR_ID`）→ `user_roles` 孤儿 **2→0** → 消费模块登记进 `USERS_CONSUMER_MODULES`（`test_guardrails.py:231`）并交代 `:243-248` 四件事
- **T3** Sprint10.5：在 `dev-doc-status.md` 登记「不归档 / 归 P5-D4 承接 / 未了债务 `G3`」；R28 / R29 两条由「开放」改为**已闭环**，写入实测命令与用途证据
- **T4** 回切点（`check_session_drift.py`，S1 须读到 **12 条**）+ 门禁全绿（契约 zero diff ／ pytest 不减 ／ ruff ／ `check_seams` ERROR 0）
- **T5** 提交（Conventional Commits）+ CI 实证回登

## 6. 验收判据（全机械）

| # | 判据 |
|---|---|
| ① | **有图口径**：本地全量 **0 failed**，且原 8 条旧红全部转通过 —— 计划目标写作 `997 passed / 5 skipped`（= CI 口径）**作为下界**；实测因本地独占两个资产（`bridge_web_demo/output.json` / MinerU 产物在 CI 上缺失）多跑通 2 条 ⇒ **999 passed / 3 skipped / 2 xfailed**，collected 数与 CI 同为 1002（详见 log §4） |
| ② | R29：`users` 行数 ≥ **1**；`user_roles` 孤儿 = **0**；`app/` 下 `\bUser\b` 命中 ⊆ `USERS_CONSUMER_MODULES`（双向一致） |
| ③ | 零 ⇒ 契约 **zero diff**、无图口径 `pytest` **991 passed 不减**、`ruff check` + `ruff format --check`、`check_seams` **ERROR 0** |
| ④ | `check_session_drift.py` 的 S1 读到 **12 条** Non-goals |
| ⑤ | 三项遗留状态在 `dev-doc-status.md` §8 由「开放」改为**闭环 / 保留并注明依据**，每条带 commit / 命令证据 |

## 7. 状态

- **草案**（2026-10-06）｜ 关联：`docs/dev-doc-status.md` §8 **R28 / R29**、`delivery-plan.md:198`、`changes/P6-P0/integration-log.md` §3.2
