# Sprint 9 · 批次 C 勘察（C0）—— 只读结论

> 日期：2026-09-29。**只读**（读文件 + grep），未起 Neo4j、未跑查询、未改代码 / 契约 / 演示库。
> 用途：替换 `tasks.md` 批次 C「C0 勘察」那五条待办的**猜测**，给新会话直接上手。
> 记号：⚠️ = 需用户裁决；⇒ = 由证据推出的结论。

## 0. 一句话结论

四源（发票 / 凭证 / 供应商主数据 / 合同）在**代码与语料里都不存在**——批次 C 不是「补三类算法」，
而是**先建一条结构化摄入链 + 主体税号真源**，再谈算法；`unaligned_subjects` 零写入属实、
`entity_merge_candidates` 不存在属实、`applied` 两条口径可调和但**契约侧当前无落点**。

## 1. C0 五条逐项结论

### C0-1 四源摄入入口：**不存在**（唯一 CSV 摄入链是考勤域）

| 证据 | 结论 |
|---|---|
| `backend/scripts/` 全部 15 个脚本 | 只有 `ingest_attendance_csv.py` / `ingest_attendance_policies.py`；无 invoice / voucher / supplier 摄入 |
| `demo/` 目录树 | **只有 `attendance/`**（9 csv + 4 docx + 5 md + mapping.yaml + 1 py）⇒ 无任何四源语料 |
| `demo/attendance/mapping.yaml:29-45` | `version: 2` / `domain: attendance`，节点从 `employees.csv` 派生（EMPLOYEE / DEPARTMENT …） |
| `app/services/external_data/schema.py:25-32`（接缝 8） | 只收 4 列（`object_type` / `local_id` / `external_system` / `external_id`）= **外部 ID 映射**，不是业务节点摄入 ⇒ **不是**四源入口 |

⇒ 四源摄入链 = **新增**。可复用的只有 mapping.yaml 那套**模式**（确定性、不经 LLM、不新建表、沿用 `kg_version` 幂等键）；
按 **R15**（`dev-doc-status.md` §8）不做过早抽象——第二个真实格式出现才把 mapping 抽成配置驱动。

### C0-2 主体层现状：只有 `:Subject` / `:LegalPerson` / `:Address`，**税号恒空**

- `kg/builder.py:31-36`：主体层由 **M2 LLM 抽取**产出（stage-2.6 建节点、stage-3.2 建 `LEGAL_REP` / `REGISTERED_AT`），
  `:Subject.id` = **规范化名称的 sha256**（跨文档同名天然合并，共享法人/地址两跳就建立在这上面）。
- `kg/builder.py:489-491`：能当 `:Subject` 的抽取类型**只有 `ORG`**（`_SUBJECT_ENTITY_TYPE = "ORG"`）。
- `kg/builder.py:624` 附近：`tax_id` / `region_code` / `id_type` / `id_hash` **一律写 `None`**（不拿名字凑统一社会信用代码）。
- `:Phone` / `:Invoice` / `:Voucher` / `:Contract` 的建图代码 **零命中**；`db/models.py:265-267` 已登记
  「spec 全集还含 `shared_phone` / `cycle` / `amount_mismatch`，依赖这些节点（**Sprint 9 批次 B**）」。

⇒ spec §3 验收 1 的「**税号** + 名称 + 地址三字段对齐 ≥ 0.95」里，**税号维度当前无真源**。
⚠️ 需裁决：① 由四源摄入链写入 `tax_id`（结构化 CSV 天然有税号，最正）；② 或显式降级为「名称 + 地址」两字段并在验收写明。

### C0-3 `unaligned_subjects`：表已建、**零写入**（原判断属实）

- 落点：`db/models.py:396` `class UnalignedSubject` + 迁移 `00f44b912817:226-240`（含 `ck_unaligned_subjects_status` 与三个 `org_id` 打头索引）。
- 全 `backend/` 检索 `unaligned` 共 8 处命中 = **模型 + 迁移 + 注释**，**无任何写入方**。
- 状态枚举已就位：`UNALIGNED_SUBJECT_STATUS_VALUES = ("pending","aligned","ignored")`（`models.py:277`）。
- 承接登记号 **S7.2-1**：`backend/CODEBUDDY.md:82` 与 `specs/m4-affiliation-detection.md:204` **两边一致**，不用再找；
  m4 §6 原话：「刻意留空而非塞假数据」。
- ⚠️ 需裁决：m4 §4.5 **没有对应读端点**（spec §5.5 四端点无 unaligned）。写进去没人读 ⇒ 又是一张死表。
  要么加读端点（进契约，属范围变更），要么在 proposal 写明「只写、供人工导出 / 后续批次消费」。

### C0-4 `entity_merge_candidates`：**确实不存在**

- 全 `backend/` 零命中（仅 docs / specs / changes 提及）；定义 = `specs/m2-extract-kg.md` §4.5（6 字段 + `status` 四值）。
- 阈值（m2 §3 验收 3）：**≥ 0.90 自动合并** / **0.70–0.90 人工队列** / **< 0.70 独立**。
- 承接登记号 **S6.2-2**（`specs/m2-extract-kg.md:252`）→ **S9 批次 D**。
- 两个决定工作量的前置事实：
  1. `:Entity` 的 id 是 `ent_<hex>`，**每次抽取都变**（`changes/Sprint9/tasks.md` 降级登记）⇒ 跨文档同一实体是两个节点，
     通用 `[:RELATION]` 层的 `(head, relation_type)` **无从匹配**（这也是本期时态仲裁只对 M4 主体层生效的原因）。
  2. **R11**：同一 `kg_version` 混住两类节点——CSV 派生（`NAMESPACE:ID`）与 span 抽取碎片（「加班」「第七条」）。
     ⇒ 按名字/属性做相似度会**跑在噪声上**。

⇒ 开工必须先定「对哪一类 id 做消解」（建议：只对**稳定 id 形态**做，span 碎片按 R11 先过滤），否则算法产出无意义。

### C0-5 `applied` 口径：**可调和，但 O-2 的「契约同步 5 步」在当前是空转**

| 原文 | 位置 |
|---|---|
| 「`applied` = M6 前向预留值；**M2 实现阶段（含 Sprint 9）不落该值**」 | `specs/m2-extract-kg.md:132-138` |
| 「S9 建表当日**一并改 Pydantic 枚举** → `export_openapi.py` → `gen:api`」（决议 **O-2**） | `docs/v2.0.0-ship-backward-plan.md:59` 与 `:173` |

- 调和结论（与 `tasks.md` C0 的猜测一致）：`applied` 是**枚举值**不是字段 ⇒
  「Pydantic 枚举加 `applied`」与「运行时不写该值」**可以同时成立**。
- **但实测新发现**：`contracts/openapi.yaml` 里 `merge` / `entity_merge` **零命中** ⇒
  该表**没有任何契约落点**（无端点暴露它）。只建表 + 加枚举而不新增端点时，
  `export_openapi.py --check` **无 diff**、`gen:api` 也无 diff ⇒ O-2 的第 2–4 步是空转；
  要让它产生 diff 就得**新增端点**（范围蔓延，且与 CODEBUDDY「预留不进契约」同向冲突）。
- ⚠️ 需裁决：S9 **只建表 + Pydantic 枚举加 `applied`（运行时不写）**，契约侧零改动；
  O-2 的契约同步 5 步留到 M6（S12）真有端点时再走，并在本批次 proposal 写明该偏离。

## 2. C0 之外的新发现（影响批次 C 的排序与验收）

- **D-1 演示域 ≠ 四源域**：active `attendance-demo-v1` 是**考勤域**（EMPLOYEE / POSITION / WORK_TIME_SYSTEM /
  POLICY_CLAUSE / OVERTIME …），四源是**金融域**。⇒ 批次 C 的产出**不会出现在当前演示库**里。
  ⚠️ 需裁决：四源用**合成数据**在**独立 org / 独立 kg_version**上做（不动演示库，无不可逆代价，
  与 plan §16.3 降级预案 1「用合成数据冻结 schema」一致）；演示侧维持考勤域不变（与 **R20 / R21** 话术同源）。
- **D-2 疑点类型常量只有 3 类**：`SUSPICION_TYPE_VALUES = ("shared_legal_rep","shared_address","missing_check_in")`
  （`db/models.py:259-274`；第三类是 S9.5 考勤域新增）。spec 全集 5 类。
  扩 3 类须同步改：本常量 + `ck_affiliation_suspicions_type` + `schemas/affiliation.py::SuspicionType`
  + **契约枚举** + Alembic 迁移（`models.py:270-273` 的「无 Alembic」备注已过时——S9.7 已引入）。
- **D-3 「三类算法」与现有两跳规则的关系必须先定义**：`graphs.py:358-368` / `384-394` 两条 Cypher
  已经是「共享法人 / 共享地址」。若把 spec 的「共享邻居」直接映射成这两条，就踩中
  plan §16.2 验收第 2 条明令禁止的「三类只实现一类后改名」。
  ⇒ 批次 C 必须先写清**三类各自判据 + 可区分的 `suspicion_type` 输出**，再写代码。
- **D-4 待真机核实（本轮未起 Neo4j）**：`attendance-demo-v1` 里是否**存在** `:Subject` / `:LegalPerson` / `:Address`
  节点——考勤图由 `import_to_neo4j` 按 mapping 建、**不经 LLM 抽取**（而主体层只由抽取产生，见 C0-2）⇒ 很可能为 0。
  这决定 `/affiliation/detect` 在演示库现在是「0 疑点」还是「501」，也决定批次 C 是「新建」还是「接在现有主体层上」。
  建议开工首日 ¥0 跑一次 `MATCH (n:Subject) RETURN count(n)` 再定。

## 3. 建议的批次切分（供裁决）

| 批次 | 内容 | 依赖 |
|---|---|---|
| **C1** | 四源 schema 冻结（合成数据）+ 确定性摄入链（不经 LLM）+ `unaligned_subjects` 写入方 | 先冻结后写算法（plan §20 R14 纪律） |
| **C2** | 补齐 `:Phone` / `:Invoice` / `:Voucher` / `:Contract` + 三类算法（判据先定，见 D-3）+ `amount_mismatch` | C1 |
| **C3** | `entity_merge_candidates` + 消解（含 R11 噪声过滤口径，见 C0-4） | C1 / C2 产出的稳定 id |

顺序不可换：**C1 → C2 → C3**。

## 4. 本轮未做 / 未核实（不伪装）

- 未起 Neo4j、未跑任何 Cypher 或真机点验（D-4 待核）；
- `contracts/openapi.yaml` **未读全文**，只按关键字（`merge` / `entity_merge`）检索；
- 未读 `backend/scripts/ingest_attendance_csv.py` 全文（只确认它是唯一 CSV 摄入链 + 被 mapping 驱动）；
- 未动代码 / 契约 / 演示库 / 未打 tag / 未归档。
