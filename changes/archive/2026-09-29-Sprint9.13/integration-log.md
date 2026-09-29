# Sprint 9.13 批次 C3 集成日志（实体消解）

> 判据：`specs/m2-extract-kg.md` **§4.5.1**（先冻结 → 后写代码）。
> 任务卡：本目录 `tasks.md`；提案：`proposal.md`。日期 2026-09-29。

## 1. 真机跑通（`uv run python scripts/ingest_affiliation_sources.py --purge`）

```
----- 四源主体对齐（税号 → 名称 → 地址）-----
  待对齐 90 行：命中 86 / 未对齐 4 ⇒ 成功率 0.9556（判据 ≥ 0.95）   ← S9.11 判据未被推翻
  命中级别 : {'tax_id': 79, 'name': 6, 'address': 1}
  未对齐因 : {'tax_id_missing': 2, 'multiple_candidates': 1, 'name_mismatch': 1}

----- 实体消解（判据 specs/m2 §4.5.1）-----
  候选 5 条：{'human_review': 4, 'auto_merged': 1}
  终态对齐 : 命中 87（含消解合并 1）/ 未对齐 3 ⇒ 率 0.9667
    - auto_merged  invoices.csv[FP2026-0012] 武汉市长江智联科技有限公司
                   → SUBJECT:91420111MA08J2D8FX（S009 武汉长江智联科技）sim=0.9412
    - human_review SUBJECT:…T2W3XX ↔ SUBJECT:…T2W4XX      sim=0.8500  tax_conflict=True   ← N1
    - human_review RAW:invoices.csv:FP2026-0023 ↔ …T2W3XX sim=1.0000  multi_candidate     ← N2
    - human_review RAW:invoices.csv:FP2026-0023 ↔ …T2W4XX sim=1.0000  multi_candidate     ← N2
    - human_review RAW:vouchers.csv:PZ2026-0008 ↔ …G9B6DX sim=0.8500  tax_conflict=True   ← N1

图（可用性回读）: subjects 21 / invoices 60 / vouchers 30 / issued 58 / posted_in 29
                 / chunks 128 / mentions 138 / shares_holder 10 / party_to 16
[PG] unaligned_subjects 写入 4 行（其中 1 行 status=aligned）
[PG] entity_merge_candidates 写入 5 行（S6.2-2 偿还）
```

**合并真的进了图**：`issued` 由 S9.12 的 **57 → 58**——被合并的那条发票现在建出了
`(:Invoice)-[:ISSUED]->(:Subject)` 边（合并前它因为未对齐而不建边）。这是"摄入时归一"
生效的直接证据，不是靠 `auto_merged` 这一行字宣称的。

## 2. PG 回读（`entity_merge_candidates` 5 行，逐行可核）

| status | similarity | left | right | signals |
|---|---|---|---|---|
| `auto_merged` | 0.9412 | `RAW:invoices.csv:FP2026-0012` | `SUBJECT:91420111MA08J2D8FX` | `name_sim=0.941176, tax_conflict=False` |
| `human_review` | 1.0000 | `RAW:invoices.csv:FP2026-0023` | `SUBJECT:91110108MA01T2W3XX` | `multi_candidate=True`（N2） |
| `human_review` | 1.0000 | `RAW:invoices.csv:FP2026-0023` | `SUBJECT:91110108MA01T2W4XX` | `multi_candidate=True`（N2） |
| `human_review` | 0.8500 | `SUBJECT:91110108MA01T2W3XX` | `SUBJECT:91110108MA01T2W4XX` | `name_sim=1.0, tax_conflict=True`（N1 封顶） |
| `human_review` | 0.8500 | `RAW:vouchers.csv:PZ2026-0008` | `SUBJECT:91120116MA10G9B6DX` | `name_sim=0.941176, tax_conflict=True`（N1 封顶） |

`unaligned_subjects` 4 行：`武汉市长江智联科技有限公司` → **aligned**（消解合并），
其余 3 行 `pending`（`未知供应商甲` / `北京恒信达科技公司` / `天津市滨海华元机械有限公司`）。

## 3. 三条否决在真机上各司其职（不是只有"能合并"被验证）

- **N1 挡住了两次**：`name_sim=1.0`（S001/S002 同名不同税号）与 `name_sim=0.94`
  （PZ2026-0008）都被压到 0.85 ⇒ `human_review`。**若判据没有 N1，这两条会被自动合并掉**——
  而它们恰恰是"看着像一家、其实是两家"的典型，并掉就是抹掉关联方。
- **N2 挡住一次**：FP2026-0023 同时像 S001 / S002（两条都 1.0）⇒ 全部降级、不合并。
- **误并 0**：脚本里有机械判据（任何 `SUBJECT:… ↔ SUBJECT:…` 的 `auto_merged` ⇒ 退出码 1），
  本次无触发。

## 4. 门禁

| 项 | 结果 |
|---|---|
| `uv run ruff check .` / `ruff format --check .` | 通过（新文件已格式化） |
| `uv run pytest -q` | **611 passed, 3 skipped**（S9.12 为 592 ⇒ +19 条） |
| `uv run python scripts/check_seams.py` | ERROR 0 / WARN 0 / OK 10 |
| `uv run python scripts/export_openapi.py --check` | **无 diff**（本批次契约零改动，符合裁决 D-E） |
| 迁移基线 | `test_migrations_baseline.py` 绿（新表 `b3e5a1c70d42` 已纳入） |

## 5. 本批次未做 / 已登记

- **S9.13-1**：`left/right_entity_id` 为 TEXT 而非 spec 起草时的 UUID（理由见 spec §4.5 注脚）；
- **S9.13-2**：`human_review` **无读端点**（裁决 D-G，同 S9.11 的 D-B）+ `:Entity` 通用层消解不做
  （id = `ent_<uuid>` 不稳定，需先解决跨文档 id 稳定性）；
- `applied` / `pending` / `rejected` **只进枚举、运行时不写**（裁决 D-E / D-F）；
- **已入图的历史节点不做事后物理合并**：本批的"合并"发生在**摄入时**，重跑 `--purge` 才生效。
