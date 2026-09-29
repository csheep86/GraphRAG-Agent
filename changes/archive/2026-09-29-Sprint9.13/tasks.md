# Sprint 9.13 · 批次 C3 任务卡（主体层实体消解）

> 提案见本目录 `proposal.md`；判据冻结在 `specs/m2-extract-kg.md` **§4.5.1**。
> 硬纪律：**判据没冻结不许写代码**（plan §20 R14）——§4.5.1 已冻结，可开工。

## A 冻结 ✅

- [x] 判据落 `specs/m2-extract-kg.md` §4.5.1（范围 / blocking / 信号 / 三条否决 / 三档 / 真机判据 / 不做的事）
- [x] 列类型偏离（TEXT vs UUID）登记 **S9.13-1** 于 §4.5 表下
- [x] 八条裁决 D-A ~ D-H 落 `proposal.md` §2

## B 语料植入（D-H：改名不增行）

- [x] `invoices.csv[FP2026-0012]` → `武汉市长江智联科技有限公司` + **清空税号**（`auto_merged` → S009）
- [x] `vouchers.csv[PZ2026-0008]` → `天津市滨海华元机械有限公司` + **保留税号**（N1 反例 ⇒ `human_review`，不许自动合并）
- [ ] 断言 S9.11 判据**不被推翻**：总数仍 90、未对齐仍 4、消解前率仍 0.9556

## C 消解器（纯函数、零 LLM）

- [x] `backend/app/services/kg/entity_resolution.py`：`name_similarity` / `score_pair` / `classify` / `generate_candidates`
- [x] 信号只取判据里的：名称（`max(jaccard₂, ratio)`）+ 结构（同法人 / 同电话 / 同址，每项 +0.05、上限 +0.10）
- [x] 否决：N1 税号冲突封顶 0.85 / N2 多候选降 `human_review` / N3 同税号不成对
- [x] `< 0.70` **不落表**

## D 建表 + 迁移

- [x] `EntityMergeCandidate`（字段逐字对齐 §4.5；`left/right_entity_id` 为 TEXT，见 S9.13-1）
- [x] `status` CHECK 含 `pending / auto_merged / human_review / rejected / applied`
      （**`applied` 只进枚举、运行时不写**，裁决 D-E）
- [x] 迁移 `b3e5a1c70d42`（`down_revision = 9c1b7d2ae4f3`）；`test_migrations_baseline.py` 绿

## E 摄入链接入

- [x] 对齐后跑消解：`auto_merged` ⇒ 边指向 canonical 节点（**摄入时归一**，不是事后改写图）
      —— 真机 `issued` 57 → **58**，即被合并的那条发票现在真的建出了边
- [x] 候选落 `entity_merge_candidates`（三档）+ `unaligned_subjects.status` → `aligned`
- [x] 终态对齐率 = (命中 + 自动合并) / 总数 = **87/90 = 0.9667**，**未达 0.95 退出码 1**（不调阈值凑数）

## F 判据测试 + 真机

- [x] `backend/tests/test_entity_resolution.py`（14 条）：三档边界、N1/N2/N3、结构分上限、`<0.70` 不落表
- [x] 真机：候选三档可核（`auto_merged` **1** / `human_review` **4** 含 N1 反例 / 误并 **0**）+ 终态 87/90
- [x] `integration-log.md` 留证（PG 逐行回读 + 三条否决各自落点）

## G 门禁与文档

- [x] `ruff check` + `ruff format --check` / `pytest -q` **611 passed, 3 skipped** /
      `check_seams.py` **ERROR 0 / WARN 0** / `export_openapi.py --check` **无 diff**
- [x] `specs/m2` §6 **S6.2-2** 标偿还 + 新增 **S9.13-1 / S9.13-2** 登记；矩阵 §3.1 / §3.4 **M2-3** 同步
- [x] `changes/Sprint9/tasks.md` 批次 C3 勾选；`demo/affiliation/README.md` 语料改动说明
- [ ] `docs/sprint-calendar.md` 状态行（S9 → 批次 C 全完成，待收尾打包）——**留给 S9 收尾批次**
