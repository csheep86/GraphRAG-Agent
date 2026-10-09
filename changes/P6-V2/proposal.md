# P6-V2：M2 抽取侧 token 落点 + `cost_metrics.stage` 列（偏离 X-6）

- **队列**：[`docs/delivery-plan.md` §9.2](../../docs/delivery-plan.md) 序 **5c**
- **前置**：P6-V1 已收口（HEAD `adc8ea2`，工作区干净），见
  [`changes/P6-V1/integration-log.md`](../P6-V1/integration-log.md)
- **状态**：进行中（2026-10-09 开工）
- **来源**：[`specs/m6-ontology-incremental.md`](../../specs/m6-ontology-incremental.md)
  §10.1.1 第 12 项 **X-6**（2026-10-09 用户裁决，先登记后实施）

---

## 1. 本批要做什么

`cost_metrics` 有表、但**只有 M3 问答在写** ⇒ `single_doc_cost` 的分子只有问答侧 token、
分母只有问答侧文档，**C3-a 没有真实口径**。本批补上另一半：

1. **把 usage 从日志层提到结构化返回值**：`LlmInvokerFn` 当前只返回 `str`，
   usage 只在 `_default_llm_invoke` 里 `logger.bind(...)` 打点 —— 结构化数据一旦
   进日志就拿不回来。改成返回 `(原文, usage)`（决策 **Y1**）；
2. **`registry.py:487` `_do_extract` 写 `cost_metrics`**（抽取侧写库**仅此 1 处**）；
3. **加 `stage` 列**（`extraction` / `answer`）并同步处理唯一约束 ——
   否则「一行 = 一个租户一天」的旧口径会让两侧 token 落进同一行，
   `single_doc_cost` 哪个口径都不是（这正是 **X-6** 要防的）；
4. **回登** `specs/m6-ontology-incremental.md` §10.1.1 的 X-6 行（**编号不重排**，守 R-5）。

## 2. Non-goals（10 条）

1. **AI 不得代填任何 `correct` 值**（A3）——永久红线。
2. **不动 P6-V1 的成果**：`PATH_SORT_DIMENSIONS` / `DB_ORDER_BY_DIMENSIONS` 两侧登记
   与真图 401 候选对照，不得为了落 token 改排序。
3. **不改 rubric / 题集 / 判分**（P6-T 仍 `UNKNOWN`，人是瓶颈）。
4. **不改 `frontend/`**（除非用户点名要一并修 X-5，那时才允许）。
5. **不改契约** —— `export_openapi.py --check` 零 diff 为判据；**包括描述文本**。
   ⇒「按 stage 切片的仪表盘参数」属**契约变更**，本批不做，**登记传承**（见 §6 残留 3）。
6. **不夹带**：不许把 C3-b 取证（P6-V3）、`full_rebuild_cost` / `incremental_cost`
   的任何写入方、跨版本边（P5H-6）并进来 —— 各自有批次。
7. **不许"只加列不改去重"**：`stage` 一加，行粒度从「一天一行」变成
   「一天 × 每个 stage 一行」⇒ `UniqueConstraint` 必须同步改（否则抽取侧静默写不进去），
   `counted_doc_ids` 的归属也必须同时交代（决策 **Y4**）。
8. **不为落点改抽取行为**：usage 只**旁路带出**，不得改变任何一档引擎的抽取结果
   （`mock` 档仍不得调 LLM，A15 反向守卫）。
9. **不因为有了第二处落点就宣称 C3-a 出数**：阈值 **TBD-7 未拍板**，本批结束仍记 BLOCKED。
10. **不改 `docs/sprint-calendar.md` 的方针**；不改 specs §4.3 表结构原文
    （只在 §10.1.1 状态表里追加本批结果）。

> ⚠️ 若实现中必须触碰某条 Non-goal ⇒ **先缩范围再报告**（哪份文档哪一行 / 改什么 / 为什么绕不过 / 试过的替代方案）。

## 3. 工量证据（2026-10-09 机械查实，**不是照抄提示词**）

| 项 | 查实结果 | 出处 |
|---|---|---|
| 抽取侧写库点 | **1 处**（`registry.py:487` `_do_extract`；db / org_id / document_id 齐全） | 实读 `registry.py:487-600` |
| usage 现状 | 在**日志层**：`langextract.py:397` `logger.bind(..._extract_token_usage(response))`，`:400` 只 `return str(response.content)` | 实读 |
| 类型契约 | `langextract.py:296` `LlmInvokerFn = Callable[[str], str]` | 实读 |
| `ExtractionResult` | `@dataclass(frozen=True, slots=True)`，**非对话即 artifacts**：`to_json_dict()` 决定落盘形状 ⇒ 新增字段**不得**进 `to_json_dict` | 实读 `:226-252` |
| `CostMetric` | 无 `stage` 列；`UniqueConstraint("org_id", "metric_date", name="uq_cost_metrics_org_date")` | 实读 `models.py:1108-1118` |
| 迁移链 head | `df5ec5c9e1b1`（cost_metrics 建表 + RLS）⇒ 新迁移 `down_revision` = 它 | `uv run alembic heads` |
| G-26 影响 | 租户表集合**不变**（改列不改表）⇒ `*_rls_*.py` 清单不动；新迁移文件名**刻意不**含 `_rls_`（避免被 glob 抓走） | 实读 `test_guardrails_rls.py:519-551` |
| 测试替身 | ⚠️ 提示词写「3 个」（https 标注型）：实查另有**多处**函数内联 `_invoke` 闭包返回 `str`（`test_extraction_llm_engine.py` / `test_extraction_sprint71.py` / `test_extraction_temporal.py`），**改签名后会一起红 ⇒ 机械修，不算扩散** | 实读三份测试 |

## 4. 决策表

| # | 决策 | 结论 |
|---|---|---|
| **Y1** | `LlmInvokerFn` 怎么带出 usage | 改成 `Callable[[str], tuple[str, dict[str, int \| None]]]]`（原文 + usage 一起返回），**不**事后回查日志——回查日志等于把结构化数据从日志里再解析一遍 |
| **Y2** | `usage` 取不到时 | 沿用 `_extract_token_usage` 的 `None` 语义：缺的那一项记 **0** 并打点，**严禁造数**（A15）；**整次抽取都没有 usage**（`mock` 档 / 注入抽取器）⇒ `ExtractionResult.llm_usage` 为空 dict ⇒ 调用方**跳过记帐**，不写 0 |
| **Y3** | `stage` 取值集合 | 只落 **`extraction` / `answer`** 两档（X-6 的最低集合），不预扩到"增量重算" |
| **Y4** | `counted_doc_ids` 去重归属 | **按 stage 各存一份**（行粒度天然隔离）⇒ 两侧 `doc_count` 不互相污染 |
| **Y5** | 判据进不进 CI | 进（纯函数 + PG，不需要 live LLM；真 LLM 那条沿用 D6 不进 CI） |
| **Y6** 🆕 | 区间聚合要不要跨 stage | **要跨**（spec §3.4 验收 8 的 `single_doc_cost` 是 M2+M3 合并口径），但**必须按文档 id 跨行去重** —— 同一份文档今天被抽一次、被问一次，两行各数一次 ⇒ 区间求和会把 `doc_count` 翻倍。这是**本批自己引入的口径风险**，不修就是假账，`build_dashboard` 里加 3 行去重（契约不动） |

## 5. 为什么「下午发生了什么」按 stage 拆，而仪表盘仍跨 stage

- **行**是单口径载体 ⇒  microscopy 时能看到「抽取多久少 token / 问答多少」；
- **区间视图**是另一方问题：契约里只有一个 `single_doc_cost`，本批不改契约（Non-goal 5）
  ⇒ 保持「跨 stage 求和」，但把 doc 去重提到跨行做（Y6）。
- 要真正分开看，得给 `GET /cost/dashboard` 增加 stage 参数 ⇒ **契约变更**，登记传承。

## 6. 残留风险（**不许被读成"C3-a 已出数"**）

1. **TBD-7 阈值未拍板** ⇒ C3-a 仍 `BLOCKED`，本批只补它的**第二个前提**（M2 侧落点）。
2. `incremental_cost` / `full_rebuild_cost` **仍无任何写入方** ⇒ `cost_ratio` 恒 0.0，
   C3-b 仍 `BLOCKED`（P6-V3）。
3. 仪表盘无 stage 切片（Non-goal 5），只能出混合口径 ⇒ 登记给后续批次。
4. 抽取失败的 chunk 已真实花掉的 token **记不到**（`_extract_chunk_tolerant` 只兜异常，
   拿不到失败调用的 usage）⇒ 分子偏保守，**不回填**（造数优于少记？否：不回填、只登记）。

## 7. 执行顺序（每步一个 Conventional Commit）

1. `langextract.py`：usage 结构化（`LlmInvokerFn` + 累加器 + `ExtractionResult.llm_usage`）
2. 测试替身签名同步（含内联闭包）；`mock` 档反向守卫
3. `models.py`：`stage` 列 + 唯一约束改 `(org_id, metric_date, stage)`
4. 迁移（含回填 + downgrade 语义）
5. `cost_metrics.py`：抽取侧写入入口 + `build_dashboard` 跨行 doc 去重（Y6）
6. `registry.py:487` 接线（唯一写库点，旁路不拖垮主链路）
7. 测试 + 回登 spec §10.1.1 + `integration-log.md`

## 8. 验收判据（每条要能贴机器输出）

1. `_do_extract` 把 usage 写进 `cost_metrics` 的用例 + 实际读数（写库**仅此 1 处**）；
2. `stage` 列 + 迁移 + `UNIQUE` 约束同步：同一 `(org, 日)` 两个 stage **并存不撞键**，
   且 `single_doc_cost` 两行各自成口径；
3. 同一文档两次抽取 **不重复计数**（复用 `counted_doc_ids`）；
4. 跨 stage 区间聚合的 `doc_count` **按文档 id 去重**（Y6）；
5. `mock` 档 `llm_usage` 为空 dict 且**不调 LLM**（A15）；
6. `pytest` **不降**（基线以动工前实测为准，提示词写 1173）；
7. `ruff check` / `ruff format --check` / `check_seams` / `export_openapi --check`
   / `check_startup_readiness` 五项读数不变；
8. 回登：`changes/P6-V2/integration-log.md` + spec §10.1.1 X-6 行（**编号不重排**）。
