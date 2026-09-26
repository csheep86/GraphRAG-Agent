# Sprint 日历（v1.0.0 → v2.0.0 上线倒推排期）

> **文档编号**：sprint-calendar
> **版本**：v1.1（2026-09-21 建立；2026-09-22 修订：S5 收尾登记 + `--strict` 口径更正）
> **性质**：**日历化排期登记表**——把 `docs/v1.1.0-demo-mvp-plan.md`（v3.0）§13 的 Sprint 时长映射到具体日历日期。**范围与口径的真源仍是 plan v3.0 §4~§21 与 `docs/v2.0.0-ship-backward-plan.md`**；本文只回答"什么时候做、什么时候 tag"，冲突时以 plan v3.0 为准。
> **排期前提**：① Sprint 5 于 **2026-09-21（周一）开工**；② 执行者为 AI，**不加节假日与风险缓冲**（用户 2026-09-21 拍板："该登记该记录还是要记录好先"前一轮确认）；③ 外部依赖（MinerU / DeepSeek API）不可压缩项保留降级预案（各 Sprint §降级预案）。
> **纪律**：提前完成 → 提前验收，**不跳验收**。每个 Sprint 收尾门禁（见 §3）全绿才可打 tag。

---

## 1. 总览

```
tag v1.0.0（现状基线，Sprint 4 已收尾，黄金路径 2/7）
   │
   ├─ Demo-MVP 段：S5~S8（约 7.5 周）──────► v1.4.0【中途演示点，非交付版】
   └─ MVP 1.0 追加段：S9~S13（约 13.5 周）──► v2.0.0【PRD MVP 1.0 交付版】
合计约 21 周；交付日 ≈ 2027-02-12。
```

## 2. 逐 Sprint 日历

| Sprint | 日历区间 | 时长 | tag | 主题（详 plan §4~§20） |
|---|---|---|---|---|
| **S5** | 2026-09-21 → 2026-10-11 | 3 周 | `v1.1.0` | 真解析 + 在线建图 + 预留位（首次可演示"上传→看图"） |
| S6 | 2026-10-12 → 2026-10-20 | 1.5 周 | `v1.2.0` | 引用溯源（Chunk 证据节点 + 前端高亮；F3 首次达标；第 3 天 go/no-go） |
| S7 | 2026-10-21 → 2026-11-03 | 2 周 | `v1.3.0` | M4 疑点最小版（1 类规则算法）+ 事件出口 + 接缝 5/7/8 |
| **S8** | 2026-11-04 → 2026-11-10 | 1 周 | `v1.4.0` | 审计闭环 + 演示打磨 + 8 接缝收口（**Demo-MVP 达成【中途演示点】**） |
| S9 | 2026-11-11 → 2026-12-01 | 3 周 | `v1.5.0` | M4 完整化：四源对齐（首日 schema 冻结）+ 三类算法 + 三方金额不一致 + 实体消解 |
| S10 | 2026-12-02 → 2026-12-18 | 2.5 周 | `v1.6.0` | 证据链与多跳（`*1..3`）+ `:Chunk` 真实引用 + `confidence` 落库 + docx 解析 |
| S11 | 2026-12-19 → 2027-01-12 | 3.5 周 | `v1.7.0` | M5 完整化 + PG 切换（首日）+ RLS 全量 + RBAC 三粒度 + 内网双轨 |
| S12 | 2027-01-13 → 2027-01-29 | 2.5 周 | `v1.8.0` | M6 完整版：本体冷启动 + 校正 GUI + 增量重算 + 成本仪表盘 |
| **S13** | 2027-01-30 → 2027-02-12 | 2 周 | **`v2.0.0`** | C1~C3 实验闭环 + TBD-3/4/6/7 收敛 + **MVP 1.0 达成声明（交付版）** |

> 日期口径：区间含首尾；tag 与合并回 main 发生在区间最后一日。

## 3. 每个 Sprint 的固定节奏（SDD，决议 O-1）

| 节点 | 动作 |
|---|---|
| 开工首日 | 建 `changes/Sprint<N>.1/proposal.md` + `tasks.md`（模板 `specs/_template/`），分支 `feature/sprint-<N>` |
| 批次推进 | 先改 `contracts/openapi.yaml` → 后端实现 → `npm run gen:api` → 前端；证据链写 `integration-log.md` |
| 收尾门禁（全绿才 tag） | `uv run ruff check . && uv run ruff format --check .`；`uv run pytest -q`；`uv run python scripts/check_seams.py`（**默认档，要求 ERROR = 0**；`--strict` 仅用于 v1.4.0 Demo-MVP 完成点，判据见脚本 docstring）；`uv run python scripts/export_openapi.py --check`；`cd frontend && npm run lint && npm run typecheck && npm run gen:api`（无 diff） |
| 收尾动作 | **bump `settings.app_version`（与打 tag 是同一个动作）** → `git tag -a vX.Y.0` → `merge --no-ff` 回 main → release notes → `git mv` 归档 `changes/Sprint<N>.M/` 到 `changes/archive/<日期>-Sprint<N>.M>/` → **更新本表 §2 状态列 + `dev-doc-status.md` §9.2** |

## 4. 横跨全程的硬闸门（错过即倒推链断）

| 时点 | 日历锚点 | 闸门 | 不达标动作 |
|---|---|---|---|
| S5 批次 A2 第 1 天末 | 2026-09-22 | CP：`llm_provider` 抽象完成且"只多一层" | 触发 plan §4.4 降级第 2 条 |
| S5 批次 A2 第 2.5 天末 | 2026-09-24 | CP：provider / 8 字段 / `AuthProvider` / `pipeline_stages` 按 ADR-0004 §2.1 落位，`check_seams.py` 无登记外实现 | 未完成项降级登记，不得挤占批次 B |
| S6 第 3 天 | 2026-10-14 | go/no-go：chunk 级引用跑不通即降级为文档级引用（`doc-` 前缀） | 演示故事不断，登记降级事实 |
| **S10 收尾** | 2026-12-18 | **CP-1**：S11 的 `tasks.md` 立项"m6 spec v1.0 定稿" | 缺失即计划缺口 |
| **S11 中段** | ≈ 2027-01-01 | **CP-2**：schema-suggestion PoC 必须**跑通**（不接受写一半） | 不通即升级报用户裁决（顺延 S12 或 F1~F5 显式降级） |
| **S11 收尾前** | 2027-01-12 | **CP-3**：m6 spec v1.0 定稿（**S12 开工硬闸门**） | 不定稿不开工 |
| S12 期间（并行） | 01-13 → 01-29 | 纯 RAG 基线（`langchain_mvp` 分支）+ 合成数据集生成器启动（plan §21.1/21.2） | 不占 S13 关键路径 |
| **S13 批次 D** | 01-30 → 02-12 | TBD-3 / 4 / 6 / 7 全部收敛登记 | — |
| **S13 收尾** | 2027-02-12 | 上线 gate：plan §3.2 B 段五条 + §15 承接表逐行勾选/显式降级 + **`docs/acceptance-traceability-matrix.md` 终审** | 缺一不打 `v2.0.0` |

## 5. 状态跟踪

> 每个 Sprint 收尾时更新本列（✅ 已收尾 / 🔄 进行中 / ⏳ 未开始）。

| Sprint | 状态 | 实际 tag 日期 | 偏差记录 |
|---|---|---|---|
| S5 | ✅ 已收尾 | 2026-09-22 | 提前 19 天（计划 09-21→10-11，实际 09-22 tag）；批次 A / A2 / B / C 全完成，**提前完成但验收不跳过**（§1 纪律）；E1/E2 登记 unresolved |
| S6 | ✅ 功能收尾（tag `v1.2.0` **待打**） | 2026-09-23（达标日） | 提前 **27 天**（计划 10-12→10-20，实际 09-23 达标）；批次 A / B / C + 6.3 真机修复全完成；**第 3 天 go/no-go 通过**（chunk 级引用跑通，未降级为文档级）；受控问题集引用覆盖率 100%；实体消解推 S9（见 release notes v1.2.0 §6.1） |
| S7 | ✅ 已收尾（tag `v1.3.0`，2026-09-24） | 2026-09-24（达标日 / tag 同日） | 提前 **28 天**（计划 10-21→11-03，实际 09-24 达标）；前置还债批次 7.0（抽取接真实 LLM）+ 批次 A / B / C / D 全完成：M4 两类规则算法 → 三表落库 → 四端点 → 前端疑点页 → `domain_events` 事件出口；接缝 5 / 7 / 8 由 WARN 转 OK（`ERROR 0 / WARN 2 / OK 8`），余 2 条为未到期接缝 6；pytest 297 → 368。**未完（不伪装）**：三类算法与四源 0.95 对齐率（S9）、准入指标（S13）、证据粒度 chunk 级与 `char_offset` 恒 0（S10）；缺口 `S7.2-1`（`unaligned_subjects` 只建表不写）、`S7.2-2`（`list_in_flight` 只扫 `documents`，承 S8）已显式登记 |
| S8 | ✅ 已收尾（tag `v1.4.0`，2026-09-26） | 2026-09-24（达标日） | 提前 **41 天**（计划 11-04→11-10，实际 09-24 达标）；批次 A 审计闭环（`audit_log` / `qa_logs` 双表 + 两端点 + 审计页关 Mock）／ B 限流（429 `RATE_LIMITED` + `Retry-After` + 审计留痕）+ 逃生阀 `tenant_leak.warn` + **S7.2-2 偿还** ／ D **A16** settings 页「演示环境」标注（批次 D 三项**只做第三项**）／ E 接缝 6 `ExportSink`（`JsonCsvExportSink`）+ `log_export` 合规占位；pytest 368→**392**；`check_seams` **ERROR 0 / WARN 0 / OK 9**（WARN 归零，`--strict` **全周期首次全绿**）；契约路径 14→**16**。**未完（不伪装）**：受控问题集 NOT PASS（语料漂移，A15 如实登记）、种子数据集固化与演示彩排脚本**未做**、黄金路径步骤 6「同一 trace ≥7 条」**未实测**、`graph/overview` `entity_count=0` 未排查 |
| S9 | ⏳ 未开始 | — | — |
| S10 | ⏳ 未开始 | — | — |
| S11 | ⏳ 未开始 | — | — |
| S12 | ⏳ 未开始 | — | — |
| S13 | ⏳ 未开始 | — | — |

## 6. 变更记录

| 日期 | 版本 | 变更 | 依据 |
|---|---|---|---|
| 2026-09-21 | v1.0 | 建立：日历化 plan v3.0 §13 的 9 个 Sprint（S5~S13），交付日 2027-02-12；用户拍板"AI 执行、不加缓冲" | plan §13；倒推文档 §3/§7.1；用户 2026-09-21 确认 |
| 2026-09-22 | v1.1 | S5 收尾登记：① §3 收尾门禁的 `check_seams.py --strict` 更正为**默认档（要求 ERROR = 0）**；② §5 状态列 S5 → ✅ 已收尾（tag 2026-09-22，提前 19 天） | `check_seams.py` docstring 第 5–6 行 + `--strict` 分支报错文案（明示「只适用于 v1.4.0 Demo-MVP 完成点」）；实测 v1.1.0 跑 `--strict` 必红——WARN 6 全部为 **未到期** 接缝（5 事件出口 / 6 导出 / 7 外部映射 / 8 外部导入），按 `required_from` 属 v1.3.0~v1.4.0，非越界 |
| 2026-09-26 | v1.4 | S8 收尾登记：① §5 状态列 S8 → ✅ 已收尾（达标日 2026-09-24，提前 41 天，**tag `v1.4.0` 于本次收尾执行**）；② 新增 **[`docs/release-notes/v1.4.0.md`](./release-notes/v1.4.0.md)**（11 commit ／ 57 files ／ +5138 ／ −33 ／ 契约路径 14→16 ／ pytest 368→392 passed ／ `check_seams` **ERROR 0 / WARN 0 / OK 9**，`--strict` 首次全绿 ／ **§6 Demo-MVP 十条对账：7 达成 / 2 部分 / 1 未达成**）；③ `settings.app_version` **1.3.0 → 1.4.0**（`config.py:92` + `.env.example:9` + 本地 `.env`，后者会覆盖默认值）+ 同步重导契约 `info.version`（diff 仅 1 行）；④ **接缝 6 上闸**：`required_from = 1.4.0` 的两项由 WARN 转 ERROR，因批次 E 已提前落地故 `WARN 0 / ERROR 0`；⑤ **未完项（不伪装）**：受控问题集 NOT PASS（语料漂移）、批次 D 另两项未做、黄金路径步骤 6 未实测、`entity_count=0` 未排查 | `changes/Sprint8.{2,3,4}` 与 `changes/archive/2026-09-24-Sprint8.1/` 的 `integration-log.md` 真机证据链（审计 13 条 / 限流 429 + `Retry-After` + `rate_limit.triggered` 2 行 / settings 页 ¥0 点验 / 接缝 6 唯一实现）；`docs/acceptance-traceability-matrix.md` M5 行、H7 行与黄金路径步骤 6 同步 |
| 2026-09-24 | v1.3 | S7 收尾登记：① §5 状态列 S7 → ✅ 已收尾（达标日 2026-09-24，提前 28 天，**tag `v1.3.0` 已打于 `f0b7ff9`，2026-09-24**；`changes/Sprint7.{0,1,2,3,4}` 已归档）；② 新增 **[`docs/release-notes/v1.3.0.md`](./release-notes/v1.3.0.md)**（13 commit ／ 94 files ／ 契约路径 10→14 ／ pytest 368 passed ／ `check_seams` ERROR 0 WARN 2 OK 8）；③ `settings.app_version` **1.2.0 → 1.3.0**（与 bump 同步重导 `contracts/openapi.yaml` 的 `info.version`——该值取自 `app_version`，不同步则契约门禁必红）；④ 缺口 **S7.1-7**（M4「两层并存」）随 notes 落 §6.9 后关闭 | `changes/Sprint7.{0,1,2,3,4}/integration-log.md` 真机证据链（10 条疑点 / 42 条证据 / 引用覆盖率 100% / `domain_events` 10 行 `dispatched_at` 全 NULL / 浏览器点验 `confirmed=4 / dismissed=1`）；`docs/acceptance-traceability-matrix.md` M4 行与黄金路径步骤 4 同步 |
| 2026-09-23 | v1.2 | S6 收尾登记：① §5 状态列 S6 → ✅ 功能收尾（达标日 2026-09-23，提前 27 天，**tag `v1.2.0` 待打**）；② 新增 **[`docs/release-notes/v1.2.0.md`](./release-notes/v1.2.0.md)**（5 个 commit ／ 56 files ／ 契约路径 8→10 ／ pytest 297 passed ／ 受控问题集覆盖率 100%） | `docs/v1.1.0-demo-mvp-plan.md` §5.3 验收清单（7 条中 6 条达标，差 release notes 已补齐）；`changes/Sprint6.{1,2,3,4}/integration-log.md` 真机证据链；`scripts/eval_controlled_qset.py` 14 问真机 PASS |
