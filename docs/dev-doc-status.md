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

**2026-09-24 追加（Sprint 7 收尾登记）**：S7 于 **2026-09-24 功能达标**（较计划区间 10-21→11-03 提前 28 天；前置还债批次 7.0 + 批次 A / B / C / D 全完成）。① 新增 **[`docs/release-notes/v1.3.0.md`](./release-notes/v1.3.0.md)**（13 commit ／ 94 files ／ +13893 ／ −1054 ／ 契约路径 10→14 ／ pytest 297→368 passed ／ `check_seams` **ERROR 0 / WARN 2 / OK 8**）。② `settings.app_version` **1.2.0 → 1.3.0**（`config.py:92` + `.env.example:9`）；**连带动作**：`contracts/openapi.yaml` 的 `info.version` 取自 `app_version`（`test_openapi_contract.py:93` 有断言守着），故 bump 后**必须重导契约**，否则契约零漂移门禁必红——已重导并 `--check` 通过（diff 仅 `version: 1.2.0 → 1.3.0` 一行）。③ `sprint-calendar.md` §5 S7 → ✅ 功能收尾（**tag `v1.3.0` 待打**）+ §6 变更记录 v1.3。④ **接缝闸门生效**：接缝 5 / 7 / 8 判据由「未到期只记 WARN」转 **ERROR**，三者 bump 前实测已 OK，故 bump 后仍 **ERROR 0**；余 2 条 WARN 为未到期接缝 6（1.4.0）。⑤ **缺口 S7.1-7 关闭**：M4「两层并存」（`:Entity` + `:Subject`）已落 release notes §6.9。⑥ **已完成**：`app_version` bump 至 1.3.0、tag **`v1.3.0` 已于 2026-09-24 打在 `f0b7ff9`**、`changes/Sprint7.{0,1,2,3,4}` **已归档**至 `changes/archive/2026-09-24-Sprint7.N/`（26 个文件，100% rename）。**未完项显式登记（不伪装）**：矩阵 P2-3 逐行对账**未做**（§9.2 第 3 项，纪律要求「任一行判据或验收人为空 → 不得收尾」）、`push` 与 `merge` 由用户执行；遗留技术债见 release notes §6（三类算法与 0.95 对齐率 → S9，证据粒度 chunk 级 / `char_offset` 恒 0 / chunk 原文含 HTML 表格标记 → S10，准入指标 → S13，`reviewed_by` 取自 dev 脚手架 → S11）。⑦ **收尾期观察（非阻塞）**：`tests/test_kg_versioning.py::test_get_active_returns_latest_ready_for_same_org` 在 bump 后首次全量跑时**偶发失败 1 次**，单跑 / 该文件内跑 / 全量复跑均通过（368 passed），判定为**偶发**而非回归；未改任何测试或阈值，如实登记以便复发时追溯。

**2026-09-24 追加（Sprint 7.4 批次 D：M4 事件出口 / 接缝 5）**：① **契约路径仍 14**（本批次**零契约变更**）：`domain_events` 属预留表，按 CODEBUDDY §功能预留原则第 4 条**不进** `contracts/openapi.yaml`、前端不消费 → `export_openapi.py --check` 无 diff。② **`domain_events` 表 + `EventSink` 接口就位**：新增 `app/services/events/`（`base.py` 接口 + `db.py` / `log.py` 两个本地实现 + `bus.py` + `types.py`）；**`EventBus` 不继承 `EventSink`**——`check_seams.py` 按基类名统计实现类并要求恰好 2 个，继承会让实现数变 3 → ERROR。③ **`risk.suspect_created` 首个真实事件源**：`persist_detection_result` 落库后**每条疑点**发一条事件；**必须先 `flush()`**（`record.id` 是 INSERT 时才生成的 UUID，不 flush 则 `aggregate_id` 为空）；事件与疑点**同 session**、`db` sink **不自己 commit**（业务回滚时事件一并撤销），`dispatched_at` **恒 NULL**（只落不派）。④ **真机**：重跑一次检测（task `0573c98f-…`）→ PG `domain_events` **10 行**（= 疑点数）、`dispatched_at` **10/10 为 NULL**、`aggregate_id` 指向真实疑点（首条 `2c507081-…` 正是被 PATCH 复核的那条）、`trace_id` 与任务同值。⑤ **门禁**：接缝 5 两条规则 **WARN → OK**（`ERROR 0 / WARN 4 / OK 7` → **`ERROR 0 / WARN 2 / OK 8`**，余 2 条为未到期接缝 6）；pytest **364 → 368 passed**。⑥ **未做（不伪装）**：`document.parsed` / `kg.updated` / `qa.answered` **只定义取值、不发送**（无真实触发点，发即假事件）；不做派发 / 重试 / webhook；不新增 `settings.*` 配置；未改 ADR-0004 §2.1（第 5 行已含 `db` / `log`）；未写迁移脚本（全仓无 Alembic，靠 `create_all`）。⑦ **未完**：`app_version` 仍 1.2.0，v1.3.0 bump + tag 在 Sprint 7 收尾统一处理。⑧ **副作用（已告知）**：重跑检测产出新一批 10 条 `open` 疑点，列表默认返回最近 completed 任务 ⇒ 此前人工复核状态从列表不可见（记录仍在，按旧 `task_id` 可查）。

**2026-09-24 追加（Sprint 7.3 批次 C：M4 疑点清单前端 / 演示剧本第 5 步）**：① **契约路径仍 14**（本批次**零契约变更**，纯消费批次 B 已进契约的四端点）。② **前端疑点页 `/affiliation` 上线**：新增 `src/api/affiliation.ts`（+ `api/mock/affiliation.ts`）、`store/use-affiliation-store.ts`（**全仓首个真轮询**：模块级句柄防叠加，2s → 10s 降频）、`components/affiliation/{suspicion-table,suspicion-toolbar,suspicion-detail-sheet}.tsx`、`components/common/suspicion-badges.tsx`、`app/affiliation/page.tsx`；`lib/nav.ts` 增「疑点清单」入口（图标用 `ShieldAlert`——`ShieldCheck` 已归 system 组「权限审计」）。③ **C6 共用高亮**：`splitHighlight` 从 `components/qa/chunk-viewer.tsx` 提取到 `lib/highlight.ts`（**只挪位置不改逻辑**，S6 真机口径），疑点证据与 QA 引用共用一份，避免两份实现日后漂移。④ **关 Mock 真机**：`GET /affiliation/suspicions` → `total=10` 且主体为招商局系（**非** mock 的「示例甲」）；**证据回查 10/10 成功**；四条请求路径全部命中 `CONTRACT_COVERED_PATTERNS` ⇒ `USE_MOCK=false` 时 `shouldMock()` 恒 false，Mock 数据不参与。⑤ **浏览器点验（用户 2026-09-24 完成）**：清单 10 条 / 证据抽屉实开（多证据并发回查 + `trace` 可见）/ 「跑一次检测」轮询刷新 / 复核落库（后端查得 `confirmed=4 / dismissed=1`，`reviewed_at` 与点击时间吻合、`reviewed_by` 有值）。⑥ **门禁**：`lint` 0 error 0 warning、`typecheck` exit 0、`gen:api` 零 diff、`build` 通过且路由含 `/affiliation`。⑦ **缺口两处（不伪装）**：证据粒度是 **chunk 级**（真机 10/10 条 `ev_len == chunk_len`），片段级定位（`char_offset` 恒 0）按 `plan.md:619` 归 **S10** ⇒ 前端整段场景改**淡底 + 标注**，**未伪造高亮**；chunk 原文混有未清洗的 `<table>` / `<tr>` / `<td>` 标记，属解析层数据质量（批次 A / S6 链路），不归本批次修，随 S10 一并处理。⑧ **演示注意（设计使然，非 bug）**：重跑检测后列表全回「待复核」——契约口径为默认返回**最近一条 completed 任务**的疑点，旧复核记录仍在库（按旧 `task_id` 可查），故复核完不要立刻重跑。

**2026-09-24 追加（Sprint 7.2 批次 B：M4 疑点持久化 + 对外端点）**：① **契约路径 10 → 14**：新增 `/affiliation/detect`、`/affiliation/tasks/{id}`、`/affiliation/suspicions`、`PATCH /affiliation/suspicions/{id}`（逐字照 `specs/m4-affiliation-detection.md` §5.5）；**顺带纠一处口径不一致**——plan §6.2 原摘要写 `GET /affiliation/suspects`，与 spec 的 `suspicions` 冲突，已按「spec 优先」统一 plan（`plan.md:275` / `plan.md:289`），历史批次 `changes/Sprint7.1/proposal.md:48` 加口径消歧，**未静默**。② **三张 PG 表** `affiliation_tasks` / `affiliation_suspicions` / `unaligned_subjects` 就位（表名逐字 = PRD §6.2，均带 `org_id` 且索引以 `org_id` 打头）；其中 `affiliation_suspicions` 按决策 B2 **新增 `task_id` 列**并已在 spec §4.3 登记变更（回答「GET 返回哪一批疑点」靠列不靠 `created_at` 猜）。③ **`TaskManager` 扩展为双载体**（决策 B8）：原 `submit()` 硬绑 `payload["document_id"]` 且 task_id 恒为 `documents.id`，无法承载「一次检测覆盖多份文档」的任务 → 增加 `affiliation_task_id` 分支，**既有三种 task_type 行为零改动**（守住 ADR-0001 要求 2：业务代码只依赖该接口）；`recover_orphan_tasks()` 同步扩到扫 `affiliation_tasks`（ADR-0001 第 73 行原就已要求扫两张表）。④ **接缝 7 / 8 落地**：`external_refs` 表 + `app/services/external_data/`（导入文件 schema JSON/CSV + 手工导入 CLI，默认 dry-run），`check_seams.py` 由 **WARN 6 → WARN 4**（余下两条为**未到期**的接缝 5 / 6）。⑤ **真机**：6 片演示数据 + `v-s71a-fe1c4dc3` → `POST detect` 202 → 任务 completed → **10 条疑点落库**（共享法人 1 + 共享地址 9，与批次 A 一致）、`trace_id` 贯穿、`PATCH` 复核留痕。pytest **352 → 364 passed**；`export_openapi.py --check` 无 diff。⑥ **未完登记（不伪装）**：`unaligned_subjects` **只建表不写**（写入点随 S9 批次 D 四源对齐，已登记缺口 **S7.2-1**）；`TaskManager.list_in_flight_task_ids()` 仍只扫 `documents`（**S7.2-2**）。

**2026-09-23 追加（Sprint 6 收尾登记）**：S6 于 **2026-09-23 功能达标**（较计划区间 10-12→10-20 提前 27 天；批次 A / B / C + 6.3 真机修复全完成，第 3 天 go/no-go 通过——chunk 级引用跑通，未降级为文档级）。① 新增 **[`docs/release-notes/v1.2.0.md`](./release-notes/v1.2.0.md)**（5 commit ／ 56 files ／ 契约路径 8→10 ／ pytest 297 passed ／ 受控问题集 14 问覆盖率 100%）；② `sprint-calendar.md` §5 S6 → ✅ 功能收尾（**tag `v1.2.0` 待打**）+ §6 变更记录 v1.2；③ `settings.app_version` **1.1.0 → 1.2.0**（与打 tag 同一动作，§3.3；`check_seams.py` 版本闸门输入）；④ **未完项显式登记（不伪装完成）**：P2-3 矩阵对账、`changes/Sprint6.*` 归档、tag / merge main / push 均未执行（收尾 B 清单）；⑤ 遗留：实体抽取质量低（整句成实体、数值独立成节点、同实体重复 3 份）推 **S9**；`Citation.char_offset` 恒 0、`_snippet` 的 strip + 省略号导致摘录≠原文区间，推 **S10**（见 release notes v1.2.0 §6.1 / §6.2 / §6.3）。

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
| **P2-3** | **`acceptance-traceability-matrix.md` 对账**：本 Sprint 承接的 spec §3 验收条逐个勾选 + 涉及的 H 行「现状」列刷新 | ⏳ 未开始（**S6 待办**） | 架构师 + 各模块负责人 | — | 已写入 §9.2 第 3 项；**任一行「判据」或「验收人」为空 → 不得收尾**。**2026-09-23**：S6 功能与门禁已达标但**本项未做**，随「tag 前 B 清单」执行（不得借"功能收尾"跳过） |

---

## 4. P3 — Sprint 13 上线 gate

| # | 行动 | 状态 | 责任人 | 完成时间 | 备注 |
|---|---|---|---|---|---|
| **P3-1** | §15.3 现状列加代码行号引用 + §15 逐行勾选 + §3.2 B 五条对账 + **`acceptance-traceability-matrix.md` §4 / §5 全表终审（48 条 spec 验收 + 12 条 H + C1–C3 / F1–F5）** + `check_seams.py --strict` + 契约零漂移 + 前端 typecheck/lint | ⏳ 未开始 | 架构师 + 后端 B + 前端 FE | — | Sprint 13 收尾统一做（§20.3 DoD） |

---

## 5. prompts S9~S13 核账（已澄清；**2026-09-23 追加两笔 Prompt 治理欠账**）

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

**2026-09-23 追加（S6 收尾盘点：两笔 Prompt 治理欠账 → Sprint 8 批次 C 治理）**

> 上述「参数化」结论本身没错，但**对生产链路不成立**，必须一并记录，否则后续 Sprint 会照着它做错设计。

1. **`entity_relation_extract_v1.md` 无代码消费者**：上表 S9 / S12 两行假定「复用该模板做参数化」，但生产链路在 `backend/app/services/extraction/langextract.py` 第 293–295 行**硬绑** `load_prompt("kg_extraction", …)`，实际消费的是 `kg_extraction_v1.md`；而 `entity_relation_extract_v1.md` 全仓仅出现在 `app/tasks/registry.py` 第 182 行**注释**中——两套抽取模板语义重叠、其一悬空。
   **连带后果**：给 M4 扩实体类型（法人 / 地址）**不能靠参数注入**，只能走**新增 `kg_extraction_v2.md`**（详见 `changes/Sprint7.1/proposal.md` What Changes 第 1 条与其「纠正」说明）。
2. **类型枚举两侧不一致**：`kg_extraction_v1.md` 第 25 / 37 行的 `entity_type` / `relation_type` 枚举含 `VENUE` / `PRODUCT`，而 `langextract.py` 的 `ENTITY_TYPES` 仅 6 类——**谁为准尚未裁决**。

两笔与 `backend/CODEBUDDY.md` §4 的 **S6-5 / S6-6** 是同一批事项；处置落点统一为 **Sprint 8 批次 C 治理**（销毁 / 合并模板 + 统一枚举口径），本次只登记、不处置。

**2026-09-23 追加（Sprint 7.1 批次 A：`kg_extraction_v2` 已落地，本节口径需随之更新）**

| 项 | 内容 |
|---|---|
| 新增版本 | `prompts/kg_extraction_v2.md`（**v1 文件不动**；`EXTRACTION_PROMPT_VERSION` 默认切 v2，`.env` / `.env.example` 同步） |
| 为什么必须新增 | 上表 S9 / S12 假定的「参数化」走的是 `entity_relation_extract_v1.md`（无代码消费者）；生产链路消费 `kg_extraction`，而 v1 的枚举是**写死**的 → 扩 M4 法人 / 地址只能新增 v2 |
| v2 相对 v1 的改动 | ① 枚举参数化为 `{{entity_types}}` / `{{relation_types}}`（由 `langextract.py::_render_extraction_prompt` 注入，**按模板声明给值**，v1 不会收到这两个变量）；② 新增「法定代表人 / 注册地址」few-shot 示例 3 |
| 新增类型 | 实体 `LEGAL_PERSON`（自然人法定代表人）/ `ADDRESS`（注册地址）；关系 `LEGAL_REP`（ORG→LEGAL_PERSON）/ `REGISTERED_AT`（ORG→ADDRESS） |
| 未变 | 未知类型降级 `RELATED`、`confidence < 0.5` 丢弃、拒答兜底、上限裁剪——v1 第 47–50 行约束全部沿用 |
| 连带 | 上表「S9~S13 复用 v1（5 件）」的 5 件**统计不含**本次 v2（v2 属 S7.1 引入，与 H9 行同口径）；S8 批次 C 治理时须把 v2 一并纳入「销毁 / 合并」裁决范围 |

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