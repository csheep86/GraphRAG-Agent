# 开发文档定稿状态跟踪表

> **目的**：跟踪"能上线版本（v2.0.0 = PRD MVP 1.0 完成点）"路径上所有文档动作的执行状态。
> **更新人**：架构师
> **更新频率**：每 Sprint 收尾 + 任一项完成时
> **关联**：`docs/v1.1.0-demo-mvp-plan.md` §15 / §20.3；**倒推依赖与开工闸门见 `docs/v2.0.0-ship-backward-plan.md`**（D-1~D-5 即本表 P1-3~P1-5 / P2-1 / P2-2）；**日历化排期见 `docs/sprint-calendar.md`**（S5~S13 → 2027-02-12 `v2.0.0`）
> **当前基线**：tag `v1.0.0`（Sprint 4 收尾）；**下一个 Sprint = Sprint 5**（v1.1.0 真解析与在线建图）。
> **基线依据**：`docs/v1.1.0-demo-mvp-plan.md` §1.1 / §13；`changes/archive/` 最新批次为 `Sprint4.10.4`；`docs/release-notes/` 仅有 `v1.0.0.md`。

---

## 0. 当前状态总览

| 类别 | 总数 | 已完成 | 进行中 | 未开始 |
|---|---|---|---|---|
| P0（开 Sprint 5 前必办） | 1 | 1 | 0 | 0 |
| P1（后续 Sprint 9/11/12 启动前） | 5 | 2 | 0 | 3 |
| P2（每 Sprint 收尾 routine） | 3 | 0 | 0 | 3 |
| P3（上线 gate） | 1 | 0 | 0 | 1 |
| **合计** | **10** | **3** | **0** | **7** |

最近更新：2026-09-21（架构师）——**P0 口径更正**（原"Sprint 9 启动前"→"开 Sprint 5 前"，见 §1）；P0-1 完成（M6 草案落地，已移入 §7 历史）；新增 P1-3（M6 spec v1.0 定稿）/ P1-4（M2 §4.5 加 `applied`）/ P1-5（schema-suggestion PoC），来源 `docs/v2.0.0-ship-backward-plan.md` §5.2 D-1/D-2/D-3。
**2026-09-21 追加**：开口项 **O-1~O-5 全部拍板**（倒推文档 §7 决策记录）；P1-3 / P1-5 已补**两段式检查点**（见 §2 备注列，机制见倒推文档 §7.1）；§9 新增"每批次开工"SDD checklist。

**2026-09-21 追加（上线级文档一致性审计）**：完成一轮横向审计（范围 = 总需求文档 `03-prd.md` / 长指南 Harness·SDD / Harness 常驻规则 / SDD 模板 / 技能库 / README / 倒推计划 / CI），**共 8 项发现（F9~F15 + R1 闭环）已全部处理完毕**，并新增 1 份核心文档 **[`docs/acceptance-traceability-matrix.md`](./acceptance-traceability-matrix.md)**（H1–H12 / C1–C3 / F1–F5 → 判据 → 验收人）。审计结论与逐项处置见 **§6.1** 与 **§7**。

**2026-09-21 追加（Sprint 日历登记）**：新增 **[`docs/sprint-calendar.md`](./sprint-calendar.md)**——把 plan v3.0 §13 的 S5~S13（21 周）日历化，Sprint 5 当日开工，**交付日 2027-02-12（`v2.0.0`）**；用户拍板"AI 执行、不加缓冲"。已同步登记 `03-prd.md` 附录 C.0（第 14a 行）。**收尾 routine（§9.2）新增一步：更新 `sprint-calendar.md` §5 状态列。**

**2026-09-21 追加（无人值守执行协议固化为技能）**：新增 `.codebuddy/skills/unattended-sprint-execution/SKILL.md`（用户选 A 方案授权）——`executing-plans` 的预授权变体：默认按 plan v3.0 + sprint-calendar + CODEBUDDY 逐批次推进、免请求自动提交、决策点一律采纳文档建议项，**仅 4 类情况升级用户**（CP-2 PoC 不通 / F1~F5 触发 / 文档未覆盖决策 / S13 上线 gate 终审）。已在 `using-superpowers/SKILL.md` 技能地图登记。

**2026-09-22 追加（Sprint 5 收尾登记）**：S5 于 **2026-09-22** 完成（tag `v1.1.0`，较计划区间 09-21→10-11 提前 19 天，验收不跳过）。① **归档**：`changes/Sprint5.1`~`Sprint5.4` → `changes/archive/2026-09-22-Sprint5.N/`；② **矩阵对账**（`acceptance-traceability-matrix.md`）：H4（`_refuse()` 出口 `trace_id` 为空）、H8（B1 `retry_count` 回写 + B4 退避路径未读 `task_retry_multiplier`）**两项「已知缺陷」关闭**，M1 / M2 现状与黄金路径步骤 3 同步刷新；③ **口径更正（重要）**：接缝门禁的 Sprint 收尾判据由 `--strict` 更正为 **默认档 + ERROR = 0**——依据 `check_seams.py` docstring 第 5–6 行，`--strict` 仅适用 v1.4.0 Demo-MVP 完成点；实测 v1.1.0 跑 `--strict` 必红，6 条 WARN 全为**未到期**接缝（5/6/7/8，分属 v1.3.0~v1.4.0）而非越界。已同步修 `sprint-calendar.md` §3 与矩阵 §5.3（原两处均误写为 `--strict`）；④ **遗留降级**：E1 / E2 数据质量评估登记 **unresolved**（抽取器为 mockable 正则占位，统计无意义），归 S13 条件吸收，见 release notes v1.1.0 §6.1。

---

## 1. P0 — 开 Sprint 5 前必办（**已全部就绪，无文档阻塞**）

> **口径更正（2026-09-21）**：本节原标题为"Sprint 9 启动前必办"，与项目事实不符——当前基线是 tag `v1.0.0`，**下一个 Sprint 是 Sprint 5**（依据见头部"基线依据"行）。原 P0-1"补 M6 spec 草案"实际属 **S12 前置**，已移入 §7 历史并另立 **P1-3**。
>
> **结论：Sprint 5 无文档前置，可直接开工。**

| # | 行动 | 状态 | 责任人 | 完成时间 | 备注 |
|---|---|---|---|---|---|
| **P0-1** | Sprint 5 开工闸门核查：`ADR-0004` Accepted + `scripts/check_seams.py` 在 CI + `documents` 8 预留字段方案冻结 | ✅ **全部就绪** | 架构师 | 2026-09-21 | 倒推文档 §3 S5 行；三项均已落地（`docs/adr/0004-integration-seams.md`、`backend/scripts/check_seams.py` + CI、`plan §8.2` 字段清单） |

---

## 2. P1 — 后续 Sprint（Sprint 9 / 11 / 12）启动前必办

| # | 行动 | 状态 | 责任人 | 完成时间 | 备注 |
|---|---|---|---|---|---|
| **P1-1** | 核 `entity_relation_extract_v1.md` 是否支持 schema-suggestion 模式 | ✅ **已完成** | 架构师 | 2026-09-21 | v1 已支持参数化（`{{entity_types}}` / `{{relation_types}}` / `{{domain_description}}`），schema-suggestion 可在应用层封装实现——**无需新增 Prompt 版本**，符合 PRD §7 |
| **P1-2** | OpenSpec 现状口径选择 | ✅ **已完成**（方案 1） | 架构师 | 2026-09-21 | README 行 25 改写一句话承认事实；根/后端 CODEBUDDY 未含 OpenSpec 字段，未改 |
| **P1-3** | `specs/m6-*.md` 由 v0.1 草案升 **v1.0 定稿** | ⏳ 未开始 | 架构师（验收：用户） | **S11 收尾前**（S12 开工闸门，**硬**） | 倒推文档 §5.2 D-1 + **§7.1 检查点**：**CP-1 = S10 收尾时**写入 S11 的 `changes/Sprint11.*/tasks.md` 立项；**CP-2 = S11 中段**核对是否进入待审；**CP-3 = S11 收尾前**闸门。m6 spec §10 已有 8 项可勾选 checklist；m6 spec 状态行自述"定稿时点 = S11 收尾前" |
| **P1-4** | `specs/m2-*.md` §4.5 `entity_merge_candidates.status` **加 `applied`**（并补 §3 验收 3 一条） | 🟡 **文档侧已完成**（2026-09-21） | 架构师 + 后端 B | 文档已补；**代码/契约侧 = S9 顺路** | 倒推文档 §5.2 D-2。**已完成**：M2 §4.5 加前向预留注脚 + §3 验收 3 交叉引用（**明确 M2/S9 不落该值、口径不变**）。**余下**：M6 落地前走后端 CODEBUDDY §3 契约同步 5 步（Pydantic → 重导契约 → 提交生成物 → `gen:api` → 零漂移校验） |
| **P1-5** | schema-suggestion **端到端 PoC**（应用层封装 + v1 参数注入） | ⏳ 未开始 | 后端 B（验收：架构师） | **S11 收尾前**（**硬**） | 倒推文档 §5.2 D-3 + **§7.1 检查点**：**CP-2（S11 中段）必须已"跑通"**，不接受"写了一半"——若未通即**升级报用户**，评估 S12 顺延或走 F1~F5 显式降级决议。缓解 R2（v1 参数化路径未实测） |

---

## 3. P2 — 每个 Sprint 收尾 routine

| # | 行动 | 状态 | 责任人 | 完成时间 | 备注 |
|---|---|---|---|---|---|
| **P2-1** | release notes 撰写（v1.5.0 / v1.6.0 / v1.7.0 / v1.8.0 / v2.0.0） | ⏳ 未开始 | 架构师 + 后端 B | — | 每个 Sprint 收尾时跟，**不堆积**；§15.4 纪律要求 |
| **P2-2** | 操作手册 Sprint 9~13 章节（阶段十八~二十二） | ⏳ 未开始 | 架构师 | — | 每个 Sprint 收尾跟一节 |
| **P2-3** | **`acceptance-traceability-matrix.md` 对账**：本 Sprint 承接的 spec §3 验收条逐个勾选 + 涉及的 H 行「现状」列刷新 | ⏳ 未开始 | 架构师 + 各模块负责人 | — | 已写入 §9.2 第 3 项；**任一行「判据」或「验收人」为空 → 不得收尾** |

---

## 4. P3 — Sprint 13 上线 gate

| # | 行动 | 状态 | 责任人 | 完成时间 | 备注 |
|---|---|---|---|---|---|
| **P3-1** | §15.3 现状列加代码行号引用 + §15 逐行勾选 + §3.2 B 五条对账 + **`acceptance-traceability-matrix.md` §4 / §5 全表终审（48 条 spec 验收 + 12 条 H + C1–C3 / F1–F5）** + `check_seams.py --strict` + 契约零漂移 + 前端 typecheck/lint | ⏳ 未开始 | 架构师 + 后端 B + 前端 FE | — | Sprint 13 收尾统一做（§20.3 DoD） |

---

## 5. prompts S9~S13 核账（已澄清，**无缺口**）

**结论**：**Sprint 9~13 全部复用 v1（5 件），不新增 Prompt 版本**，符合 PRD §7 与 CODEBUDDY H9。

| Sprint | 新能力 | 复用 Prompt | 备注 |
|---|---|---|---|
| S9 | M4 三类算法 + 实体消解 | `entity_relation_extract_v1.md` | 场景适配（参数化） |
| S10 | 多跳 + 证据链 + docx 解析 | `kg_qa_v1.md` | 多跳与拒答已支持 |
| S11 | M5 + RLS + 内网双轨 | — | M5 不消费 Prompt（spec §1 头） |
| S12 | M6 冷启动 + 校正 GUI + 增量重算 + 成本仪表盘 | `entity_relation_extract_v1.md`（**仅参数化**） | 详见 §5.1 |
| S13 | C1~C3 实验闭环 | — | 不涉及 prompt |

### 5.1 M6 schema-suggestion 模式实现路径（已决议）

```text
1. POST /api/v1/ontology/cold-start
   → 调用 kg_qa_v1（轻量 LLM 调用）建议 entity_types / relation_types
2. 用户在 M6 校正 GUI 确认
3. 写入 ontology_schemas 表（status=active, version=1）
4. M2 抽取时从 ontology_schemas 表读取
   → 作为参数传入 entity_relation_extract_v1.md
5. v1 prompt 中 {{entity_types}} / {{relation_types}} 占位符消费该参数
```

**关键证据**：`entity_relation_extract_v1.md` 第 16~18 行已含 `{{entity_types}}` / `{{relation_types}}` / `{{domain_description}}` 占位符——**v1 已支持模板参数化**。

---

## 6. OpenSpec 现状口径（已采纳方案 1）

**决议**：**方案 1**——承认事实。`openspec/` 目录保留但工具链未启用；变更以 `specs/` + ADR + Sprint log 为准。

**理由**：
- 启用 OpenSpec 工作流（方案 2）成本大（需补 `openspec/specs/` 的 5 个模块 baseline + `changes/` 模板）；
- 维持空壳（方案 3）留下隐性债务；
- **承认事实（方案 1）成本最低、与现状一致**。

**已落动作**：README 行 25 改写为"`openspec/` 工具链工作区目录（**当前未启用**；`openspec/specs/` 与 `openspec/changes/archive/` 均为空，变更以 `specs/` + ADR + `changes/` 为准）"。

> **2026-09-21 复核更正**：上一版改写句中的"历史归档保留在 `openspec/changes/archive/`"是**误述**——实测 `openspec/changes/archive/` **为空**，历史批次归档实际在 **`changes/archive/`**（`2026-09-20-Sprint4.10.1` ~ `…Sprint4.10.4`）。README 行 25 与行 28 已同步更正。

**2026-09-21 追加（口径收紧为"停用"）**：方案 1 从"承认事实"升级为**主动围栏**——原因是审计发现 **OpenSpec 的 6 个技能 + 6 个命令仍处于可被自动匹配的状态**，一旦触发会写到 `openspec/changes/`（错误落点）。已落动作：

| 落点 | 动作 |
|---|---|
| `.codebuddy/skills/openspec-*/SKILL.md`（6 个） | `description` 前置 `【本仓库已停用，禁止调用】` + 正文加⛔警告 + 给出替代路径 |
| `.codebuddy/commands/opsx/*.md`（6 个） | 同上（`【本仓库已停用，禁止执行】`） |
| `README.md` | 行 25 目录表 + 行 36 技能库说明 + 头部"OpenSpec 已停用"声明 + 开发约定 |
| 长指南 | 阶段一"安装 OpenSpec CLI"/"`openspec init`"**两步标注作废**；头部"适用边界"第 5 条 |

> **保留而非删除的理由**：文件在 git 中可追溯，删除属破坏性操作且需使用者确认；**用围栏使其"不可触发"已足够消除偏离风险**。若后续确认无需留痕，可另行删除。

---

## 6.1 上线级文档一致性审计（2026-09-21）

**审计范围**：`docs/03-prd.md`（总需求）、长指南（Harness + SDD 标准）、根/后端 `CODEBUDDY.md`、`.codebuddy/rules/`（Harness 围栏）、`.codebuddy/skills/`、`specs/` + `specs/_template/`、`README.md`、`contracts/`、`ci.yml`、`docs/v2.0.0-ship-backward-plan.md`。

**审计口径（三项判据）**：

| 判据 | 含义 |
|---|---|
| **C-一致** | 同一事实在不同文档中表述**不冲突**（冲突即未来必偏离） |
| **C-可追** | 每条需求能追到**唯一落点**（spec 的哪条验收） |
| **C-可验** | 每条需求有**可复现判据 + 具名验收人** |

**结论**：**C-一致 = 已达标**（**8 项冲突全部修毕**，见 §7 F9~F15 + R1）；**C-可追 = 已达标**（新增验收矩阵，48 条 spec 验收 + 12 条 H 硬约束全部有唯一落点）；**C-可验 = 已达标**（H1–H12 逐行有判据与验收人；3 行带条件：H8 附已知缺陷、H11 附"评测脚本待建"、H6 附占位例外登记）。

**遗留（不阻塞，已排期）**：

| 项 | 状态 |
|---|---|
| 长指南阶段十八~二十二（Sprint 9~13）未编写 | **D-4 / P2-2**，头部已标注口径以 plan 为准 |
| C1–C3 评测脚本（`eval`）尚未存在 | **S13**，矩阵 §5.1 已标"待建" |
| H8 的 `task_retry_multiplier` 缺陷 | **plan T11 / S5 批次**，矩阵 §4 已标 ⚠️ |
| H4 的 `_refuse()` 出口 `trace_id` 为空 | **S5 批次收口**，矩阵 §4 已标 ⚠️ |

---

## 7. 历史变更（已关闭）

| # | 项 | 关闭时间 | 处理决定 | 备注 |
|---|---|---|---|---|
| F1 | release-notes 历史补全（v1.1.0~v1.4.0） | 2026-09-21 | **不补** | 已 ship 不可改；retro 写进 `v1.0.0-revised.md`（如需要） |
| F2 | 长指南 `.md` vs `.docx` 一致性核 | 2026-09-21 | **不核** | 多数团队只看 .md；docx 可标"快照版"免责 |
| F3 | prompts S9~S13 缺口（用户提） | 2026-09-21 | **误判修正 → 无缺口** | plan §19.1 A 显式说"不新增 Prompt 版本"；已澄清（详见 §5） |
| F4 | §15.3 现状列加代码行号引用（早期） | 2026-09-21 | **不现在做** | Sprint 9~13 期间还会变；推迟至 P3-1（§4）上线 gate 时统一做 |
| F5 | M6 spec 草案（原 P0-1） | 2026-09-21 | ✅ **已完成** | `specs/m6-ontology-incremental.md` v0.1 就位；v1.0 定稿另立 **P1-3**（S11 收尾前，S12 开工闸门） |
| F6 | SDD 三件套落点（原倒推文档 O-1 待裁决） | 2026-09-21 | ✅ **已决议：方案 A′** | 落点 = `changes/Sprint<N>.<M>/`，三件套与 `integration-log.md` 并存；**不启用 OpenSpec CLI**；依据 `changes/archive/` 6 个历史批次；详见 `docs/v2.0.0-ship-backward-plan.md` §6.1。三件套模板说明（`specs/_template/*.md`）已按此校准 |
| F7 | README `openspec/` 归档路径误述 | 2026-09-21 | ✅ **已更正** | 实际归档在 `changes/archive/`；README 行 25 / 行 28 已改 |
| F8 | 开口项 **O-2 / O-3 / O-4 / O-5** 待拍板 | 2026-09-21 | ✅ **全部拍板** | **O-2**：`applied` 代码/契约侧 **S9 顺路**（S9 建表当日走契约同步 5 步）；**O-3**：D-1/D-3 走**两段式检查点**（CP-1 = S10 收尾立项 / CP-2 = S11 中段核对 / CP-3 = S11 收尾前闸门，机制见倒推文档 §7.1）；**O-4**：TBD-3/4/6/7 按 plan §20.1 批次 D 在 S13 收敛；**O-5**：数据集生成器 + 纯 RAG 基线 **S12 期间并行启动** |
| F9 | **`03-prd.md` §2 / §7 的 M6 归属与 plan v3.0 冲突**（R1 根因） | 2026-09-21 | ✅ **已修订** | §2 M6 行 `P1（不在本期）`→ **`P0（S12 承接）`** + 加判定依据；§2 结论行改"6 个模块"；§7 Prompt 清单改"M6 本期含"；§3 依赖图补 M6 四条边 + 第 5 条结论；§4 H 表末加矩阵指针。**这是"可按原始文档验收"的前置条件** |
| F10 | PRD 头部关联规格/ADR 缺 M6 与 ADR-0004；技术栈写 **Next.js 15** | 2026-09-21 | ✅ **已更正** | 关联规格补 `m6-ontology-incremental.md` + `_template/`；关联 ADR 补 `0004-integration-seams.md`；新增"关联计划"行；技术栈改 **Next.js 16.3.5 + React 19**（依据 `frontend/package.json`） |
| F11 | PRD §8 TBD-3/4/6/7 决策窗口为"M1.0 末期 / 验证期 / 实现期"（无锚点） | 2026-09-21 | ✅ **已收敛** | 统一改为 **`Sprint 13（批次 D）`**（依据 O-4）；TBD-7 补"阈值落 `backend/app/core/config.py`，可经 `.env` 覆盖" |
| F12 | PRD 附录 C 文件清单过时（仅 9 个文件） | 2026-09-21 | ✅ **已重构** | 新增 **C.0 当前文档基线（17 条，唯一权威）**，旧表降为 **C.1 首轮产出快照（历史留痕）**；并补"非文档产物"（契约 / prompts / changes） |
| F13 | 长指南把 `v1.4.0` 称"Demo-MVP 完成点"、分支与 tag 只到 Sprint 8、**环境准备仍教安装 OpenSpec CLI**、技术栈含 Milvus/MCP | 2026-09-21 | ✅ **已更正** | 头部新增「**文档适用边界**」5 条（覆盖范围 / 口径优先级 / 交付口径 / 验收对账 / OpenSpec 停用）；分支策略补 **Sprint 9~13**；tag 清单延伸到 **v2.0.0**；`v1.4.0` 改"中途演示点（非交付版）"；**第 6 / 9 步标注作废**；技术栈移除 Milvus / MCP、补 PostgreSQL，并说明 Milvus 于阶段十四已跳过 |
| F14 | `.codebuddy/rules/always-on/project-conventions.md` **与根 `CODEBUDDY.md` 冲突**（pre-commit hook）+ **缺接缝纪律** | 2026-09-21 | ✅ **已更正** | pre-commit 改为"**暂未启用**（规划 v1.1.0），以 CI 为最终裁决"；**新增三节**：「功能预留与接缝纪律」（3 条铁律 + 门禁）、「SDD 变更流程」（落点 + 归档 + 禁 OpenSpec）、「验收与'完成'口径」（判据 + 收尾门禁 + 降级纪律 + tag=bump） |
| F15 | 6 个 `openspec-*` 技能 + 6 个 `opsx` 命令**仍可被自动匹配**，与 O-1 决议冲突 | 2026-09-21 | ✅ **已加停用围栏** | **12 个文件**的 `description` 前置停用标记（技能 = `【本仓库已停用，禁止调用】`；命令 = `【本仓库已停用，禁止执行】`）并加正文⛔警告与替代路径；README 行 25 / 行 36 + 头部 + 开发约定同步；**保留文件仅作留痕，未删除** |

---

## 8. 风险登记

| # | 风险 | 影响 | 缓解 | 状态 |
|---|---|---|---|---|
| ~~**R1**~~ | ~~PRD §2 与 plan §15.1 第 5 行口径冲突~~ | M6 spec 落地后文档未同步 | ✅ **已闭环 2026-09-21**：PRD §2 / §7 / §3 / §4 / 附录 C 全部同步（见 F9 / F10 / F12），**不再推迟到 Sprint 12** | **已关闭** |
| **R2** | schema-suggestion 模式未实测验证 | S12 启动后发现 v1 参数化路径走不通 | Sprint 11 收尾前补端到端 PoC（**CP-2 于 S11 中段核对是否已跑通**，见 P1-5） | 跟踪中 |
| **R3** | dev-doc-status.md 失维护 | §15.4 纪律被打破 | 列入 Sprint 收尾 checklist（P2-1 / P2-2）+ §9.2 第 3 项 | 跟踪中 |
| **R4** | release-notes v1.5.0 起累计欠账 | §15.4 显式声明失败 | 每次 Sprint 收尾跟进，**不堆积** | 跟踪中 |
| **R5** | **规格验收编号漂移**：任一次"重排 / 插入 / 删除"编号，会使 `acceptance-traceability-matrix.md` 全部锚点失效 | 验收对账静默失效（比无矩阵更危险：看起来有判据） | **矩阵 §7 第 1 条**：编号一经定稿**只能追加**；Sprint 收尾核对时若发现编号变动，**必须同步修矩阵** | 新增 |
| **R6** | 长指南阶段十八~二十二未编写（D-4），Sprint 9 起无操作手册 | 新成员 / 新会话按长指南执行会停在 Sprint 8 | 长指南头部已加「文档适用边界」，**明确 Sprint 9~13 口径以 plan 为准**；P2-2 每 Sprint 跟一节 | 新增 |
| **R7** | **新增文档未登记形成"第二真源"** | 同一事实出现两处不一致表述 | **PRD 附录 C.0 为唯一文档基线**，新增文档必须登记；矩阵 §7 第 4 条"不复制参数值" | 新增 |

---

## 9. 联动 Checklist

### 9.1 每批次**开工**必做（SDD 事前，决议见倒推文档 §6）

```
[ ] 1. 建 changes/Sprint<N>.<M>/ 目录
[ ] 2. 写 proposal.md（为什么做 / 改什么 / 影响面 / 不做什么）
[ ] 3. 写 tasks.md（可独立验证的任务清单 = 排计划的直接依据）
[ ] 4. 有架构决策或多方案时补 design.md
```

### 9.2 每 Sprint **收尾**必做（按顺序）

> **顺序不可换**：先补事后证据 → 再归档 → 最后刷文档。归档后 `changes/Sprint<N>.<M>/` 即消失，漏了证据只能翻 `archive/`。

```
[ ] 1. 补 integration-log.md（实测证据链：前置核实 / 跑数 / 关键发现 / gap / 未触碰项 / 收尾确认）
[ ] 2. 归档 changes/Sprint<N>.<M>/ → changes/archive/<日期>-Sprint<N>.<M>/
       （只归档 .md 与 .py；*.log / *.pyc 不入库）
[ ] 3. 按 acceptance-traceability-matrix.md 逐行对账：
       ① 本 Sprint 承接的 spec §3 验收条**逐条打勾**；
       ② 本 Sprint 涉及的 H 行「现状」列刷新；
       ③ 任何一行「判据」或「验收人」为空 → **不得收尾**
[ ] 4. 更新本跟踪表（dev-doc-status.md）状态列
[ ] 5. 更新对应 spec 的"状态"行（如实现态已变化）
[ ] 5a. 更新 docs/sprint-calendar.md §5 状态列（实际 tag 日期 + 偏差记录）
[ ] 6. 更新对应 spec 的"已登记的实现缺口"列表
[ ] 7. 撰写 release notes（v1.x.0.md）
[ ] 8. 撰写操作手册对应章节（阶段 X）
[ ] 9. 核 §15 承接表对应行：勾选 / 显式降级登记
[ ] 10. CI / check_seams.py / 契约零漂移 全绿
[ ] 11. tag v1.x.0 + bump settings.app_version（同步动作，§3.3）
```

### 9.3 触发式必做（满足条件即执行，**不等 Sprint 收尾**）

```
[ ] 改 PRD §4（增删改任一 H）→ 同步 specs 对应 §3 + acceptance-traceability-matrix.md §4（三处同步）
[ ] 改任一 spec §3 的验收条 → 只在**末尾追加编号**，禁止重排/插入/删除（矩阵锚点会失效，见 R5）
[ ] 新增预留字段 / 表 / 接口实现 → 先扩写 docs/adr/0004-integration-seams.md §2.1 登记行，再改门禁
[ ] 新增任何文档 → 登记到 docs/03-prd.md 附录 C.0（唯一文档基线，防"第二真源"）
[ ] 变更 tag 规划 / 交付口径 → 同步 README「交付状态」+ 长指南「文档适用边界」+ 倒推计划 §2/§3
```

> **一年/上线前**：跑一次 **§6.1 口径的横向一致性抽查**（总需求 ↔ 长指南 ↔ 常驻规则 ↔ 技能库 ↔ README ↔ 计划），判据见 §6.1 的 C-一致 / C-可追 / C-可验。

---

> **本表与 `docs/v1.1.0-demo-mvp-plan.md` §15 / §3.2 B 段 / §20.3 共同构成"上线 gate 三件套"**。任一 Sprint 收尾时**必须**对照本表与 §15 更新状态。