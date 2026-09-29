# Sprint 9.11 —— 批次 C1：四源 schema 冻结 + 结构化摄入链 + 主体对齐

> 登记日期：2026-09-29。**S9 批次 C 的第一刀**（C1 → C2 → C3，顺序不可换）。
> 前置勘察：[`../../Sprint9/c0-recon.md`](../../Sprint9/c0-recon.md)（只读结论，开工前必读）。
> 定性：**不改演示路径**（演示库仍是考勤域 `attendance-demo-v1`），本批次只补 S9 的 M4 验收缺口。

## 1. 为什么做

`specs/m4-affiliation-detection.md` §3 验收 1 要求「四源（合同 PDF + 发票 / 凭证 / 供应商主数据 CSV）
主体对齐，成功率 ≥ 0.95，未对齐进 `unaligned_subjects`」。C0 勘察实测（**不是猜测**）：

| 事实 | 证据 |
|---|---|
| 四源摄入入口**不存在** | `backend/scripts/` 只有考勤两个脚本；`demo/` 只有 `attendance/` |
| `:Invoice` / `:Voucher` / `:Contract` / `:Phone` 建图代码**零命中** | `db/models.py:265-267` 已登记「依赖 Sprint 9 批次 B」 |
| `:Subject.tax_id` **恒 `None`** | `kg/builder.py:624` 附近（抽取侧拿不到税号，不拿名字凑） |
| `unaligned_subjects` **表建了、零写入** | 登记号 **S7.2-1**（`backend/CODEBUDDY.md:82` + m4 §6:204） |

⇒ 所以批次 C 的**第一件事不是写算法，是先把"对齐"这件事的数据真源建出来**——
plan §20 **R14** 的纪律也是「schema 先冻结、冻结后才写算法」。

## 2. 三条口径裁决（本批次按此执行，写在 proposal 里以便被推翻）

| # | 争议 | 裁决 | 理由 |
|---|---|---|---|
| **D-A** | 税号真源（`c0-recon.md` §1 C0-2 的 ⚠️） | **由四源摄入链写入 `tax_id`**：供应商主数据 CSV 提供 `tax_id` / `name` / `address` 作为 canonical 主体；对齐按 **税号 → 规范化名称 → 规范化地址** 三级递减 | spec §3 验收 1 明写「基于供应商主数据**税号** + 名称 + 地址三字段匹配」；结构化 CSV 天然有税号，是唯一不靠猜的真源 |
| **D-B** | `unaligned_subjects` 读端点（`c0-recon.md` §1 C0-3 的 ⚠️） | **本批次只写不读**，不新增端点、不动契约；缺口登记为 **S9.11-1** | m4 §5.5 四端点里没有它，新增端点 = 范围变更；对齐率判据由**测试断言**（合成集已知总数）给出，不需要 UI |
| **D-C** | `applied` 契约同步（`c0-recon.md` §1 C0-5 的 ⚠️） | **C3 建 `entity_merge_candidates` 当日**：Pydantic 枚举加 `applied`、**运行时不写该值**、契约侧**零改动** | 实测 `contracts/openapi.yaml` 里 `merge` 零命中 ⇒ 该表无契约落点，`export_openapi.py --check` 本来就该无 diff（O-2 的第 2–4 步在此处是空转，登记偏离，不为了"走出 diff"而造端点） |

## 3. 改什么

| # | 内容 | 落点 |
|---|---|---|
| **A** | **四源 schema 冻结**：三张 CSV（供应商主数据 / 发票 / 凭证）的列名、必填、校验规则、税号格式口径 | `specs/m4-affiliation-detection.md` **新增 §4.6**（改 spec，不新增文档 ⇒ 不触发 PRD 附录 C.0 登记） |
| **B** | **合成语料**：`demo/affiliation/`（供应商主数据 ~20 行 / 发票 ~60 / 凭证 ~30，含**刻意植入**的税号缺失 / 名称别名 / 地址异写样本） | 新目录；**不动** `demo/attendance/` |
| **C** | **摄入器**：`backend/scripts/ingest_affiliation_sources.py`——确定性、**不经 LLM**；产出 `:Subject`（带 `tax_id`）/ `:Invoice` / `:Voucher` + `:ISSUED` / `:POSTED_IN`，并按 R14 纪律落 `Document` + `Chunk` + `MENTIONS` 原文证据边 | 新脚本（照 `ingest_attendance_csv.py` 先例；按 **R15** 不做配置驱动抽象） |
| **D** | **对齐器**：税号 → 规范化名称 → 规范化地址三级；命中即复用 canonical `:Subject`，三源都未命中 ⇒ 写 `unaligned_subjects`（`reason` = 税号缺失 / 名称不一致 / 多候选） | 新模块 + **S7.2-1 偿还** |
| **E** | **判据与门禁**：对齐成功率 ≥ 0.95 由测试断言（合成集总数已知，未对齐行数可核）；`unaligned_subjects` 真机有行 | `backend/tests/test_affiliation_alignment.py` + `integration-log.md` |

### 3.1 三条硬纪律（照既有教训写死）

1. **chunk id 必须是 `chunk-<12 hex>`**（**R16**）：自造 id（冒号形态）会让引用抠不出来 ⇒ 问答侧静默拒答，极难定位。
2. **独立 org + 独立 `kg_version`**：合成数据写在**新 org** 下（`affiliation-demo-v1`），**不激活**到演示 org ⇒ 演示库 active `attendance-demo-v1` 与实体 2,625 / 文档 14 **一律不变**（无不可逆代价）。
3. **确定性、不经 LLM**：结构化数据用 LLM 抽取是错配（`demo/attendance/mapping.yaml:5-7` 原话），本批次 ¥0。

## 4. 明确不做

- **不做三类算法**（连通分量 / 共享邻居 / 环路）与 `amount_mismatch` ⇒ **C2**；本批次不写一行算法代码（守 R14「先冻结后写算法」）。
- **不建 `entity_merge_candidates`** ⇒ **C3**；本批次不落 `applied`（D-C）。
- **不动契约**（预计 `export_openapi.py --check` 无 diff）：不新增端点、不加字段；若实现中确认必须改 ⇒ **停下来先改契约**再继续。
- **不碰 `:Phone` / `:LegalPerson` 的哈希字段**（spec §4.1 敏感口径）⇒ 随 C2 的 `shared_phone` 一并做。
- **不跑 `POST /affiliation/detect`**（C2 才有新疑点类型可产）；本批次只验「摄入 + 对齐」。
- 不动 `app_version`（仍 **1.4.2**；`v1.5.0` 留给 S9 收尾统一 bump + tag）。
- 不动 `demo/attendance/`、不动演示库、不上传任何文件到演示 org。

## 5. 风险与红线

| 项 | 处置 |
|---|---|
| 合成数据若被当成"真实客户数据" | 语料目录内 README 明写「合成、仅用于验收」，并沿用 **R9** 的语料标注纪律 |
| 对齐率凑数 | 判据是**未对齐行数 / 已知总数**，合成集里刻意植入未对齐样本 ⇒ 率不可能为 1.0；不做"调阈值凑到 0.95" |
| `unaligned_subjects` 变死表 | 缺口 **S9.11-1** 显式登记（无读端点），不假装已闭环 |
| 误激活到演示 org | 脚本强制校验 `org_id` 与 active 版本，激活只在新 org 内做；`integration-log` 留前后 `GET /graph/overview` 对照 |

## 6. 验收判据（可核）

- [ ] `specs/m4` §4.6 四源 schema 冻结清单可读（列名 / 必填 / 校验 / 税号格式）
- [ ] 合成语料 `demo/affiliation/` 落盘，含 ≥1 组刻意未对齐样本
- [ ] 摄入器跑通：新 org 下 `:Subject` 带 `tax_id`、`:Invoice` / `:Voucher` 节点与边数可核、chunk id 全部匹配 `chunk-<12 hex>`
- [ ] 对齐器跑通：对齐成功率 **≥ 0.95**（测试断言 + 真机行数双证），未对齐行落 `unaligned_subjects` 且 `reason` 非空
- [ ] 演示 org 的 `GET /graph/overview` 前后**完全一致**（`doc=4 / ent=2625`）
- [ ] 门禁全绿：`ruff check` + `ruff format --check` / `pytest -q` / `check_seams.py` / `export_openapi.py --check` / 前端 `lint` + `tsc` + `gen:api` 无 diff
