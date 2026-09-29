# Sprint 9.13 · 批次 C3：主体层实体消解（`entity_merge_candidates`）

> 承接 `changes/Sprint9/tasks.md` 批次 C3 与 Sprint 9.11 裁决 **D-C**。
> 判据已冻结于 **`specs/m2-extract-kg.md` §4.5.1**（先冻结、后写代码，plan §20 **R14**）。
> 真机证据留本目录 `integration-log.md`。

## 1. 为什么做

`specs/m2-extract-kg.md` §3 验收 3 要求实体消解器输出合并候选并按三档处置，
S9 的 C0 勘察（2026-09-29）实测：

| 事实 | 证据 |
|---|---|
| `entity_merge_candidates` **表不存在** | C0 勘察第 4 条；登记号 **S6.2-2**（`specs/m2` §6） |
| 抽取侧「同一实体重复 3 份」（6 → 18 节点） | S6 收尾登记 **S6.2-2**，至今未偿还 |
| 该表是 **S12 的前置** | `v2.0.0-ship-backward-plan` §4 / §8：S9 实体消解不落地 ⇒ M6 本体校正 GUI 无输入 |

⇒ C3 是 Sprint 9 的**最后一块**，也是关键路径上「一堵全堵」的节点。

## 2. 裁决（先裁决，后动手）

| # | 争议 | 裁决 | 理由 |
|---|---|---|---|
| **D-A** | 候选对在哪一层生成 | **`:Subject` 主体层** | 主体 id = `SUBJECT:<税号>` 跨文档稳定；`:Entity` 通用层 id = `ent_<uuid>` 每次抽取都变 ⇒ 无从配对（降级登记见 `specs/m4` §6） |
| **D-B** | `left/right_entity_id` 类型 | **TEXT**（偏离 spec 的 UUID），登记 **S9.13-1** | 图侧实体 id 是稳定字符串，**没有 UUID 可存**；硬按 UUID 建列 ⇒ 写不进去或另造假映射 |
| **D-C** | 税号不同能不能自动合并 | **不能**（封顶 0.85，永不 `auto_merged`） | 不同统一社会信用代码 = 法律上不同主体；自动并掉 = 抹掉 M4 要找的关联方。与 §3 验收 3 举例不冲突（举例是无 id 场景） |
| **D-D** | 同一 raw 有多个 ≥0.90 候选 | **全部降 `human_review`、不合并** | 沿用 S9.11 D-B：并错两家比漏并一家危险 |
| **D-E** | `applied` 枚举 | Pydantic 枚举**加值**、运行时**不写**、契约**零改动** | S9.11 裁决 D-C 已定；`openapi.yaml` 里 `merge` 零命中，不为"走出 diff"造端点 |
| **D-F** | `< 0.70` 的候选 | **不落表**（`pending` / `rejected` 本阶段无写入方） | 「保持独立」= 没有候选行；写 `pending` 等于宣称有人会处理 |
| **D-G** | `human_review` 人工队列 | **只写表、不读端点、不动图**，缺口 **S9.13-2** | S9.11 D-B 同口径：无 UI 的队列不造参数 |
| **D-H** | 语料怎么植入样本 | **改现有 2 行的名字，不增行** | 增行会把 S9.11 的判据（总数 90 / 未对齐 4 / 0.9556）推翻；改名不动总数 ⇒ C1 的断言仍然成立 |

### 2.1 语料改动（D-H，逐行可核）

| 文件 | 行 | 原 `counterparty_name` | 改为 | 税号 | 期望档位 |
|---|---|---|---|---|---|
| `invoices.csv` | FP2026-0012 | 北京新联达科技有限公司 | **武汉市长江智联科技有限公司** | **清空** | `auto_merged` → S009（`name_sim ≈ 0.94`，无税号冲突、唯一候选） |
| `vouchers.csv` | PZ2026-0008 | 北京恒信达科技（集团）有限公司 | **天津市滨海华元机械有限公司** | 保留（与主数据不同） | **N1 反例**：`name_sim ≈ 0.89` 但税号冲突 ⇒ 封顶 0.85 ⇒ `human_review`，**不得**自动合并 |

**为什么一条清税号、一条留税号**：恰好把 N1 的**两个方向**都做成真机可核对——
清税号那条走通 `auto_merged`（证明机制可用），留税号那条被 N1 挡住（证明机制**不会**乱并）。
只做前者等于自证"能合并"，不做后者等于没验证"该挡的挡得住"。

两行的规范化名与主体**不完全相同**（"武汉市…" / "天津市…" 多一字）⇒ S9.11 的三级对齐
**照旧未命中**（总数仍 90、未对齐仍 4、率仍 0.9556，**C1 判据不被推翻**）。保留的另两行
继续充当反例：`未知供应商甲`（< 0.70，不落表）、`北京恒信达科技公司`（多候选 ⇒ 降级）。

## 3. 改什么

| # | 改动 | 落点 |
|---|---|---|
| **A** | 判据冻结 | `specs/m2-extract-kg.md` **§4.5.1**（已完成）+ §4.5 列类型偏离注脚（已完成） |
| **B** | 语料植入（D-H） | `demo/affiliation/invoices.csv` / `vouchers.csv` 各 1 行 |
| **C** | 消解器（纯函数、零 LLM） | `backend/app/services/kg/entity_resolution.py` |
| **D** | 建表 + 迁移 | `backend/app/db/models.py`（`EntityMergeCandidate`）+ `migrations/versions/`（`down_revision = 9c1b7d2ae4f3`） |
| **E** | 摄入链接入（合并 + 落候选 + 更新 `unaligned_subjects.status` + 终态对齐率） | `backend/scripts/ingest_affiliation_sources.py` |
| **F** | 判据测试 | `backend/tests/test_entity_resolution.py` |

## 4. 风险与对策

| 风险 | 对策 |
|---|---|
| 自动并错（把两家真公司并成一家） | N1 税号冲突封顶 + N2 多候选降级；真机断言「误并 0」 |
| 结构信号诱导误并（同法人 / 同电话） | 结构分**上限 +0.10** 且 `name_sim < 0.70` 时**不产生候选** |
| 表变死表（写了没人读） | 缺口 **S9.13-2** 显式登记，不假装闭环 |
| 污染演示 org | 摄入器强制 `--org` 新 org + 激活只在该 org 内；`integration-log` 留前后 `GET /graph/overview` 对照 |

## 5. 验收判据（可核）

- [ ] §4.5.1 判据可读，且代码实现**只**用判据里写明的信号
- [ ] 新表 + 迁移就位（`test_migrations_baseline.py` 绿）
- [ ] 真机：候选表三档可核 —— `auto_merged` **1** / `human_review` ≥ 1（含 N1 反例）/ 误并 **0**
- [ ] 真机：终态对齐率 **87/90 = 0.9667**（≥ 0.95），未对齐行 `status` 由 `pending` → `aligned`
- [ ] 门禁全绿：`ruff check` + `ruff format --check` / `pytest -q` / `check_seams.py` / `export_openapi.py --check`
- [ ] 文档：`specs/m2` §6 **S6.2-2** 偿还、`docs/acceptance-traceability-matrix.md` §3.4 同步、`changes/Sprint9/tasks.md` 勾选
