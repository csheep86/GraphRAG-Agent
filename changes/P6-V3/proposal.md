# P6-V3：`incremental_cost` / `full_rebuild_cost` 的唯一写入方（X-7 落地）

- **队列**：[`docs/delivery-plan.md` §9.2](../../docs/delivery-plan.md) 序 **5d**
- **前置**：P6-V2 已收口（五个提交，见
  [`changes/P6-V2/integration-log.md`](../P6-V2/integration-log.md)）
- **状态**：进行中（2026-10-10 开工）
- **来源**：[`specs/m6-ontology-incremental.md`](../../specs/m6-ontology-incremental.md)
  §10.1.1 **第 15 项**（2026-10-10 用户再裁决）
- **上一批交接**：[`changes/P6-V2/new-session-prompt.md`](../P6-V2/new-session-prompt.md)

---

## 1. 本批要做什么

`cost_metrics` 现在有**两个**写入方（M3 问答 + M2 抽取），但 `incremental_cost` /
`full_rebuild_cost` **仍无任何写入方** ⇒ `cost_ratio` 恒 `0.0`（探针实测，上一篇 §2 已核）。本批把这两列真正接上：

1. **分母**：文档**首次全量构建**写入的图元素个数（`entity_count + relation_count`），
   写库点在 `app/tasks/registry.py:810-815` 的 `mark_ready` 之后——**仅此 1 处**；
2. **分子**：**增量重算**写入的图元素个数，写库点在
   `app/services/kg/incremental.py:294-296` 的 `mark_ready` 之后——**仅此 1 处**；
3. 两侧共用 `app/services/cost_metrics.py` 的一个 `_record_graph_cost`，
   **同一个换算口**（`_graph_elements`）⇒ 量纲不可能各自漂移；
4. 回登 spec §10.1.1 第 15 项 + 更正 `delivery-plan.md` §9.2 序 5d 的过期前提
   （**用户 2026-10-10 同意一并在本裁决内更正**）。

**为什么是「图元素个数」而不是 token**（本次裁决的核心）：

| 事实 | 出处 |
|---|---|
| `services/kg/` 全目录搜 `build_chat_model` / `TokenUsage` / `invoke(` ⇒ **0 命中** | 开工前实读 |
| `registry.py:630`→`:700`→`:756-815`（全新构建真实路径）= 读 storage 的 `entities/relations/chunks.json` → `ThreeStageKgBuilder` 写图，**自身零 LLM** | 实读至 815 行 |
| `entity_resolution.py:12` / `temporal.py:5` 明写「零 LLM」「不调 LLM」 | 实读 |

⇒ **分子分母两侧都是零 LLM**：token 口径下分子恒 0、`cost_ratio` 会假性「显著 < 1.00」；
而 spec §10.1.1 第 12 项那条旧裁决（"全新构建分支已有真实 LLM 调用可量"）正是被这条
事实推翻的。耗时口径则需给 `KgVersion` 加列 + 迁移。⇒ 取**图元素个数**：两侧都已有列、
同为"个数"量纲、**零迁移、零新埋点**。

## 2. Non-goals（9 条）

1. **AI 不得代填任何 `correct` 值**（A3）——永久红线。
2. **不许新建全量重建入口**：X-7 的落地必须正面绕开
   `incremental.py:16-18`「失败显式失败、**绝不**静默回落全量」护栏。**硬边界，不是权衡**。
3. **不改写 C3-a / C3-b 的阈值**（TBD-7 未拍板；本批只让两侧能出数，**不宣称达标**）。
4. **不改 rubric / 题集 / 判分**（P6-T 仍 `UNKNOWN`，人是瓶颈）。
5. **不改 `frontend/`**；**不改契约** —— `export_openapi.py --check` 零 diff 为判据
   （含描述文本 ⇒ **X-5 不在本批**）。
6. **不动 P6-V2 的成果**：`stage` 列的两档取值集合、`UNIQUE (org_id, metric_date, stage)`、
   抽取侧唯一写库点、跨行 doc 去重 —— 本批**只在既有两档之上工作**，不引入第三档 stage。
7. **不夹带**：dashboard 的 stage 切片（契约变更）、X-5 描述文本、P5H-6 跨版本边
   —— 各自有批次。
8. **不为"出数"而虚构口径/垫数**：分子分母都来自真实 `mark_ready` 的计数；
   **零值一律跳过**（不写 0），不为凑出「显著 < 1.00」而垫数或回填。
9. **不改 `docs/sprint-calendar.md` 的方针**；不改 specs §4.3 表结构原文
   （只在 §10.1.1 状态表追加本批结果，**编号不重排**，守 R-5）。

> ⚠️ 若实现中必须触碰某条 Non-goal ⇒ **先缩范围再报告**（哪份文档哪一行 / 改什么 /
> 为什么绕不过 / 试过的替代方案）。

## 3. 工量证据（2026-10-10 机械查实）

| 项 | 查实结果 | 出处 |
|---|---|---|
| `incremental_cost` / `full_rebuild_cost` 写入方 | **0 个**：出现点仅迁移 `df5ec5c9e1b1:55-56`、模型 `models.py:1177-1178`、读数 `cost_metrics.py:344-347`、测试手工造数 `test_cost_metrics.py:140-142` | 全仓搜索 |
| 分母侧计数字段 | `KgVersion.entity_count` / `relation_count` **已有**（`models.py:293-294`），`mark_ready` 已在写 ⇒ **零迁移** | 实读 `versioning.py:129-151` |
| 分母侧"首次"怎么判定 | `registry.py:649-667` 三分支：`document.kg_version_id is None` 才走 `create_pending`（= **全新构建**）；其余两条是复用 ⇒ 重跑不是首次 | 实读 |
| 分子侧计数字段 | `IncrementalRebuildResult.entity_count/relation_count`（`incremental.py:139-140`）⇒ **零新埋点** | 实读 |
| 分子侧失败路径 | `_fail(...)` 返回的三个计数恒 0，版本行置 `failed` ⇒ **不记账**（不能写 0） | 实读 `:344-385` |
| 增量测试的图依赖 | `rebuild_incrementally(session_factory=...)` 可注入 ⇒ **不依赖真 Neo4j** 也能跑本批判据 | 实读 `_make_runner:565-582` |
| `cost_ratio` 列语义 | 模型注释（`models.py:1179`）=「无分母时为 0.0」；读数如此 ⇒ 行级也要维护，否则行读数与区间级不一致 | 实读 |

## 4. 决策表

| # | 决策 | 结论 |
|---|---|---|
| **Z1** | 分母 `full_rebuild_cost` | 首次全量构建的 `entity_count + relation_count`（**仅全新构建**时计入；复用 `kg_version` 的重跑不计 ⇒ 否则分母被重跑成倍垫大、`cost_ratio` 假性变绿） |
| **Z2** | 分子 `incremental_cost` | 增量重算的 `entity_count + relation_count`（`IncrementalRebuildResult`，零新埋点） |
| **Z3** | 量纲 | 两侧**同为"图元素个数"**，由**同一个** `_graph_elements()` 换算 ⇒ 结构上不可能漂移 |
| **Z4** | 落哪一行 | 当日 `stage='extraction'` 行（X-7 分母的"同一批语料"= 该行讲的同一批文档）；**不改** P6-V2 的 stage 集合与唯一约束；两列**各有且仅有一个写入方**，都经 `_record_graph_cost` |
| **Z5** | 零值怎么办 | `amount <= 0` ⇒ **跳过 + 打日志**（与既有"不写 0"工艺纪律同口径：写 0 会让仪表盘看起来"有数据"） |
| **Z6** | 无增量 / 无分母 | `cost_ratio` 沿用 **`0.0`** 语义（用户裁决：不动契约、不加 null 分支） |
| **Z7** | 行级要不要维护 `cost_ratio` | **要**（`_refresh_cost_ratio`），否则同一张表的行读数与区间级读数两个口径 |
| **Z8** | 判据进不进 CI | 进（纯逻辑 + PG，假图经 `session_factory` 注入 ⇒ 不需要真 Neo4j） |

## 5. 验收判据（每条要能贴机器输出）

1. `full_rebuild_cost` **有且仅有一个写入方**（`registry.py` 一处），且有实际读数；
2. `incremental_cost` **有且仅有一个写入方**（`incremental.py` 一处），且有实际读数；
3. **同一批语料第二次 kg.build（复用 `kg_version`）不重复累加分母** —— 重跑*n*次分母仍是
   首次的那个值（这条是 X-7「首次」二字的全部意义）；
4. **两侧同量纲**：分子分母都由 `_graph_elements()` 换算 ⇒ 断言
   `记录值 == entity_count + relation_count`，且比值为**个数比**（不是 token 比 / 毫秒比）；
5. **护栏**：增量重算失败 ⇒ 走 `_fail(...)`，**不写 `full_rebuild_cost`**（没有人为了出数
   去回落全量）、也不写 0 值的 `incremental_cost`，`cost_ratio` 仍 `0.0`；
6. **无数据时 `cost_ratio` = `0.0` 而非 NaN**（沿用既有语义，`math.isnan` 断言）；
7. 行级 `cost_ratio` 与区间级口径一致（同一份数据两处读数相同）；
8. `pytest` **不降**（基线：见 §6，动工前实测）；
9. 五项门禁读数不变：`check_startup_readiness` 17/0/0、`check_seams` 12 OK/0 ERROR、
   `export_openapi --check` 零 diff、`extract_seam_signatures --check` 一致、ruff 双通过；
10. 回登：`changes/P6-V3/integration-log.md` + spec §10.1.1（新行，**编号不重排**）。

## 6. 执行顺序（每步一个 Conventional Commit）

1. `cost_metrics.py`：`_graph_elements` + `_record_graph_cost` + 两个公开写入入口
   + `_refresh_cost_ratio`（抽取 `_upsert_day_row` 的取行逻辑共用，避免两份锁逻辑漂移）
2. `registry.py`：首次全量构建 ⇒ 写分母（旁路 try/except，**不拖垮主链路**）
3. `incremental.py`：增量重算成功 ⇒ 写分子（旁路 try/except）
4. 测试（新文件）+ `ruff`
5. 回登 spec / integration-log / new-session-prompt

## 7. 残留风险（**不许被读成"C3-b 已达标"**）

1. **TBD-7 阈值未拍板** ⇒ C3-b 仍 `BLOCKED`：本批只让两侧**能出数**；
2. **量纲是"个数"不是"钱"**：`cost_ratio` 是"重写了多少图元素 / 全量构建了多少图元素"，
   **不等于**成本单价比；要换成金额口径须另行裁决（且两侧构建路径实读均无 LLM 投入）；
3. 仪表盘仍**无 stage 切片**（X-5 未做）⇒ 区间视图依然是混合口径；
4. 增量**失败**的那次重算已真实花掉的图写操作**记不到**（`_fail` 里图侧可能已写了部分 batch）
   ⇒ 分子偏保守，**不回填、不猜数**。
