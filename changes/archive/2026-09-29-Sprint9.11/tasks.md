# Sprint 9.11 · 批次 C1 任务卡（四源 schema 冻结 + 摄入链 + 主体对齐）

> 承接 `changes/Sprint9/c0-recon.md`（C0 勘察结论）与 `dev-doc-status.md` **S7.2-1**（`unaligned_subjects` 空表）。
> 证据链见本目录 `integration-log.md`（2026-09-29 已真机跑通）。
> 硬纪律：**A 没冻结完，不许开始写 C / D 的代码**（plan §20 R14）——已遵守。

## 1. A 四源 schema 冻结（**先冻结**）✅

- [x] `specs/m4-affiliation-detection.md` **新增 §4.6「四源 CSV schema（S9.11 冻结）」**：
      供应商主数据 / 发票 / 凭证三张表的**列名、必填、校验规则、税号格式口径**
- [x] 对齐规则三级写入同一节：**税号 → 规范化名称 → 规范化地址**（裁决 D-A）
- [x] 未对齐的三种 `reason` 取值与 §4.5 对齐（税号缺失 / 名称不一致 / 多候选）
- [x] spec §6 缺口表：**S7.2-1 → 已偿还（S9.11）**，新增 **S9.11-1**（无读端点）
- [x] 口径修正（实现期发现）：`counterparty_tax_id` **列必存、值可缺失**——「抬头没写税号」
      是 §4.5 的真实业务情形；**有值却格式非法**才是语料错误（§4.6.2 已登记）

## 2. B 合成语料（独立 org，¥0）✅

- [x] `demo/affiliation/`：`suppliers.csv`（20）/ `invoices.csv`（60）/ `vouchers.csv`（30）
- [x] **刻意植入 4 条未对齐样本**：税号缺失 / 名称不在主数据 / 同名多候选 / 地址异写
- [x] 目录内 `README.md` 明写「合成数据、仅用于 M4 验收、非真实客户数据」（**R9**）
- [x] **不动** `demo/attendance/` 任何文件

## 3. C 摄入器（确定性，不经 LLM）✅

- [x] `backend/scripts/ingest_affiliation_sources.py`：
      供应商主数据 → `:Entity:Subject`（**写 `tax_id`**）／发票 → `:Entity:Invoice` + `ISSUED`
      ／凭证 → `:Entity:Voucher` + `POSTED_IN`（关系方向逐字照 §4.2）
- [x] 按 **R14** 纪律落 `Document` + `Chunk` + `MENTIONS` 原文证据边（110 / 110）
- [x] chunk id 形如 `chunk-<12 hex>`（**R16**，单测钉死：形态不对 ⇒ 引用被静默丢弃）
- [x] 新 org（`5dea8f62-…`）+ 新 `kg_version`（`affiliation-demo-v1`），只在新 org 内激活；
      演示 org 的 active `attendance-demo-v1`（ent 2625 / rel 3576）**前后一致**
- [x] 不引入 mapping 抽象层（**R15**）
- [x] 双标签（`:Entity:Subject` 等）理由写入 §4.6.5：算法 Cypher 只认语义标签，
      读侧与证据回溯只认 `:Entity`——只打语义标签会重演「进得了库、查不出来」

## 4. D 对齐器 + `unaligned_subjects` 写入（偿还 S7.2-1）✅

- [x] 三级对齐：税号 → 规范化名称 → 规范化地址（真机 79 / 6 / 1）；命中即复用 canonical `:Subject`
- [x] 未对齐落 `unaligned_subjects`：`raw_name` / `source_doc_id` / `reason` / `candidates` / `status=pending`
      （真机 4 行，逐行可核）；**多候选不自动合并**
- [x] **不新增读端点、不动契约**（裁决 D-B）；缺口登记 **S9.11-1**
- [x] 对齐率 **86/90 = 0.9556 ≥ 0.95**；未达标即脚本退出码 1（不调阈值凑数）

## 5. E 判据与门禁 ✅

- [x] `backend/tests/test_affiliation_alignment.py`（15 条）：对齐率、三种 reason、三级都被用到、
      税号优先于名称、多候选不合并、chunk id 形态、语料违规必报出、税号可空但非法必报错
- [x] 真机跑通 + `integration-log.md` 留证（节点/边数、对齐率、`unaligned_subjects` 行数、
      演示 org 前后对照）
- [x] Alembic：**无迁移**（本批次不新建表，`unaligned_subjects` 已存在）
- [x] `uv run ruff check .` + `uv run ruff format --check .` → 通过
- [x] `uv run pytest -q` → **592 passed, 3 skipped**
- [x] `uv run python scripts/check_seams.py` → ERROR 0 / WARN 0
- [x] `uv run python scripts/export_openapi.py --check` → **无 diff**
- [x] 前端 `npm run lint` + `npx tsc --noEmit` + `npm run gen:api` → **无 diff**

## 6. 不做什么（划界，已遵守）

- 不做三类算法 / `amount_mismatch`（**C2**）——本批次未写算法代码
- 不建 `entity_merge_candidates`、不落 `applied`（**C3**）
- 不动契约、不新增端点、不改 `app_version`（仍 1.4.2）
- 不碰 `:Phone` / `:LegalPerson` 哈希字段（随 C2 的 `shared_phone`）
- 不跑 `POST /affiliation/detect`、不上传任何文件到演示 org（无 DELETE 接口，不可逆）

## 7. 真机核实（C0 的 D-4）✅

- [x] `MATCH (n:Subject) RETURN count(n)` = **20**，全部属于 `affiliation-demo-v1`
      ⇒ 考勤演示图里**原本没有 `:Subject`** ⇒ **C2 的主体层是"新建"**，不是接入现有主体层
