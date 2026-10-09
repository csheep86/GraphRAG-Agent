# P6-V2 开工提示词（写给下一批，2026-10-09 由 P6-V1 落成）

> 队列活版口径：[`docs/delivery-plan.md` §9.2 序 5c](../../docs/delivery-plan.md)；
> 上一批收口：[`integration-log.md`](./integration-log.md)

---

## 1. 执行模式

**无人值守**，默认采纳本文档的建议项；只有 §11 那四类情况停下来升级用户。
跨角色严格隔离：`backend/` 归后端、`specs/` 与 `contracts/` 归架构师、`frontend/`
**本批一行不动**（除非 X-5 由用户点名要改）。

## 2. 为什么起点是 P6-V2（三条**机械**理由，不是"顺序到了"）

1. **队列口径**：`delivery-plan.md` §9.2 序 **5c** 写明 **P6-V2 = M2 抽取侧 token 落点 +
   `stage` 列**（偏离 **X-6**），前置 = P6-V1；P6-V1 已收口并提交（三个提交，
   详见本目录 `integration-log.md` §1 / §7）。
2. **它是 C3-a 的第二个前提**：`cost_metrics` 有表、但**只有 M3 问答在写** ⇒
   `single_doc_cost` 的分母只统计问答侧文档，抽取侧从未计数 ⇒ **C3-a 尚无真实分母**
   （P6-V 已登记"有表 ≠ 有分母"）。
3. **工量已被机械查实为小改**（见 §5，不是照抄文档）：写库**只有 1 处**
   （`registry.py:487` `_do_extract`，db / org_id / document_id 齐全）；
   真正的工量在**把 usage 从日志层提到结构化返回值**（`langextract.py:296`
   类型契约 + `:390-400` 调用处 + `:403` 取值），外加 **3 个测试替身**签名。

## 3. 开工自检（先跑，别凭文档下结论）

```bash
cd backend && uv run python scripts/check_startup_readiness.py   # 期望 17/0/0
cd backend && uv run python scripts/check_seams.py               # 期望 ERROR 0 / WARN 0 / OK 12
cd backend && uv run python scripts/export_openapi.py --check     # 期望零 diff
```

三个都对上才开始。**结论只能来自脚本输出**，不能来自本篇或集成日志的表格。

## 4. 边界纪律（Non-goals **≥ 8 条**，落 `changes/P6-V2/proposal.md`）

（下面这几条至少都要覆盖；不许删根，只准加）

1. **AI 不得代填任何 `correct` 值**（A3）——永久红线。
2. **不动 P6-V1 的成果**：排序口径两侧登记（`PATH_SORT_DIMENSIONS` /
   `DB_ORDER_BY_DIMENSIONS`）与真图 401 候选对照，不得为了落 token 改排序。
3. **不改 rubric / 题集 / 判分**（P6-T 仍 `UNKNOWN`，人是瓶颈）。
4. **不改 `frontend/`**（除非用户点名要一并修 X-5）。
5. **不改契约** —— `export_openapi.py --check` 零 diff 为判据；**包括描述文本**。
6. **不夹带**：不许把 C3-b 取证（P6-V3）、跨版本边（P5H-6）、
   `fetch_evidence_chunks` 继承读并进来 —— 各自有批次。
7. **不许"只加列不改去重"**：`stage` 一加，**一行 = 一个租户一天**的口径就变了
   ⇒ 必须同时交代 `counted_doc_ids` 的归属（按 stage 各存一份，还是合并），
   否则 `doc_count` 会在两侧口径间互相污染（这正是 X-6 要防的）。
8. **不改 `docs/sprint-calendar.md` 的方针**。
9. **不为了落点改抽取行为**：usage 只**旁路带出**，不得改变任何一档引擎的
   抽取结果（`mock` 档仍不得调 LLM）。

## 5. 已查证坐标（**2026-10-09 由 P6-V1 实读，但仍请先自己复核一遍** —— 本篇会过期）

| 坐标 | 位置 | 备注 |
|---|---|---|
| 写库唯一处 | `backend/app/tasks/registry.py:487` `_do_extract` | db / org_id / document_id **齐全** |
| 类型契约 | `backend/app/services/extraction/langextract.py:296` `LlmInvokerFn = Callable[[str], str]` | 当前**只返回 str** ⇒ token 无处可带 |
| 调用处 | 同文件 `:390-400`（`return str(response.content)`，`:397` 只把 usage 打进日志） | usage 目前在**日志层** |
| usage 取值 | 同文件 `:403` `_extract_token_usage` | 已存在，可取来复用（**不要**另写一份） |
| 测试替身 | `tests/test_extraction_llm_engine.py:79`、`tests/test_extraction_sprint71.py:86`、`tests/test_extraction_temporal.py:71` | **共 3 个**，改签名会一起红 |
| 表形状 | `backend/app/db/models.py:1084` `CostMetric` | ⚠️ **无 `stage` 列**；唯一约束当前是 `UNIQUE (org_id, metric_date)` |
| 队列定义 | `docs/delivery-plan.md` §9.2 序 5c | 编号 / 前置 / 判据 4 条 |
| 偏离登记 | `specs/m6-ontology-incremental.md` §10.1.1（X-6 行） | 2026-10-09 用户已裁决，**收口时以该文件为准** |

⚠️ **唯一约束是本批最容易漏的一处**：加了 `stage` 之后「一天一行」变成「一天 ×
每个 stage 一行」⇒ `UniqueConstraint("org_id", "metric_date")` 必须一并处理，
否则第二次写同日不同 stage 会撞唯一键（症状是抽取侧静默写不进去）。

## 6. 决策表（默认采纳；要改请在 `proposal.md` 登记）

| # | 决策 | 建议 |
|---|---|---|
| **Y1** | `LlmInvokerFn` 怎么带出 usage | **建议改成 `Callable[[str], tuple[str, dict[str, int \| None]]]`**（原文 + usage 一起返回），而不是"调用后回查日志"——回查日志等于把结构化数据从日志里再解析一遍 |
| **Y2** | `usage` 取不到时怎么办 | **保持 `_extract_token_usage` 的 `None` 语义**：取不到就记 0 并打点，**严禁造数**（沿用 A15） |
| **Y3** | `stage` 取值集合 | 只落 **抽取 / 问答** 两档（X-6 的最低集合）；不要在未裁决前扩到"增量重算" |
| **Y4** | `counted_doc_ids` 去重 | **按 stage 各存一份**（抽取侧记抽取文档、问答侧记问答文档）⇒ 两侧 `doc_count` 不互相污染 |
| **Y5** | 判据进不进 CI | 进（纯函数 + PG，不需要 live LLM；真 LLM 那条沿用 D6 不进 CI） |

## 7. 已完成项（不许重做）

- P6-V1：两侧排序口径登记 + 真图 401 候选对照（`pytest` 1167 → **1173**）。
- P6-V：ADR-0008 §7 **7/7 读路径**已切继承读；`cost_metrics` 表 + RLS 迁移 + 端点真实现。
- ⚠️ **C3-a / C3-b 仍 BLOCKED**：本批只解 C3-a 的**第二个前提**（M2 侧落点），
  **不许因为有第二处落点就宣称 C3-a 出数**（阈值 TBD-7 仍未拍板）。

## 8. 基线（动工前自己重跑一次现行值，本篇数字会过期）

- pytest（有图口径）：**1173 passed / 5 skipped**
  （env 见 `integration-log.md` §6 —— **三个变量都要设**，少设 `USER` 会静默 skip 两条）
- CI 起跑点：P6-V1 收口 run —— **以 CI 页面最新绿 run 为准，别照抄本篇**
- 本地容器：`graphrag-postgres` / `graphrag-neo` 双 Up

## 9. 验收判据（每条都要能贴机器输出）

1. `registry.py:487` `_do_extract` 把 usage **写进 `cost_metrics`**（写库**仅此 1 处**）
   的用例 + 实际读数；
2. **`stage` 列**落地 + 迁移 + `UNIQUE` 约束同步处理的用例（同一文档两次抽取
   **不重复计数**，复用 `counted_doc_ids`）；
3. 3 个测试替身签名同步、且 `mock` 档**仍不调 LLM**（A15 反向守卫）；
4. `pytest` **不降**（≥ 1173 passed）；
5. `ruff` / `check_seams` / `export_openapi --check` / `check_startup_readiness` 四项读数不变；
6. 回登：`changes/P6-V2/integration-log.md` + `specs/m6-ontology-incremental.md`
   §10.1.1 的 X-6 行（**编号不重排**，守 R-5）。

## 10. 提交 / 推送纪律

- 每步一个 Conventional Commit；**代码 / 测试 / 文档分列**，不混提交；`main` 直推。
- 推送后以 **CI 四 job 全绿**为收口；红了的第一种反应是**看是不是批次摊太大**，
  不是先改测试让它绿（R-10：CI 才是门禁）。
- 收口时把实测证据固化进 `changes/P6-V2/integration-log.md`，再写
  `changes/P6-V2/new-session-prompt.md`（**提示词一律落成 MD 文件，不在聊天里贴全文**）。

## 11. 升级用户的四类情况

1. **判据本身有争议**（例："抽取侧 token 算不算单文档成本"spec 没定义）⇒ 停下来问。
2. **必须改契约**才能落 ⇒ 停下来（含 X-5 的描述文本）。
3. **边界冲突**：发现更有价值但落在 Non-goals 之外的东西 ⇒ **先缩范围登记下来、再报告**，
   不许硬做完再说。
4. **AI 无法自行判断的取舍**（例：唯一约束要不要按 stage 拆、去重清单归谁）⇒ 问。

## 12. 不许外推

- "usage 打进日志了" ≠ "token 已落库"；没有写库读数就不许写"落点已通"。
- "加了 `stage` 列" ≠ "C3-a 出数"：阈值 **TBD-7 未拍板**，本批结束仍不得宣称达标。
- 别把验收写成"截图 / 人工确认"——本批判据必须能 `pytest` 复跑复现。

## 13. 下一批指针（收口时按**实际结果**改，别照抄）

1. **P6-T 判分 86 题**：**必须传承到每一批**，直到完成（P8-Release 零缺口对账前判完）。
2. **P6-V3**（序 5d）：C3-b 取证 —— `full_rebuild_cost` 取**首次全量构建**（偏离 **X-7**，
   方案 B2），**不许**新建全量重建入口（会撞 `incremental.py:17-18`「失败绝不回落全量」护栏）。
   ⚠️ **仍卡在同一个未决前提**：增量重算零 LLM ⇒ token 口径下分子恒 ≈ 0 ⇒
   `cost_ratio` 会假性"显著 < 1.00"。**在"耗时 / 图写操作数 / 受影响节点数"定案前
   不得开工、不得宣称达标** —— 这一条要一直传到用户裁决为止。
3. **P6-W**（DR-E4 安装验收十项脚本化，需目标环境）→ **P6-X**（演练留证，
   **独立环境 + 双人**，AI 不得单独收口）→ **P6-Y**（L2 端到端）→ **P7-B** →
   **P8-Release**（tag `v2.0.0`）。
4. **X-5** 契约描述文本更新（`cost/dashboard` 还写着"占位骨架 / 恒 501"）：
   跨角色任务，需 `export_openapi.py` + 前端 `npm run gen:api` 一起提。
