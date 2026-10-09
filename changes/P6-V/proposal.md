# P6-V：M6 剩余读路径切版本继承读 + `agents.py` 接线 + `cost_metrics`

- **队列**：[`docs/delivery-plan.md` §9.2](../../docs/delivery-plan.md) 序 5（P5-J 并入）
- **前置**：P6-U 已收口，CI run **37916431340** 绿，`main` 直推
- **状态**：进行中（2026-10-09 开工）

---

## 1. 本批要做什么

把 ADR-0008 §7 表里剩下的 **7 条读路径**切到**版本继承读**（`build_read_view` / `version_scope`），
把 **`agents.py` 的检索**接上版本视野（⇒ M4 端到端问答才真吃到继承读），
并把 **`cost_metrics` 表 + 成本仪表盘**从 501 占位做成真实现（解开 C3-a / C3-b 的 `BLOCKED`）。

同批必做：回登 `docs/adr/ADR-0008-version-chain-read.md` §7 未切换清单（切一条勾一条）
+ `specs/m6-ontology-incremental.md` §10.1.1 落地状态表（**编号不重排**，守 R-5）。

## 2. Non-goals（10 条）

1. **AI 不得代填任何 `correct` 值**（A3 / delivery-plan §9.3 第 1 条）——永久红线。
2. **不改 rubric / 题集**（`rubric-v2` / `controlled-qset-v4` / `gold-multihop-v1` 题目一字不改）。
3. **不动 C2-a / C2-b / C2-c 口径**（三条已出数，A8 裁决）。
4. **不动前端**（`frontend/` 一行不改）。
5. **不动契约**：成本端点契约已先行 ⇒ 实现不得增删字段（`export_openapi.py --check` 零 diff 为判据）。
6. **不新裁决 ADR-0008 §7 的两个遗留语义**（统计口径 P5H-4 / 版本号长度）与 `parent_version` 列（指针 4）——只登记传承。
7. **不做多跳推理的 id 级图遍历**（ADR §7 指针 5）⇒ P5H-6 已知限制本批保留。
8. **不做 `alert` 表 + 限流超阈值联动**（P2，已连续多批有意不做）。
9. **不做 as-of 排序口径对齐**（`_cypher_paths()` DB/Py 两侧不一致）⇒ `P6-V1` 独立小批。
10. **写侧一行不改**：P5F-3（增量重写节点数 = 校正节点数）继续成立，本批不为了读侧好看把新版本写全。

> ⚠️ 若实现中必须触碰某条 Non-goal ⇒ **先缩范围再报告**（哪份文档哪一行 / 改什么 / 为什么绕不过 / 试过的替代方案）。

## 3. 工量证据（2026-10-09 机械查实，**不是照抄文档**）

| 项 | 查实结果 | 出处 |
|---|---|---|
| 未切换读路径条数 | **7 条**（ADR §7 表 7 行，不是 P5-J 提示词写的「六条」） | `docs/adr/ADR-0008-version-chain-read.md:112-121` |
| `cost_metrics` 表 | ❌ **不存在**（`models.py` 无 Cost 类）⇒ 建表 + 迁移 + RLS + 落点全要新做 | 实读 `models.py` |
| `GET /cost/dashboard` | 🟡 端点 + 契约已存在但恒 501 ⇒ 实现**不需要动契约** | `routes/cost.py:31-48`、`openapi.yaml:4145` |
| 新增租户表代价 | `cost_metrics` 带 `org_id` ⇒ 必须同步 `*_rls_*.py` 迁移清单，否则 G-26 `test_g26_migration_table_list_matches_metadata` 必红 | `tests/test_guardrails_rls.py:519` |
| 迁移目录 | `backend/migrations/versions`（**不是** `alembic/versions`） | 实读目录 |

## 4. 决策表（V6 为新增）

| # | 决策 | 结论 |
|---|---|---|
| **V1** | 7 条 + cost 是否一批做完 | **结论：没缩，全做了** —— 五个独立提交（读路径 / 异常 / 成本 / 文档 /  evaluator 订正）；drift S2 提示 1712 行（>600），已在 `integration-log.md` §8 第 4 条登记为"下次同体量要一开始就拆两批" |
| **V2** | `agents.py` 接线后 M4 端到端是否出数 | 出数依赖 live LLM ⇒ **判据不进 CI**（沿用 D6）；本地出数才贴输出，没出数就登记「未验」 |
| **V3** | `cost_metrics` 落点 | 表 + 迁移（含 RLS）+ 记录入口 + 聚合服务 + 路由 501→200；**预留字段不进契约** |
| **V4** | C3-a / C3-b 能否转 `MEASURED` | **不能**：阈值 **TBD-7 未拍板** ⇒ 本批只解 `BLOCKED`，**不宣称达标** |
| **V5** | ADR / spec 回登 | 切一条勾一条；编号不重排（R-5） |
| **V6** 🆕 | 成本配置 `COST_RATIO_ALERT_THRESHOLD` | spec §6 已定 `0.5`；落 `config.py` **必须**有消费者（告警分支），否则接缝门禁 「无消费者配置」 会拦 |

## 5. 执行顺序（每步一个 Conventional Commit，跨角色不混提交）

1. `agents.py` 检索接线（M4 端到端的开关）
2. `graphs.py`：`fetch_all_subgraph` / `fetch_entity_detail` / `fetch_anchor_entity_ids` / `fetch_document_subgraph`
3. `documents.py` 图谱读（把 `db` 会话传下去）
4. 考勤异常两条：`list_attendance_anomalies` / `explain_attendance_anomaly`（`rules/attribution.py` 全链路）
5. `cost_metrics` 表 + 迁移 + RLS
6. 成本落点 + 聚合服务 + 路由实现
7. 架构师段：ADR §7 清单 + spec §10.1.1 状态表回登

## 6. 验收判据（每条要能贴机器输出）

同 [`new-session-prompt.md`](./new-session-prompt.md) §8 七条：真图用例 / ADR 清单回登 / `agents.py` 口径证据 /
建表 + 迁移 / 端点真响应 + 护栏不倒退（pytest ≥ 1157、seams OK 12、readiness 17/0/0）/ CI 四 job 全绿。
