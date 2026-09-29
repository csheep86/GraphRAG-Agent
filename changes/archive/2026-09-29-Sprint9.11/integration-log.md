# Sprint 9.11 · 批次 C1 实测证据

> 时间：2026-09-29 · 应用版本 **1.4.2**（未 bump，`v1.5.0` 留给 S9 收尾）· LLM 调用 **¥0**（确定性，不经 LLM）

## 1. 干跑（--dry-run，不连库）

```
语料规模   : 供应商 20 / 发票 60 / 凭证 30
待对齐 90 行：命中 86 / 未对齐 4 ⇒ 成功率 0.9556（判据 ≥ 0.95）
命中级别   : {'tax_id': 79, 'name': 6, 'address': 1}
未对齐因   : {'tax_id_missing': 1, 'name_mismatch': 2, 'multiple_candidates': 1}
    - invoices.csv[FP2026-0005] 未知供应商甲 → tax_id_missing
    - invoices.csv[FP2026-0012] 北京新联达科技有限公司 → name_mismatch
    - invoices.csv[FP2026-0023] 北京恒信达科技公司 → multiple_candidates 候选 [S001, S002]
    - vouchers.csv[PZ2026-0008] 北京恒信达科技（集团）有限公司 → name_mismatch
规范化结果 : 主体 20 / 发票 60 / 凭证 30 / 关系 86
证据层     : Document 3 / Chunk 110 / MENTIONS 110
```

三级**都被用到**（tax_id 79 / name 6 / address 1）——不是"只实现了第一级"就交差。

## 2. 真机（Neo4j + PG）

```
Neo4j 连接 : bolt://localhost:7687 (db=neo4j)
[1/3] KgVersion affiliation-demo-v1 -> writing
[2/3] MERGE 主体 20 / 发票 60 / 凭证 30
[2/3] MERGE 关系 ISSUED 57 / POSTED_IN 29
[self-check] 回读 Entity=110 / Relation=86      ← 与提交量一致，无静默丢失
[evidence] Document 3 / Chunk 110 / MENTIONS 110
[3/3] KgVersion -> active（耗时 2879 ms）

----- 可用性回读（入图 ≠ 可查）-----
subjects 20 / invoices 60 / vouchers 30 / issued 57 / posted_in 29 / chunks 110 / mentions 110

[PG] unaligned_subjects 写入 4 行（S7.2-1 偿还）
[PG] affiliation-demo-v1 -> ready（实体 110 / 关系 86）
```

PG 侧实际落库（逐行可核）：

| raw_name | reason | candidates | status |
|---|---|---|---|
| 未知供应商甲 | `tax_id_missing` | null | pending |
| 北京新联达科技有限公司 | `name_mismatch` | null | pending |
| 北京恒信达科技公司 | `multiple_candidates` | `[SUBJECT:…T2W3XX, SUBJECT:…T2W4XX]` | pending |
| 北京恒信达科技（集团）有限公司 | `name_mismatch` | null | pending |

## 3. 演示库零影响（前后对照）

| 指标 | 前 | 后 |
|---|---|---|
| 演示 org `attendance-demo-v1`（PG `kg_versions`） | ready / ent **2625** / rel **3576** | ready / ent **2625** / rel **3576** |
| `kg_versions` 行数 | 3（演示 org） | 4（+ 独立 org 的 `affiliation-demo-v1`） |

本批次写入**只发生在** `org=5dea8f62-…`（合成数据专用 org）与 `kg_version=affiliation-demo-v1`；
`demo/attendance/` 与演示 org 的文档 / 图谱**一行未动**，无不可逆操作。

## 4. C0 遗留问题的真机答案（D-4）

- `MATCH (n:Subject) RETURN count(n)` = **20**，且全部属于 `affiliation-demo-v1`
  ⇒ **考勤演示图里原本没有 `:Subject`**（主体层只由 M2 抽取产生，考勤图是结构化入图）。
  结论：**C2 的主体层是"新建"**，不是"接在现有主体层上"。

## 5. 观察项（登记，不掩饰）

- Neo4j `:Entity[attendance-demo-v1]` = **2764**，而 PG `kg_versions` 记 **2625**
  ⇒ 两数**不同源**（Neo4j 含 M2 抽取增量 / 历史节点）。**非本批次引入**（本批次未写该版本），
  与已知的 R21「两数都真、治理走话术」同源，此处只登记不改代码。

## 6. 门禁（全绿）

- `uv run ruff check .` / `ruff format --check .` → All checks passed / 167 files formatted
- `uv run pytest -q` → **592 passed, 3 skipped**（含新增 15 条对齐单测）
- `uv run python scripts/check_seams.py` → **ERROR 0 / WARN 0 / OK 10**
- `uv run python scripts/export_openapi.py --check` → 无 diff（**契约零改动**，与裁决 D-B/D-C 一致）
- 前端 `npm run lint` / `npx tsc --noEmit` / `npm run gen:api` → 通过，**生成物无 diff**

## 7. 本批次未做（留给后续批次）

- 三类算法 / `amount_mismatch`（**C2**）——本批次未写一行算法代码（守 R14）
- `entity_merge_candidates` 与实体消解（**C3**），含 `applied` 枚举（裁决 D-C：届时加枚举、运行时不写值、契约零改动）
- `unaligned_subjects` 读端点 → 缺口 **S9.11-1**
- 合同 PDF / `:Contract` / 三方金额比对 → **C2**
