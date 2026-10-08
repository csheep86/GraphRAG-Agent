# ADR-0008：M6 版本继承读（版本链读侧）

- **状态**：Accepted（2026-10-08，P5-H 批次 C'）
- **关联**：`specs/m6-ontology-incremental.md` §5.1 注脚 P5-H；ADR-0002（版本是幂等键）；ADR-0003（租户隔离）；P5-F / P5-G
- **落地**：`backend/app/services/kg/version_view.py`、`backend/app/services/kg/version_scope.py`；三条读路径（概览 / 多跳推理 / 合规扫描）

---

## 1. 背景：一个真实的功能缺陷

P5-G §2.1 把校正顺序定为「① 读 active 版本 → ④ `rebuild_incrementally`
（受影响子图 ∪ 1 跳邻居）→ 产新版本并置 `ready`」。而
`KgVersioningService.get_active` 按 `ready_at DESC` 只取**一条**。两者的合力是：

> **一次校正之后，active `kg_version` 就是那个只含「受影响子图 ∪ 1 跳邻居」的小版本。**

而消费侧（概览 / 问答 / 合规）全部按**单一** `kg_version` 过滤 ⇒ **校正后它们几乎读空**。
这不是优化，是 P5-F / P5-G 引入的功能缺陷（对照 `specs/m6-ontology-incremental.md:207`：
「校正动作触发后，问答结果应能立即反映新图谱」—— 落地后实际不满足）。

## 2. 决策

**读侧引入「版本继承读」**：读的时候用 **active ∪ 祖先**的**有序版本列表**（新 → 旧），
并在图上对每个实体 id 选出**唯一**可见版本。

三条被否决的路线与理由：

| 路线 | 结论 | 理由 |
|---|---|---|
| 写侧把 base 全量复制进新版本 | ❌ | 直接违反 **P5F-3**（增量重写节点数 = 校正节点数） |
| 校正不换 active | ❌ | 违反 m6 §5.1 与 §3.2 验收 3（响应要回新 `kg_version`） |
| 给 `kg_versions` 加 `parent_version` 列 | ⏸ 下一批 | 要写迁移、触碰 **G-6 迁移等价性**护栏 |

## 3. 版本链的真源：`ontology_actions`，不是 `kg_versions`

`kg_versions` 表**没有** `parent_version` 列（2026-10-08 实读 `models.py:283-306`），
父链的完整信息**只在** `ontology_actions` 里：一行动作的 `result_kg_version`
（产出版本）指向它的 `kg_version`（基线版本）。

故 `resolve_read_versions()` **沿 `ontology_actions` 反推**父链。

> ⚠️ 这是**无迁移前提下的取法，不是设计意图**。长远要不要把版本链提升为表内真源
> 另行裁决（属下一批，见 §7 指针 4）。**本 ADR 不裁这件事。**

配套的三条硬约束：

1. **限深 16（防环的工程兜底，不是语义保证）**：超过 ⇒ **截断**（丢掉最老那几代），
   **不报错**，只打 `warning`。
2. **`org_id` 是常设过滤键**（ADR-0003 / DR-B5）：他 org 的动作行即便
   `result_kg_version` 撞名也**不得**串进本租户的链。
3. **不引入缓存**（D7）：版本链是一次 PG 查询 + 一次图查询；缓存只会换来
   「读到过期版本链」这种更坏的失败。

## 4. 选中规则（每个 id 只保留一个版本）

自上而下（新 → 旧）遍历版本链，三条规则按序应用：

1. **链上最新者胜**：先被选中的版本即为该 id 的可见版本 ⇒ 校正后的值接管旧值；
2. **删除不再继承**：某版本对应动作的 `target_entities.entity_ids` 里的 id
   **不在**该版本的节点集里 ⇒ 判为该动作删掉了它 ⇒ **停止**向更旧版本继承；
3. **已选中者优先于删除判定**：已在更新版本里出现过的 id，即便被某个更旧版本的
   作用域判为「缺失」，也以新版本为准。

Cypher 侧的统一谓词（三条读路径**共用**，真身在
`app/services/kg/version_scope.py`）：

```cypher
n.kg_version IN $kgs
AND (size(keys($sel)) = 0 OR $sel[n.id] = n.kg_version)
```

**`size(keys($sel)) = 0` 这一句不能省，也不能改写成 `$sel[n.id] IS NULL`** ——
map 参数里没有某个 key 时 `$sel[key]` 同样取到 `null`，于是
「选中表为空（缺省形态）」与「该 id 未被选中（已被 merge 删掉）」会被混为一谈，
被删掉的节点会重新读出来。本批实测踩过，症状是"merge 似乎没生效"。

缺省形态（版本链只有 active 一条、选中表为空 map）⇒ 谓词退化为
`n.kg_version IN $kgs`（列表只有一个元素）⇒ **等价于原来的 `= $kg`：零变化**。

> 为什么 `version_scope` 必须住在**零依赖**模块里：`app.services.kg.__init__`
> 会拖进 `builder`（→ `graphs`），而 `graphs.py` 的 Cypher 常量在**模块级**构建
> ⇒ 直接 import 会成环（本批实测 `ImportError`）。故谓词函数不牵任何 `app.*`，
> 共享它的一方各自导入。

## 5. 跨版本边：本批的口径与**已知限制**

同一个 id 在两个版本里是**两个物理节点**（`e2@v1` 与 `e2@base`）。而写侧按
P5F-3 与「只迁移两端都在受影响集内的边」**刻意不迁移**受影响集的**边界边**
（`e2 — e3` 只存在于旧版本）⇒ 这类边在物理上**不存在**。

裁决（D6 本批口径，登记为 **P5H-1**）：

| 读路径 | 跨版本边 | 说明 |
|---|---|---|
| **图谱概览**（`fetch_graph_overview`） | ✅ **出边** | 边投影改为**按 id 空间**取（`CALL {}` 子查询 + 按 `(source,target)` 取链上最新一份）。若按物理节点成员判断（`a IN nodes`），图上会碎成孤岛，那不算"看到全图" |
| **合规扫描**（`scan_attendance_compliance`） | ✅ 天然可用 | 继承来的节点彼此同在一个旧版本，边也在那个版本上 ⇒ 事实链完整 |
| **多跳推理**（`fetch_reasoning_path`） | ❌ **不连**（**P5H-6 已知限制**） | Cypher 的变长路径走的是物理边；要跨版本就得换成 Python 侧的 id 级图遍历 —— 那是另一处改动，本批不做 |

**幽灵路径怎么防**（判据 5 的实质）：边的两端必须是**选中表里存在的 id**，
而被 merge 删掉的 id 压根不在选中表里 ⇒ 连不出去。安全侧比"两端同版本"更强。

## 6. 常见误读（三条）

1. **「读侧能看全图」≠「写侧可以偷懒」**：P5F-3 必须继续成立，本批**没有**为了
   读侧好看而把新版本写全；
2. **「版本链限深 16」≠「不会退化」**：超限行为是截断 + warning，不是语义保证；
3. **「三条路径切了」≠「读侧已完整」**：剩余路径仍是单版本（清单见 §7 指针 1），
   且 M4 端到端问答**尚未**接上视野（`agents.py` 的检索没有 PG 会话来解析版本链）。

## 7. 未切换的读路径（**逐条登记**，下一批指针）

| 路径 | 位置 | 状态 |
|---|---|---|
| `fetch_all_subgraph` | `graphs.py:1359` | 单版本 |
| `fetch_entity_detail` | `graphs.py:2149` | 单版本 |
| `fetch_anchor_entity_ids` | `graphs.py` | 单版本 |
| `list_attendance_anomalies` / `explain_attendance_anomaly` | `graphs.py:2400` | 单版本 |
| `fetch_document_subgraph` | `graphs.py` | 单版本 |
| `agents.py` 的检索链路 | `agents.py:257` | 单版本（**M4 端到端因此仍未修复**） |
| `documents.py` 的图谱读 | `documents.py:264` | 单版本 |

其它登记项：

- **统计口径（P5H-4）**：概览的 `doc_count` / `entity_count` / `relation_count`
  仍取 PG `kg_versions` 的落库计数（active 版本的产出数），与继承后的节点 /
  边投影**会不一致**。改统计 = 重新裁决"继承进来的算不算这个版本的产出"，
  属另一条语义决策 ⇒ 留给 GUI 批次一并裁。
- **版本号长度**：`kg_versions.version` 是 `String(64)`，连续多级增量
  （每级 +11 字符）会撑爆该列 ⇒ 另择时机裁决。
- **指针 4**：给 `kg_versions` 加 `parent_version` 列（需迁移 + G-6）。
- **指针 5**：多跳推理改为 id 级图遍历，取消 P5H-6 限制。

## 8. 机械判据（本批新增的守卫）

| 判据 | 用例 |
|---|---|
| 版本链有序（无父链 / 单跳 / 连续 3 次） | `tests/test_version_read_view.py` |
| 跨 org 版本不混入链、选中表不跨租户 | 同上 |
| 选中表：同 id 取最新；被 merge 删掉者不再继承 | 同上 |
| 缺省零开销（无历史 ⇒ 不额外打图） | 同上 |
| 校正后未受影响节点仍读得到 / 读到校正后的值 | `tests/test_version_chain_readers.py` |
| 三条读路径各一条真图用例（概览 / 推理 / 合规） | 同上 |
| 跨版本边出边 + 不留幽灵边 | 同上 |
| 写侧判据没被打掉（P5F-3 九条 + 例外断言仍绿） | `tests/test_kg_incremental_rebuild.py`、`tests/test_ontology_correction_actions.py` |
