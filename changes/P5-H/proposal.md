# P5-H · M6 批次 C'：**版本链读侧**（P5F-4 消费侧完整性）

> **日期**：2026-10-08　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../P5-G/integration-log.md`](../P5-G/integration-log.md)（`main` = `67347970`，CI run `37743119955` 四 job 全绿）
> **边界**：本文件 §3（**10 条** Non-goals，逐条对照）｜**花销**：预期 ¥0（PG 查询 + 图查询，不调 LLM）
> **任务拆解**：[`tasks.md`](./tasks.md)

---

## 1. 目标（一句话）

让**读侧**在「一次校正产出增量新版本」之后仍能看到**完整图谱**：新增**版本继承读**解析
（`resolve_read_versions()`：active 版本 ∪ 其祖先版本，新 → 旧有序），把首批读路径从

```cypher
WHERE n.kg_version = $kg              -- 单值
```

换成「**同 id 在版本链上取最新者**」的选中表 `$sel`，并把三条读路径切过去。

四刀：

1. **版本链解析**（新增 `app/services/kg/version_view.py`）：沿 `ontology_actions`
   （`result_kg_version` → `kg_version`）回溯父链，返回有序版本列表（新 → 旧），限深度防环。
2. **选中表解析**：一次图查询枚举版本链上的 `(id, version)` 组合，按「链上最新者胜 +
   被本版)](作删除者不再继承」算出 `selection: dict[id, version]`。
3. **读路径切换**（首批 **3 条**，见 D5）：`fetch_graph_overview` / `fetch_reasoning_path` /
   `scan_attendance_compliance`。
4. **ADR + 升版 `specs/m6-ontology-incremental.md` §5.1 注脚**（架构师帽）：把「active 版本
   **不等于**可见全集」这个隐含前提写明。

## 2. 为什么是这一刀

- **它是 P5-G 收口时登记的第 1 号指针**：`changes/P5-G/integration-log.md` §8 第 1 条
  「版本链读侧……本批已把"缺"钉成显式事实」。P5-G 按 **D9** 取了最小形态（只做显式断言 +
  缺口登记），**没有解决**它 ⇒ 它现在是在飞的第一顺位。
- **它是功能缺陷，不是优化**（实读链路，2026-10-08）：
  P5-G §2.1 的顺序是「① 读 active → ④ `rebuild_incrementally`(受影响集 ∪ 1 跳邻居) → 新版本
  置 ready」。而 `KgVersioningService.get_active:203` 按 `ready_at DESC` 只取**一条**
  ⇒ **校正后 active 就是那个小版本**。消费侧六个入口
  （`graphs.py:1359 fetch_all_subgraph` / `:2012 fetch_graph_overview` / `:2149 fetch_entity_detail`
  / `:2261 fetch_reasoning_path` / `:2350 scan_attendance_compliance` /
  `:2400 list_attendance_anomalies`，外加 `documents.py:264` 与 `agents.py:257`）
  全部按**单一** `kg_version` 过滤 ⇒ **校正后它们几乎读空**。
- **它有 spec 依据**：`specs/m6-ontology-incremental.md:207`（§5.1 上游依赖第 3 条）明文
  「M6 校正动作触发后，**问答结果应能立即反映**新图谱」。当前实现**不满足**这一条。
- **判据可机械**：「未受影响的节点在校正后仍能被读到」「被校正的节点读到的是校正后的值」
  「跨版本边不连出幽灵路径」——都能数出来，且**不需要 LLM**（本批 ¥0）。

### 2.1 为什么不选另外两个候选

| 候选 | 不选的原因 |
|---|---|
| **本体校正 GUI（前端）** | P5-G 指针第 4 条，属另一批。**顺序上必须先做本批**：GUI 一旦上线就会频繁触发校正，每触发一次就把 active 变成小版本 ⇒ 先把洞堵上再开门 |
| **`GET /cost/dashboard` + `cost_metrics`**（批次 D / MVP 准入 C3-a·C3-b） | 属另一条价值链；`cost_ratio` 阈值（TBD-7）**Sprint 13** 才收敛，现在做拿不到"显著 < 1.00"的判据 |

## 3. 明确不做（**10 条 Non-goals**，逐条对照）

1. **不做 GUI / 前端业务代码**：本批连前端都不碰（除非判定契约必需，才再生 `api.d.ts`）。
2. **不改 `specs/m6-ontology-incremental.md` 的正文**：只追加 §5.1 注脚（架构师帽），
   **不重排编号**（`dev-doc-status.md` **R5**）。
3. **不动写侧**：`app/services/kg/incremental.py` 与 `app/services/kg/correction.py`
   **一行不改**（P5F-3「增量重写节点数 = 校正节点数」的机械判据必须继续成立）。
4. **不动 `KgVersioningService.get_active` 的语义**：它仍返回**一条** active 版本；
   本批新增的是**并列**的 `resolve_read_versions()`，不是替换。
5. **不给 `kg_versions` 加 `parent_version` 列**：需要写迁移并触碰 **G-6 迁移等价性**护栏，
   本批不启动（见 D4）。
6. **不碰成本仪表盘 / `cost_metrics` / `COST_RATIO_ALERT_THRESHOLD`**：批次 D。
7. **不新增第三方依赖**：现有 `neo4j` 驱动 + SQLAlchemy 即可。
8. **不新增错误码**（预期）：失败沿用既有码。若确有必要 ⇒ `errors.py` **四处**字典齐加。
9. **不一次切完所有读路径**：~40 处 `kg_version` 过滤点一次性改会触发 `check_session_drift.py`
   的 **S2** 阈值 ⇒ 首批只切 D5 点名的 3 条，其余**逐条登记**为下一批指针。
10. **不做批量校正 / 撤销栈 / 本体版本对比 GUI**：m6 §1.2 明列 Out of Scope。

## 4. 采纳的决策（来自新会话开场提示词 §5）

| # | 决策 | 处置 |
|---|---|---|
| **D1** | 主题 | ✅ 定 **M6 版本链读侧（P5F-4 消费侧完整性）** |
| **D2** | 是否新增配置 | **不新增**；若确需 ⇒ ① 有真实消费者 ② 同步 `.env.example` ③ 不得占位 |
| **D3** ⚠️**必答** | 实现形态 | **取 A（读侧版本集合）**：读时用 `active ∪ 祖先` 的有序版本列表。<br>**B（写侧把 base 全量复制进新版本）不选** —— 直接违反 P5F-3；<br>**C（校正不换 active）不选** —— 违反 m6 §5.1 与 §3.2 验收 3（响应要回新 `kg_version`） |
| **D4** ⚠️**必答** | 版本链从哪来 | **取 A1（沿 `ontology_actions` 反推，无迁移）**：`result_kg_version` → `kg_version` 逐跳回溯，限深度（默认 16）防环。<br>**A2（加 `parent_version` 列）本批不做**（要迁移 + G-6）。<br>⇒ **ADR 里写明：版本链的真源是 `ontology_actions`，不是 `kg_versions`** |
| **D5** ⚠️**必答** | 首批切哪几条 | **只切 3 条**：`fetch_graph_overview` / `fetch_reasoning_path` / `scan_attendance_compliance`。<br>其余（`fetch_all_subgraph` / `fetch_entity_detail` / `fetch_anchor_entity_ids` / `list_attendance_anomalies` / `explain_attendance_anomaly` / `fetch_document_subgraph` / `agents.py` 检索）**本批不动**，逐条登记为下一批指针 |
| **D6** ⚠️**必答** | 同 id 多版本节点怎么去重 / 跨版本边怎么取 | 见 §5 **P5H-1**（本批对 D6 的两种候选都做了收敛，理由逐条登记） |
| **D7** | 缓存 | **不引入缓存**：版本链解析是一次 PG 查询 + 一次图查询，不为它加一层会过期的状态 |
| **D8** | 契约会不会动 | **预期零改动**；若动了 ⇒ 走完同步五步，**不算升级** |
| **D9** | 审计 | 本批不新增审计点；M5 中间件已全量覆盖 |
| **D10** | 成本敞口 | 本批**预期 ¥0** |

## 5. 本批需要登记的**决策补充**

| # | 冲突点 | 本批取法 | 登记理由 |
|---|---|---|---|
| **P5H-1** | **D6 的跨版本边取法**：候选 A「边的版本 = 两端被选中版本的**较新者**」会把多次校正叠加后的边**全部**判为拼不出（读到的图会碎成孤岛）；候选 B「两端**同版本**才出边」同样会把「只在旧版本里存在的一条真边」判掉（如 `B(v_new)—C(v_base)` 这种相邻关系） | **取 C：两端都必须是**选中表里的**那个具体节点 + 边自身 `kg_version ∈` 版本链** | §10 第 2 类的三步自检：① 不在 Non-goal 里（D6 明写「拼不出来 ⇒ 不连」，本口径**同样不连**"两端不是同一批被选中节点"的路径）；② 可整体缩小到 C 并登记；③ 故**不升级**。安全侧反而更强：**幽灵路径的本质是"连到一个已被删除 / 尚未存在的节点"，而 C 口径下每个节点都先经选中表裁决，merge 删掉的节点根本进不了图** ⇒ 判据 5 以更强的形式成立 |
| **P5H-2** | **merge 删除怎么表达**：`correction._merge_transform` 是 `DETACH DELETE` 右节点，图里**没有墓碑**；若只看「链上最新出现版本」，右节点会从旧版本里被继承回来，判据 3「被 merge 掉的节点**读不到**」会塌 | **读方位版的动作作用域兜底**：某版本 `v` 对应的 `ontology_actions.target_entities.entity_ids` 里的 id，**若不在 `v` 的节点集里 ⇒ 判为该版本已把它删除**，停止向更旧版本继承 | Non-goal 3 禁止改写侧（不许加墓碑）；Non-goal 5 禁止加 `parent_version` 列。`target_entities` 是**写侧自己落的审计字段**（P5-G 已落地）⇒ 拿它当"本动作承诺要处理的 id"是真源语义，不是猜 |
| **P5H-3** | **Cypher 怎么携带选中表** | `$sel[n.id] = n.kg_version`（Neo4j map 参数的**动态键访问**，缺键 ⇒ `null` ⇒ 谓词为 null ⇒ 该节点被过滤） | 2026-10-08 **实测**：本机 Neo4j `5.26.31` 支持该语法（`$sel['C']` ⇒ `None`）；比「按 rank 排序 + `head(collect(n))`」省一层阶段，且能在**变长路径**（推理在多跳）里对每个中间节点逐个裁决 |
| **P5H-4** | **overview 的三个统计值**（`doc_count` / `entity_count` / `relation_count`，PG `kg_versions` 真源）与继承后的节点 / 边投影**会不一致** | **统计真源一字不改**（仍是 active 版本的落库计数），差异登记为缺口 | 改统计 = 重新裁决「继承进来的实体算不算这个版本的产出」，属另一条语义决策，本批无判据覆盖（Non-goal：不许顺手外推）。GUI 批次（§11 指针 2）消费它时一并裁决 |
| **P5H-5** | **链长超限（> 16）怎么办** | 截断到 16，**不报错**，打 `warning` 日志 | 深度上限是**防环的工程兜底**，不是语义保证。累积 16 次以上连续校正是极端情形，届时 readonly 会退化为「丢掉最老那几个版本的继承」而非拒答 —— 行为必须在 ADR 里登记 |

## 6. 验收判据（**每条都要能贴机器输出**）

| # | 判据 | 怎么验 |
|---|---|---|
| 1 | **版本链解析正确** | 单跳 / 多跳（连续 3 次校正）/ 无父链三种情形各一条用例，断言 `resolve_read_versions()` 返回**有序**列表（新 → 旧） |
| 2 | **校正后未受影响的节点仍可读到**（**本批核心**） | 真 Neo4j + 真 PG：5 个节点，rename 其中 1 个 ⇒ 以 active 版本读图**仍能读到全部 5 个** |
| 3 | **被校正的节点读到的是校正后的值** | 被改名者读到**新名**且旧名在其 `aliases` 里；被 merge 掉的节点**读不到**（P5H-2 的删除语义） |
| 4 | **三条读路径都切了** | `fetch_graph_overview` / `fetch_reasoning_path` / `scan_attendance_compliance` 各一条真图用例，结果与判据 2 / 3 一致 |
| 5 | **不连出跨版本幽灵路径** | 显式构造「边的一端在新版本、另一端只在旧版本」⇒ 按 P5H-1 的 C 口径判定；且**被删除节点不得出现在结果里** |
| 6 | **写侧判据没被打掉** | `test_kg_incremental_rebuild.py` **9 条全绿且断言未改**；`test_ontology_correction_actions.py::test_new_version_carries_only_the_corrected_subgraph` **仍绿**（它钉「新版本**物理上**不承载全图」，本批钉「读侧**逻辑上**能看到全图」，两条**互补**，不许删任何一条） |
| 7 | **ADR 已落** | `docs/adr/ADR-0008-*.md`：版本链真源 = `ontology_actions`、有序继承规则、同 id 去重规则、跨版本边取法、删除兜底、**未切换的读路径清单** |
| 8 | **m6 spec §5.1 注脚已升版** | 口径写明「active 版本**不等于**可见全集，读侧按版本链继承」；**编号未重排**（R5） |
| 9 | **契约零漂移** | `export_openapi.py --check` 零 diff、**26 路径不变** |
| 10 | **护栏不倒退** | `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0 |
| 11 | **隔离不倒退** | G-9 / G-10（T1 跨 org 越权 / T2 并发串租户）**仍全绿且断言未放宽**；新增一条：**跨 org 的版本不混入本租户的版本链**（`resolve_read_versions()` 内带 `org_id` 过滤） |
| 12 | **pytest 不降** | CI **≥ 1118 passed / 5 skipped / 0 failed**；既有守卫**不许为让它绿而改断言** |
| 13 | **CI 四 job 全绿** | `gh run watch <id> --exit-status` 退出码 0，run id 回登 integration-log |
