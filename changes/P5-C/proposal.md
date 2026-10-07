# P5-C · D2 / M6 第一批：`/ontology/active` + 冷启动确认闭环

> **日期**：2026-10-07　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../P5-B/integration-log.md`](../P5-B/integration-log.md)
> **边界**：本文件 §Non-goals（11 条）｜**花销**：预期 ¥0（不调真 LLM 做冷启动实测）
> **任务拆解**：[`tasks.md`](./tasks.md)

---

## 1. 目标（一句话）

把 M6 的**读侧**与**冷启动闭环**从 501 占位做成真实现：`GET /ontology/active`、
`POST /ontology/cold-start`、`POST /ontology/confirm`，并把「断言它必须 501」的那批测试
改成断言**真行为**。

三刀：

1. 落 `ontology_actions` 审计表（spec §4.2）——「未确认不生效」可举证的前提；
2. `GET /ontology/active` 接到 `load_active_ontology`（零算法风险）；
3. `cold-start → confirm` 闭环：冷启动**只建议**，必须 confirm 才转 `active`
   （spec §3.1 验收 1 / §3.5 验收 12）；
4. 同步改写测试（Non-goal 6：改写成断言真行为，**不删**）。

## 2. 为什么是这一刀

- **排期队列指向它**：`docs/delivery-plan.md:198` 的 P5 顺序是 `D4 → **D2 M6** → D1 → …`，
  D4 已由 P5-B 于 2026-10-07 收口。
- **闸门已满足**：`specs/m6-ontology-incremental.md` 已是 v1.0（2026-10-02 定稿），
  §10 checklist 七项全勾；同一份 spec 明写「7 个端点仍为 501 占位骨架」。
- **服务层已做掉大半**：`app/services/ontology.py` 的 `load_active_ontology` /
  `suggest_ontology_types` 都是可用实现（后者真机产出 12 实体 + 12 关系类型）。

## 3. 明确不做

1. **不改 `contracts/openapi.yaml`**：7 个端点的契约已先行落好；改契约 ⇒ 触发契约同步五步，那是另一批。
2. **不碰 `merge` / `split` / `rename`**：前置「增量重算」不存在。
3. **不做前端页面 / 不写前端 API 封装**：本批不进 `frontend/`。
4. **不引入新的测试框架**：沿用 pytest；无前端测试框架。
5. **不重建 / 迁移演示图谱**：图谱已在 P5-B 恢复（`attendance-demo-v1` ready）。
6. **不删除占位测试来让它绿**：`test_ontology_placeholder_endpoints.py` 在实现落地当天必然变红，
   处置是**改写成断言真行为**，删文件等于拆护栏。
7. **不新增依赖**（后端不引 Black，只用 Ruff）：G-1 护栏。
8. **不为 M6 新增别名 / 兼容层**：有多套叫法属历史债，本批不顺手。
9. **不改 `demo/attendance/ontology_schema.json` 的实体 / 关系定义**：它是本体唯一真源。
10. **不顺手订正 `docs/delivery-requirements-and-guardrails.md:115` 的过期表述**：值得改，但要单独登记。
11. **不碰 `entity_merge_candidates` 与 `applied` 枚举的契约同步五步**（D3 已裁决）：
    `applied` 只服务于 `/ontology/merge`，而 merge 已由第 2 条排除 ⇒ 五步整体顺延。

## 4. 采纳的决策（来自新会话开场提示词）

| # | 决策 | 处置 |
|---|---|---|
| D1 | 闸门是否满足 | 满足，直接开工（spec v1.0 + checklist 全勾） |
| D2 | 占位测试怎么写 | **改写成真行为测试**，不删不 skip |
| D3 | 是否先升 M2 spec 加 `applied` | **不动 spec / 契约**，契约同步五步随 merge 端点整体顺延 |
| D4 | `/cost/dashboard` 的 RBAC | **只登记、不动 `rbac/policy.py`**（端点恒 501 ⇒ 无访问面）；债随端点走 |
| D5 | C1 判据口径 | 沿用 P5-B **X-1 裁决**：0.0294 只作历史数字，引用须带判分表版本 + `graph_spec.retriever` |
| D6 | 成本敞口 | 本批预期 ¥0；若确需跑真冷启动，先说明再花 |

## 5. 本批需要登记的**偏离**（不是某 lifework，逐条可撤回）

> 三条都源于「spec §4.2 / §4.1 的字段约束」与「本批验收判据」撞车，按最小代价选边并如实登记。
| # | 偏离 | 为什么不这样不行 | 撤回方式 |
|---|---|---|---|
| **X-2a** | `ontology_actions.action_type` 的 CHECK 在 spec 的三值（`merge/split/rename`）之外**多一个 `confirm`** | 判据 4 要求「确认后的状态变化写进 `ontology_actions`」；而 spec §4.2 的「仅三值」源自 plan §12 R12 对**批次 B GUI 三动作**的收口，未定义**批次 A**（冷启动 / 确认）的审计载体 | 一个迁移 + 删常量即可退回三值（退回 ⇒ 判据 4 作废） |
| **X-2b** | `ontology_actions.kg_version` 允许 NULL，且 `confirm` 行的 CHECK 形如「非 confirm 必须非空」 | spec §4.6 的新租户链路是「先确认本体、后有图谱」⇒ confirm 时**不可能**有 `kg_version`；写假值等于 fabrication | 同上 |
| **X-2c** | `confirm` 落 `ontology_schemas` 时 `domain_description` 写**空串** | `OntologyConfirmRequest` 不含该字段（契约不可改，Non-goal 1），而列 `NOT NULL`；编一段"看起来合理"的描述等于替用户决定业务域 | 将来契约带上该字段后直接回填；在此之前以"空 = 未知"为口径 |
| **B-1** | **契约 + 前端生成物**随三个端点实现**再生**（openapi.yaml 42 行 / api.d.ts 49 行，均为描述文本与一条已失效的 501 声明） | 端点已实现，而契约仍写「占位骨架，恒返回 501」「未接线到本端点」——留着是**失真**；另一选项是明知描述为假仍提交，与本仓反「假做」的基线直接冲突 | 单独一个提交（`90bb5163`），两个文件均系生成物，撤回即恢复零契约改动（⇒ 判据 6 之外的所有判据不受影响） |

## 6. 验收判据（每条都要能贴机器输出）

1. `ontology_actions` 表已建（迁移后有该表，RLS ENABLE + FORCE 已落）
2. `GET /ontology/active` 返回真本体（不再是 501）
3. 冷启动只建议、未生效（`ontology_schemas` 无新增行，`test_suggest_writes_nothing_to_database` 仍绿）
4. confirm 后才转 `active`，且变化写进 `ontology_actions`
5. 占位测试**改写而非删除**，未实现的 4 个端点仍钉死 501
6. `export_openapi.py --check` 零漂移；26 路径计数不变
7. `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0
8. pytest 不降（CI 口径 ≥ 1007 passed / 5 skipped / 0 failed）
9. RBAC 债不丢、不裸奔（见 D4 登记）
10. CI 四 job 全绿，run id 回登 integration-log
