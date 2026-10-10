# P6-V3 集成日志：X-7 两侧写入方（2026-10-10）

- **队列**：[`docs/delivery-plan.md`](../../docs/delivery-plan.md) §9.2 序 **5d**
- **裁决来源**：[`specs/m6-ontology-incremental.md`](../../specs/m6-ontology-incremental.md)
  §10.1.1 **第 15 项**（2026-10-10 用户拍板：**A 组「图规模同量纲」**）
- **边界**：[`proposal.md`](./proposal.md)（Non-goals **9** 条）
- **上一批交接**：[`changes/P6-V2/new-session-prompt.md`](../P6-V2/new-session-prompt.md)

---

## 1. 本批做了什么

`incremental_cost` / `full_rebuild_cost` 此前**零写入方** ⇒ `cost_ratio` 恒 `0.0`。
本批按裁决把两列接上，两侧**同为「图元素个数」（实体数 + 关系数）**：

| 侧 | 落点 | 写入方（**各 1 处**） |
|---|---|---|
| 分母 `full_rebuild_cost` | `app/tasks/registry.py` `_do_kg_build`，`mark_ready` 之后 | 仅 **全新构建** 时（`fresh_build=True`），复用 `kg_version` 的重跑不计 |
| 分子 `incremental_cost` | `app/services/kg/incremental.py`，`mark_ready` 之后的**成功**分支 | 失败路径 `_fail(...)` **不写**（不写 0） |

两侧共用 `app/services/cost_metrics.py` 的 `_graph_elements()` 换算 + `_take_day_row()`
同一把行锁（从 P6-V2 的 `_upsert_day_row` 抽出，防止两份锁逻辑漂移），落到当日
`stage='extraction'` 行，并同步维护**行级** `cost_ratio`。

**提交**（代码 / 测试 / 文档分列）：

| Hash | 提交 | 内容 |
|---|---|---|
| `6054f21` | `docs(m6)` | 登记 X-7 口径再裁决 + 更正 `delivery-plan.md` 序 5d 的过期前提 |
| `6d564f8` | `feat(cost)` | 两侧写入方 + `_graph_elements` / `_record_graph_cost` / `_refresh_cost_ratio` |
| `c4f0dc0` | `test(cost)` | 判据 9 条（新文件）+ 修 1 条**顺序耦合**的既有用例 |
| `ddce063` | `docs(changes)` | `proposal.md` / 本日志 / 下一批提示词 |

**CI**：run [`38014108048`](https://github.com/csheep86/GraphRAG-Agent/actions/runs/38014108048)
**success**（推送 `c57bc41..ddce063` 触发；`main` 直推）。

---

## 2. 为什么是"图元素个数"（**本次裁决的依据，不是引用**）

开工前实读复核（提示词要求复核三遍）:

| 查实项 | 结果 | 出处 |
|---|---|---|
| `services/kg/` 是否有 LLM | **0 命中**（`build_chat_model` / `TokenUsage` / `invoke(` / `callback_handler` / `record_*_usage`） | 全目录实读 |
| 「全新构建分支」是否可量 LLM | ❌ `registry.py:630`→`:700`→`:756-815` 全程 = 读 storage 的 `entities/relations/chunks.json` → `ThreeStageKgBuilder` 写图 | 实读至 815 行 |
| 两列是否已有写入方 | **0 个**：仅见于迁移 `df5ec5c9e1b1:55-56`、模型 `models.py:1177-1178`、读数 `cost_metrics.py`（原 344-347）、测试手工造数 | 全仓搜索 |
| 分母所需计数是否已有列 | ✅ `KgVersion.entity_count` / `relation_count`（`models.py:293-294`），`mark_ready` 已在写 ⇒ **零迁移** | 实读 `versioning.py:129-151` |
| 分子所需计数是否已有 | ✅ `IncrementalRebuildResult`（`incremental.py:139-140`）⇒ **零新埋点** | 实读 |

⇒ spec 第 12 项那条旧裁决（"全新构建分支**已有真实 LLM 调用可量**"）**被实读推翻**；
token 口径下分子恒 0 ⇒ `cost_ratio` 会假性「显著 < 1.00」。⇒ 用户改为 **A 组**。

---

## 3. 决策落地（对照 proposal §4）

| # | 决策 | 落地结果 |
|---|---|---|
| Z1 | 分母 = 首次全量构建的图元素个数 | ✅ 且**复用 `kg_version` 的重跑不计**（`fresh_build` 判定 + 判据 9） |
| Z2 | 分子 = 增量重算的图元素个数 | ✅ 零新埋点 |
| Z3 | 两侧同量纲 | ✅ 同一 `_graph_elements()`；判据 `test_both_sides_use_one_shared_unit` 钉死 |
| Z4 | 落 `stage='extraction'` 行 | ✅ 未引入第三档 stage，`UNIQUE (org_id, metric_date, stage)` 未动 |
| Z5 | 零值跳过（不写 0） | ✅ `amount <= 0` ⇒ 跳过 + 日志；判据 4 |
| Z6 | 无分母 ⇒ `0.0`（不是 NaN） | ✅ `_refresh_cost_ratio` + `build_dashboard` 原语义未改；判据 7 |
| Z7 | 维护行级 `cost_ratio` | ✅ 与区间级同口径；判据 8 |
| Z8 | 判据进 CI | ✅ 假图经 `session_factory` 注入，**不需要真 Neo4j** |

---

## 4. 判据与机器输出

**新文件** `backend/tests/test_cost_metrics_graph.py`（9 条）：

| # | 用例 | 验的是什么 |
|---|---|---|
| 1 | `test_full_rebuild_cost_records_graph_element_sum` | 分母 = 实体 + 关系（不是 token / 毫秒） |
| 2 | `test_graph_costs_accumulate_and_refresh_row_ratio` | 同日多次重写累加 + 行级比值跟着走 |
| 3 | `test_both_sides_use_one_shared_unit` | **同量纲**（本批核心） |
| 4 | `test_zero_graph_elements_and_missing_session_are_skipped` | 不写 0、不建行、`db=None` 跳过 |
| 5 | `test_incremental_rebuild_writes_numerator` | 真增量重算 ⇒ 分子落库（读库里的行，不是返回值） |
| 6 | `test_failed_incremental_rebuild_writes_nothing` | **护栏**：失败既不写分子、也不写分母（不许回落全量） |
| 7 | `test_cost_ratio_is_zero_not_nan_without_denominator` | `0.0` 而非 `NaN`（`math.isnan` 断言） |
| 8 | `test_dashboard_ratio_matches_row_level` | 行级与区间级同口径 |
| 9 | `test_same_corpus_rebuild_does_not_inflate_denominator` | **同一批语料重跑不重复计入分母** |

**实测读数**：

```
有图口径（GRAPH_REAL_NEO4J_{URI,USER,PASSWORD} 三个都设）：
  1191 passed, 5 skipped      ← 基线 1182 passed / 5 skipped ⇒ +9 新增，不降
无图口径（本机不设图变量）：
  1154 passed, 42 skipped
五项门禁：
  check_startup_readiness   [OK] 17 / [~~] 0 / [--] 0
  check_seams               ERROR 0 / WARN 0 / OK 12
  export_openapi --check    零 diff
  extract_seam_signatures   与快照逐字一致
  ruff check / format       279 files already formatted，All checks passed
check_session_drift         S1 读到 9 条边界；S2 6 文件 / 307 行；S3~S5 未触发
```

本地容器 `graphrag-pg` / `graphrag-neo` 双 Up（注意：本机测试库是**持久库**，见 §5 第 2 条）。

---

## 5. 本批踩到的三个坑（**留给下一批，别再踩**）

1. **conftest 有一条 `autouse` 桩会把 `get_active` 顶掉**：
   `tests/conftest.py::pg_active_kg_version` 恒返回 `KgVersionRecord(version="v-test", ...)`，
   任意 org 都返回它 ⇒ 谁要**真读 PG 真源的 active 版本**，必须显式请求
   `real_pg_get_active` fixture 撤桩（既有的 `test_kg_incremental_rebuild.py` 每条都这么做）。
   本批的两条增量用例因此一开始以「动作行记录的基线 `p6v3-xxx` 与当前 active `v-test`
   不一致」的形态红掉 ——**看起来像增量失败，实为夹具问题**。
2. **`test_cost_metrics.py::test_dashboard_endpoint_returns_real_rows` 有顺序耦合**：
   真图用例（`test_kg_incremental_rebuild.py`）跑在 **default_org** 上，本批起它们会**真的写**
   这两列 ⇒ 那条既有用例读到 `cost_ratio == 15.0`（而非期望的 `0.0`）。
   ⇒ 修的是**它的隔离**（先清当日本 org 的行，再落自己的行），**不是**改判据让它绿：
   它断言的语义仍是「无增量 ⇒ 0.0」，只是不该依赖"当日只有自己一行"。
3. **本机测试库是持久库**（P6-V2 已记）：CI 每次起新 PG，本地不会 ⇒ 别指望 `create_all` 补列。

---

## 6. 残留风险（**不许被读成"C3-b 已达标"**）

1. **TBD-7 阈值仍未拍板** ⇒ C3-b **仍 `BLOCKED`**：本批只让两侧**能出数**。
2. **量纲是"个数"不是"钱"**：`cost_ratio` =「重写了多少图元素 / 全量构建了多少图元素」，
   **不是**成本单价比；要换成金额口径须另行裁决（且两侧路径实读均无 LLM 投入）。
3. 仪表盘仍**无 stage 切片**（属契约变更，未做）⇒ 区间视图仍是混合口径；X-5 描述文本亦未动。
4. 增量**失败**那次已真实写出的部分图操作**记不到**（`_fail` 拿不到计数）⇒ 分子偏保守。
5. `0/0` 仍按用户裁决报 **`0.0`**（不是 null）：「比值缺失」与「比值真为 0」读起来无法区分，
   已登记在 proposal §7。

---

## 7. 下一批指针

见 [`new-session-prompt.md`](./new-session-prompt.md)（已按本批**实际结果**改写，未照抄上一版）。
