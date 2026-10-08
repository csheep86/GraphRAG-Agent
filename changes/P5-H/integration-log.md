# P5-H 集成实录 · M6 批次 C'：**版本链读侧**（P5F-4 消费侧完整性）

> **日期** 2026-10-08　**分支** `main` 直推　**执行模式** 无人值守
> **上游** [`../P5-G/integration-log.md`](../P5-G/integration-log.md)（`main` = `67347970`，CI run `37743119955` 四 job 全绿）
> **边界** [`proposal.md`](./proposal.md) §3（**10 条** Non-goals）｜**任务** [`tasks.md`](./tasks.md)
> **ADR** [`docs/adr/ADR-0008-version-chain-read.md`](../../docs/adr/ADR-0008-version-chain-read.md)

---

## 1. 一句话

一次校正之后，active `kg_version` 会变成「只含受影响子图 ∪ 1 跳邻居」的增量版本 ⇒
概览 / 问答 / 合规**几乎读空**。本批新增**版本继承读**（active ∪ 祖先，有序版本列表 +
同 id 链上最新者胜），并把它切进**三条**读路径。

## 2. 为什么是这一刀（机械理由）

| # | 理由 | 证据 |
|---|---|---|
| 1 | P5-G 收口时登记的第 1 号指针 | `changes/P5-G/integration-log.md` §8：P5F-4 按 **D9** 取最小形态（只做显式断言 + 缺口登记），**没有解决** |
| 2 | 它是**功能缺陷**不是优化 | 实读链路：`get_active` 按 `ready_at DESC` 取一条 ⇒ 校正后 active = 小版本；消费侧按单一 `kg_version` 过滤 ⇒ 读空 |
| 3 | 有 spec 依据 | `specs/m6-ontology-incremental.md:207`：「校正动作触发后，问答结果应能立即反映新图谱」——落地后**不满足** |
| 4 | 判据可机械、且 **¥0** | 节点数 / 名字 / 边行数都能数出来，不调 LLM |

## 3. 决策表（本批自己裁决的部分）

| # | 决策 | 处置（**与 proposal §5 一致的部分不再复述**） |
|---|---|---|
| **P5H-1** ⚠️ | 跨版本边的取法 | **概览按 id 空间出边**（`CALL {}` 子查询 + 按 `(source,target)` 取链上最新一份）；**多跳推理不连**（见 P5H-6）。§10 第 2 类的三步自检：① D6 明写「拼不出来 ⇒ 不连」，本口径**同样不连**「两端不是同一批被选中节点」的路径；② 可整体缩小并登记；③ 故**不升级用户** |
| **P5H-2** ⚠️ | merge 删除怎么表达 | 用 `ontology_actions.target_entities` 当**动作作用域**兜底：某版本承诺处理的 id 不在该版本 ⇒ 判删除，停止继承。改写侧 ∈ Non-goal 3、加墓碑列 ∈ Non-goal 5 ⇒ 这是唯一剩下的真源 |
| **P5H-3** | Cypher 怎么携带选中表 | `$sel[n.id] = n.kg_version`（Neo4j map 参数动态键访问）。**实测**：本机 Neo4j `5.26.31` 支持，缺键 ⇒ `null` |
| **P5H-4** | 概览三个统计值 | **真源一字不改**（仍取 PG `kg_versions` 落库计数）⇒ 与继承投影**会不一致**，登记为缺口留给 GUI 批次 |
| **P5H-5** | 链长超限（> 16） | 截断 + `warning`，**不报错** |
| **P5H-6** ⚠️ | 多跳推理跨版本 | **不做**。Cypher 变长路径走物理边；要跨版本就得换成 Python 侧 id 级图遍历 —— 另一处改动。**已写成用例钉住**（`test_reasoning_path_stops_at_version_boundary_yet`），将来真接通时它会变红 ⇒ 强制回来更新口径 |

## 4. 实测结果（**全部是跑出来的，不是读代码得出的**）

### 4.1 Cypher 形态与 Neo4j 能力（开工第一步就验）

```
Neo4j 5.26.31：$sel['A'] = 'v1' / $sel['C'] = None   →  动态键访问可用
size(keys($sel))：map 非空 ⇒ 1；map 为空 ⇒ 0          →  「选中表为空」可机械区分
```

### 4.2 本批新增用例（真 Neo4j + 真 PG）

```
tests/test_version_read_view.py      13 passed
tests/test_version_chain_readers.py   6 passed     # 真图
```

真图用例逐条对应的判据：

| 用例 | 判据 | 实读 |
|---|---|---|
| `test_overview_reads_the_whole_graph_after_a_rename` | 2 / 3 | 5 节点改名 1 个 ⇒ 仍读到 **5 个**；改名者读到新名、旧名在 `aliases` |
| `test_overview_projects_edges_that_live_in_an_older_version` | 5 | `e2(v1) → e3(base)` 跨版本边**出边**（P5H-1 C 口径的可观测证据） |
| `test_merged_away_node_and_its_edges_never_reappear` | 3 / 5 | 被 merge 的节点**读不到**，且没有任何边的端点涉及它 |
| `test_reasoning_path_stops_at_version_boundary_yet` | 5 | 跨版本路径**不连**（P5H-6，显式钉住的限制） |
| `test_reasoning_path_recovers_after_an_unrelated_correction` | 4 | 不相关校正 ⇒ 不带视野时链**整条读空**；带视野 ⇒ `[POSITION:P001, POLICY_CLAUSE:C01]` |
| `test_compliance_scan_still_sees_employees_outside_the_corrected_subgraph` | 4 | `employee_count == 2`（未被影响的员工从旧版本继承回来） |

### 4.3 写侧判据没被打掉（判据 6）

```
tests/test_kg_incremental_rebuild.py       9 passed（断言未改）
tests/test_ontology_correction_actions.py 12 passed
```

其中 `test_new_version_carries_only_the_corrected_subgraph` **仍绿** —— 它钉「新版本
**物理上**不承载全图」，本批钉的是「读侧**逻辑上**能看到全图」，两条**互补**，都留着。

### 4.4 全量与门禁

| 项 | 结果 |
|---|---|
| 本地全量 pytest（带 `GRAPH_REAL_NEO4J_*`） | **1136 passed / 4 skipped / 2 failed** —— 2 条 failed 是**已知的本地环境债**（`test_eval_ci_gate.py::test_g25_real_graph_detection_is_not_empty`、`test_eval_corpus_a8.py::test_g25_v2_corpus_meets_thresholds_by_confidence_bound`，依赖 CI 才有的受控种子语料；CI 上有导入步骤 ⇒ 那 2 条在 CI 上绿） |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0**（与基线一致） |
| `check_seams.py` | ERROR 0 / WARN 0 / **OK 12** |
| `export_openapi.py --check` | 零 diff（契约**未动**） |
| `check_session_drift.py` | S1 读到 **10 条** Non-goals / S2 **6 文件 · 248 新增行**（阈值 25 / 600）/ S3 无事 / S4 无契约改动 / S5 新模块已被引用 —— **全 [OK]** |
| G-9 T1 / G-10 T2 | 全量跑过，断言**未放宽**；新增「跨 org 版本不混入链」与「选中表不跨租户」两条 |

## 5. 两处**动了既有测试**的地方（**逐条登记，不许悄悄改**）

1. **`tests/test_agent_reasoning_path.py::test_query_is_parameterized_by_kg_version_and_org`**
   原断言 `params["kg"] == "v-test"` ⇒ 改为 `params["kgs"] == ["v-test"]` +
   `params["sel"] == {}`。这是**同义收紧**（守卫意图「Cypher 必带版本过滤」仍在，
   并多钉了一条「缺省形态等价于单版本」），**不是放宽**。
2. **`tests/conftest.py` 新增 `real_graph_read_path` fixture**
   原因：conftest 有一个 **autouse** fixture 把 `GraphService.fetch_reasoning_path`
   桩成恒空 `[]`（目的是防止把基础设施故障插成别的语义）。而本批要验的**正是**
   推理路径本身 ⇒ 挂着那个桩时判据**永远绿也永远没意义**。新 fixture 在 conftest
   **导入期**抓下真身（autouse 桩装上之前），需要验路径的用例显式挂它。
   **它不是放宽护栏**：其他用例的屏蔽一字未动。

## 6. 本批踩到的坑（**下一批别再踩**）

1. **`$sel[n.id] IS NULL` ≠ 「未被选中」** —— map 参数缺键也返回 `null` ⇒
   「选中表为空（缺省）」与「该 id 已被删除」会被混为一谈，症状是
   **"merge 似乎没生效"**。必须写成 `size(keys($sel)) = 0 OR $sel[n.id] = n.kg_version`。
   （本批实测踩到，靠真图用例 `{e2: v1}` 与实读 `{e1,e2,e3}` 不一致才定位到。）
2. **跨版本边在物理上不存在** —— 同一 id 的新旧版本是两个物理节点，而写侧按 P5F-3
   不迁移边界边 ⇒ `a IN nodes`（节点对象成员判断）会把它全部判掉。概览改为
   **按 id 空间**投影才连得起来。
3. **`kg_versions.version` 是 `String(64)`** —— 连续多级增量（每级 `+11` 字符）
   4 级就会撑爆该列（本批写 5 级链用例时实测 `value too long`）。已登记为另择时机裁决。
4. **`app.services.kg.__init__` 会拖进 `builder`（→ `graphs`）** —— `graphs.py`
   的 Cypher 常量在**模块级**构建，直接 import `version_scope` 会成环。故谓词函数
   住在**零依赖**的 `version_scope.py`，Cypher 常量改为 `lru_cache` 的惰性函数。
5. **conftest 的 autouse 恒空桩**（见 §5 第 2 条）——真图用例照样会"绿得很空"。

## 7. 提交（分段，便于整笔 revert）

| # | 提交 | 范围 |
|---|---|---|
| 1 | `feat(m6)`: 版本继承读 + 三条读路径切换 | `backend/app/`、`backend/tests/` |
| 2 | `docs(m6)`: ADR-0008 + m6 spec §5.1 注脚 + 矩阵 | `docs/adr/`、`specs/m6-*.md`、`docs/acceptance-traceability-matrix.md` |
| 3 | `docs(chore)`: 本批 SDD 产物 | `changes/P5-H/` |

CI 为终裁（R-10）：run id ____（推送后回登；四 job 全绿 + `gh run watch --exit-status` 退出码 0）

## 8. 本批**不许外推**（完成本批 ≠ 以下任何一条）

- **读侧能看全图 ≠ 写侧可以偷懒**：P5F-3 继续成立，本批**没有**把新版本写全。
- **三条路径切了 ≠ 读侧已完整**：`fetch_all_subgraph` / `fetch_entity_detail` /
  `fetch_anchor_entity_ids` / `list_attendance_anomalies` / `explain_attendance_anomaly` /
  `fetch_document_subgraph` / `agents.py` 检索 → **仍单版本**（逐条登记 ADR-0008 §7）。
- **M4 端到端仍未修**：`agents.py` 没接视野（它需要 PG 会话才能解析版本链）。
- **`ontology_actions` 能反推链 ≠ 链是真源设计**：只是无迁移前提下的取法，
  加 `parent_version` 列**未裁**。
- **限深 16 ≠ 不会退化**：超限行为是截断 + warning。
- **概览统计值仍不一致**（P5H-4）。
- **本批修好读侧 ≠ GUI 可用**：m6 §1.1 批次 B 的前端界面仍不存在。
- **本地绿 ≠ CI 绿**：本机 Neo4j 常是停的，且本地有 2 条 g25 失败（缺 CI 种子语料）。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己写着
  「pytest 全绿 ≠ 护栏在拦」。

## 9. 下一批指针（按本批实际结果更新）

1. **剩余读路径切换**（ADR-0008 §7 清单）+ **`agents.py` 接线**（M4 端到端才算修好）。
2. **多跳推理改为 id 级图遍历**（取消 P5H-6 限制）。
3. **本体校正 GUI（前端）**：m6 §1.1 批次 B；同批按需建 `frontend/src/api/ontology.ts`。
4. **`GET /cost/dashboard` + `cost_metrics`**（m6 §3.4 验收 8 / 9，MVP 准入 C3-a / C3-b）；
   `cost_ratio` 阈值 TBD-7 **Sprint 13** 才收敛。
5. **给 `kg_versions` 加 `parent_version` 列**（需迁移 + **G-6**）；**顺带**裁决
   `version` 列的 64 字符上限。
6. **概览三个统计值的口径**（P5H-4）：与 GUI 批次一并裁。
7. **`human_review` 队列读端点**（M2 的 S9.13-2）。
8. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2，**已连续六批**有意不做）。
9. **DR-B6 / DR-B7 与 G-9 / G-10 的口径对账**（纯 docs，建议并入任一批次顺手做）。
10. **多租户出向审计归属**（P5-D 的 X-3 撤回条件）。
11. **D7（`question` 参与检索）/ D5（M4 完整化）/ D8**：算法活，各自单独排。
12. **m6 定稿遗留的另两个配置项**（`ONTOLOGY_LLM_SUGGEST_TIMEOUT` /
    `COST_RATIO_ALERT_THRESHOLD`）：在对应批次回填。
13. **日志 `message` 正文的脱敏**：逐个把 `mask()` 补到写敏感值的日志语句上。
