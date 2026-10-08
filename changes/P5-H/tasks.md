# P5-H · 任务拆解

> **边界**：[`proposal.md`](./proposal.md) §3（10 条 Non-goals）
> **执行模式**：无人值守，逐任务验证通过即提交

---

## T1 · `backend/app/services/kg/version_view.py`（**新增**，后端开发 B）

- [ ] `resolve_read_versions(*, db, org_id, active_version=None, max_depth=16) -> tuple[str, ...]`
      —— 纯 PG：从 active 起沿 `ontology_actions`（`result_kg_version` → `kg_version`）回溯父链，
      返回**有序**列表（新 → 旧）；`org_id` 过滤是**常设防线**（ADR-0003 / DR-B5）；超限截断 + `warning`
- [ ] `resolve_entity_selection(*, session, org_id, versions, scopes) -> dict[str, str]`
      —— 一次图查询枚举版本链上的 `(id, version)`，按「链上最新者胜」选中
- [ ] **删除兜底（P5H-2）**：某版本对应动作的 `target_entities.entity_ids` 里的 id
      **不在该版本的节点集里** ⇒ 判为已删除，**停止**向更旧版本继承
- [ ] `build_read_view(*, db, session, org_id, max_depth=16) -> VersionReadView`
      —— 组装 `versions` + `selection`；`cypher_params()` 给下游 Cypher 提供 `$kgs` / `$sel`
- [ ] 模块 docstring 写明：版本链真源是 `ontology_actions`（**不是** `kg_versions`），
      以及链长超限的行为登记（P5H-5）

## T2 · 读路径 ①：`GraphService.fetch_graph_overview`（`graphs.py:2012`）

- [ ] 版本 singolo → view：`self._build_read_view(db=db, org_id=org_id)`
- [ ] `_QUERY_GRAPH_OVERVIEW` 由 `n.kg_version = $kg_version` 改 `$sel[n.id] = n.kg_version`
      （**org 三重判断照旧**，与应用层选出表的 org 过滤双保险）
- [ ] 边：在已选中的节点之间取，沿用 `_temporal_view("r")`（as-of 口径零变化）
- [ ] ⚠️ 三个统计值（`doc_count` / `entity_count` / `relation_count`）**真源一字不改**（P5H-4）

## T3 · 读路径 ②：`GraphService.fetch_reasoning_path`（`graphs.py:2261` → `reasoning.py`）

- [ ] `build_reasoning_path()` 新增 `version_view` 形参（内部同时给 `resolve_anchors`）
- [ ] `_CYPHER_ANCHOR_CANDIDATES`：节点谓词改选中表判断
- [ ] `_cypher_paths()`：变长路径里 `ALL(n IN nodes(p) WHERE $sel[n.id] = n.kg_version)`；
      边的 `kg_version` 由 `= $kg` 改 `IN $kgs`（P5H-1 的 C 口径）
- [ ] `graphs.fetch_reasoning_path` 把 view 传下去；`fetch_anchor_entity_ids` 等
      **其余入口本批不动**（D5，登记为下一批指针）

## T4 · 读路径 ③：`GraphService.scan_attendance_compliance`（`graphs.py:2350` → `rules/`）

- [ ] `scan_compliance()` / `load_employee_facts()` 新增 `version_view` 形参
- [ ] `engine.py` 四条事实 Cypher（EMPLOYEE / SHIFT / ATTENDANCE / OVERTIME）：
      节点谓词改选中表，关系 `kg_version IN $kgs`
- [ ] `policy_values.load_policy_clauses()`：同上（它是合规扫描的规则值来源）
- [ ] `ComplianceReport.kg_version` 仍是 **head** 版本（契约字段值不变）

## T5 · 测试（后端开发 B）

- [ ] 新文件 `backend/tests/test_version_read_view.py`：
  - [ ] 判据 1：版本链三种情形（单跳 / 连续 3 次校正 / 无父链）⇒ **有序**（新 → 旧）
  - [ ] **跨 org 版本不混入链**（判据 11 新增项）
  - [ ] 选中表：同 id 多版本取最新；merge 删除的 id **不出现在选中表里**（P5H-2）
- [ ] 新文件 `backend/tests/test_version_chain_readers.py`（真 Neo4j + 真 PG）：
  - [ ] 判据 2：5 节点 rename 1 个 ⇒ 以 active 读图仍读到 **5 个**
  - [ ] 判据 3：改名者读到新名 + 旧名在 `aliases`；merge 掉的节点**读不到**
  - [ ] 判据 4：三条读路径各一条（overview / reasoning / compliance）
  - [ ] 判据 5：显式构造「边的一端在新版本、另一端只在旧版本」⇒ 幽灵路径的具体断言
- [ ] 判据 6（**反向，不许改断言**）：`test_kg_incremental_rebuild.py` 9 条 +
      `test_ontology_correction_actions.py::test_new_version_carries_only_the_corrected_subgraph` 仍绿

## T6 · ADR + spec 注脚（**架构师**角色，单独一笔提交）

- [ ] `docs/adr/ADR-0008-version-chain-read.md`：
      版本链真源 = `ontology_actions` / 有序继承 / 同 id 去重 / 跨版本边取法（P5H-1 C 口径）/
      删除兜底（P5H-2）/ **未切换的读路径清单** / 链长超限行为 / 常见误读三条
- [ ] `specs/m6-ontology-incremental.md` §5.1 `:207` 追加注脚：
      「active 版本**不等于**可见全集」+ 指向 ADR-0008；**不重排编号**（R5）
- [ ] `docs/acceptance-traceability-matrix.md` M6 行追加本批状态

## T7 · 门禁与收口

- [ ] `uv run ruff check .` + `uv run ruff format --check .`
- [ ] `export_openapi.py --check` 零 diff、**26 路径不变**（判据 9）
- [ ] `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0（判据 10）
- [ ] `check_seams.py` 仍 ERROR 0 / WARN 0 / OK 12
- [ ] `check_session_drift.py`（S1 读到 **10 条** Non-goals；S3 预期无事；S5 新模块的答案：
      被 T2–T4 三条读路径直接引用，非提前写）
- [ ] 本地 pytest（带 `GRAPH_REAL_NEO4J_*` 三开关）
- [ ] integration-log 撰写 + 提交推送 + CI 四 job 全绿（判据 12 / 13）
