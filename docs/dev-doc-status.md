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

**2026-09-24 追加（Sprint 7 收尾登记）**：S7 于 **2026-09-24 功能达标**（较计划区间 10-21→11-03 提前 28 天；前置还债批次 7.0 + 批次 A / B / C / D 全完成）。① 新增 **[`docs/release-notes/v1.3.0.md`](./release-notes/v1.3.0.md)**（13 commit ／ 94 files ／ +13893 ／ −1054 ／ 契约路径 10→14 ／ pytest 297→368 passed ／ `check_seams` **ERROR 0 / WARN 2 / OK 8**）。② `settings.app_version` **1.2.0 → 1.3.0**（`config.py:92` + `.env.example:9`）；**连带动作**：`contracts/openapi.yaml` 的 `info.version` 取自 `app_version`（`test_openapi_contract.py:93` 有断言守着），故 bump 后**必须重导契约**，否则契约零漂移门禁必红——已重导并 `--check` 通过（diff 仅 `version: 1.2.0 → 1.3.0` 一行）。③ `sprint-calendar.md` §5 S7 → ✅ 功能收尾（**tag `v1.3.0` 待打**）+ §6 变更记录 v1.3。④ **接缝闸门生效**：接缝 5 / 7 / 8 判据由「未到期只记 WARN」转 **ERROR**，三者 bump 前实测已 OK，故 bump 后仍 **ERROR 0**；余 2 条 WARN 为未到期接缝 6（1.4.0）。⑤ **缺口 S7.1-7 关闭**：M4「两层并存」（`:Entity` + `:Subject`）已落 release notes §6.9。⑥ **已完成**：`app_version` bump 至 1.3.0、tag **`v1.3.0` 已于 2026-09-24 打在 `f0b7ff9`**、`changes/Sprint7.{0,1,2,3,4}` **已归档**至 `changes/archive/2026-09-24-Sprint7.N/`（26 个文件，100% rename）。**已完成**：矩阵 P2-3 逐行对账（§9.2 第 3 项）已做——新增矩阵 §3.3「M4 §3 验收 1–7 逐条对账」+ H 行与 C2-c 现状刷新 + `plan.md` §15.2 / §15.3 同步 + `specs/m4` §6 缺口登记；`push` 已由用户执行（2026-09-24）。**未完项显式登记（不伪装）**：**S6 侧**矩阵对账仍 ⏳ 待办（不因 S7 完成而勾销）；§9.2 第 8 项（操作手册章节）对 S7 **不适用**——P2-2 的范围是「操作手册 **Sprint 9~13** 章节（阶段十八~二十二）」，S7 无对应章节，非漏做；遗留技术债见 release notes §6（三类算法与 0.95 对齐率 → S9，证据粒度 chunk 级 / `char_offset` 恒 0 / chunk 原文含 HTML 表格标记 → S10，准入指标 → S13，`reviewed_by` 取自 dev 脚手架 → S11）。⑦ **收尾期观察（非阻塞）**：`tests/test_kg_versioning.py::test_get_active_returns_latest_ready_for_same_org` 在 bump 后首次全量跑时**偶发失败 1 次**，单跑 / 该文件内跑 / 全量复跑均通过（368 passed），判定为**偶发**而非回归；未改任何测试或阈值，如实登记以便复发时追溯。

**2026-09-26 追加（Sprint 8 收尾登记：审计闭环 + 演示打磨 + 8 接缝收口 ⇒ tag `v1.4.0`，Demo-MVP 完成点）**：① **范围**：11 个 commit ／ **57 files ／ +5138 ／ −33**（4 个代码批次：A 审计最小闭环 `cb919ab7` 26 files ／ B 限流 + 逃生阀 + S7.2-2 `36d4c26c` 20 files ／ D A16 settings 标注 `0e0b7033` 6 files ／ E 接缝 6 收口 `d67bc206` 13 files；7 个为依赖与规划文档 commit）。② **契约**：路径 **14 → 16**（`GET /api/v1/audit`、`GET /api/v1/audit/trace/{trace_id}`，新增 3 schema）；错误码新增 **`RATE_LIMITED`**（429，含 `429 → RATE_LIMITED` 兜底映射，避免兜底成 `HTTP_ERROR`→500）；**无改名 / 无删除**；`info.version` 随 bump **1.3.0 → 1.4.0**。③ **bump 连带动作（漏了必红）**：`app_version` 1.3.0 → **1.4.0**（`config.py:92` + `.env.example:9` + **本地 `.env`**——后者会**覆盖**默认值，不改则本地导出仍是 1.3.0，出现「本地红、CI 绿」）；`contracts/openapi.yaml` 的 `info.version` 取自 `app_version`（`test_openapi_contract.py:98` 断言守着）⇒ 已重导并 `--check` 通过，**diff 仅 `version` 一行**。④ **接缝闸门**：接缝 6 `required_from = 1.4.0` 的两项（接口实现 + `app/services/export/` 目录）由 WARN 转 ERROR，因批次 E 已提前落地 ⇒ `check_seams.py` **ERROR 0 / WARN 0 / OK 9**（WARN 归零），**`--strict` 全周期首次 exit 0**（plan §7.2 第 6 / 7 条的机械判据达成）。⑤ **门禁**：`ruff check` 全过 + `ruff format --check` **125 files** ／ `pytest -q` **392 passed** ／ `export_openapi.py --check` 零漂移 ／ `gen:api` 无 diff ／ 前端 lint / typecheck 0。⑥ 新增 **[`docs/release-notes/v1.4.0.md`](./release-notes/v1.4.0.md)**：**§6 对 plan §7.2 十条逐条对账 = 7 达成 / 2 部分达成 / 1 未达成**，§7 登记 8 项已知限制（受控问题集 NOT PASS 因语料漂移、批次 D 另两项未做、黄金路径步骤 6「同一 trace ≥7 条」未实测、`graph/overview` `entity_count=0` 未排查、M5 剩余缺口 → S11 等）。⑦ **定性不变**：`v1.4.0` 是**中途演示点**，对外**不得**称「MVP 1.0 已完成」（目标交付 `v2.0.0` / Sprint 13）。⑧ **2026-09-26 收尾已执行（留痕）**：提交 **`97950b25`**（`chore(release)`，9 files ／ +225 ／ −12，含新 notes）→ **`18ed2db3`**（`chore(archive)`，Sprint 8.2 / 8.3 / 8.4 三个目录 **100% rename** 至 `changes/archive/2026-09-26-Sprint8.N/`）→ push `d67bc206..18ed2db3`；**tag `v1.4.0` 已打并推送**（附注 tag，`git ls-remote --tags` 可核）。**push 仍拒 9 次后第 10 次成功**（`Recv failure` / `Failed to connect`，本机 GitHub 网络时好时坏，非 DNS）⇒ 再次验证「**push 失败直接重试即可**」这一结论。**CI（PR #3，run `36219182280`，sha `18ed2db`）4/4 全绿**：契约校验 30s ✅ ／ 后端 19s ✅ ／ 前端 31s ✅ ／ 流水线汇总 38s ✅。**待执行（等用户点头）**：PR #3 转正式 → Merge 到 `main`。

**2026-09-26 追加（收尾期修复：`GET /graph/overview` 三个统计值恒为 0 —— 静默假数据）**：① **症状**：演示第 2 步「看图」显示 `entity_count = 0`（图谱有节点，只有计数是 0）。② **根因（¥0 只读排查确定，非数据问题）**：`app/services/graphs.py::_fetch_graph_overview_stats` **直接 `return {"doc_count":0,"entity_count":0,"relation_count":0}`**，注释称「实际实现见 `GraphOverviewRoute._load_stats_from_pg()`」——而 `app/api/v1/routes/graph.py` **根本没有该方法**，且 `fetch_graph_overview` 手里的 `db` **没往下传**。③ **定性**：**静默假数据**（返回 0 冒充统计值）——合规占位必须显式报错（如 `log_export` 抛 `NOT_IMPLEMENTED`），给 0 属纪律要拦的"假做"。④ **修复**：统计值接 PG 真源（`KgVersioningService(db).get_by_version(...)` 取建图时 `mark_ready` 回填的 `entity_count` / `relation_count`，**不**走 Cypher `count(n)` 以免全表扫描）；`doc_count` 取 **`kg_version_id` 指向 active 版本 id** 的文档数（严格 **6** ／ 宽松 `IS NOT NULL` **7**，取严格——宽松会把历史版本文档混进 active 视图，违反 ADR-0002 §3.2）；真源缺失（无该版本行 / 漏传 `db` 或 `org_id`）**显式抛**（`NoActiveKgVersionError` → 409 / `ValueError`），**绝不静默 0**。⑤ **真机证据（真实 `dev.db`，¥0）**：active `v-s71a-fe1c4dc3` → **`doc_count 6 / entity_count 2000 / relation_count 819`**（修复前恒 0）；漏传 `db` → `ValueError`。⑥ **教训（已登记）**：原有用例把整个 `fetch_graph_overview` **打桩**，硬编码 0 因此**测不出来**（392 passed 照样红不了），只有真机能暴露 ⇒ 补 3 例直测统计真源，并把 conftest 的 `get_active` 桩**成对**扩到 `get_by_version`（否则「Neo4j 不可达」用例会因统计真源缺失被误判成 409 —— 已实测到该失败并修掉）。⑦ **门禁**：`pytest` **392 → 395 passed** ／ `ruff check` 全过 + `format` 125 files ／ `check_seams` **ERROR 0 / WARN 0 / OK 9**（`--strict` exit 0）／ 契约零漂移（本次**不改契约**）／ `gen:api` 无 diff。⑧ **tag 处置（用户选 A）**：修复提交落在 `v1.4.0` tag **之后** ⇒ **重打 tag `v1.4.0`** 到新 HEAD（force update，已获用户明确同意），使 v1.4.0 **不带**这个静默假数据。**已执行**：本地 `git tag -f -a v1.4.0`（`2df7be10` → `782096d0`，指向 `5f6ea7cb`）+ `git push -f origin v1.4.0`（forced update），`git ls-remote --tags origin` 核到 `refs/tags/v1.4.0^{}` = **`5f6ea7cb`**。⑨ **CI（PR #3，run `36226648736`，sha `5f6ea7c`）success**（重打 tag 前已复核）。详见 [`docs/release-notes/v1.4.0.md`](./release-notes/v1.4.0.md) §7.5。

**2026-09-26 追加 2（Docker / Neo4j 起后的真机点验 —— 又抓出并修掉 2 个真机 bug）**：① **背景**：上一版 v1.4.0 收尾时 Docker 没起，`/graph/overview` 修复只有「真实 `dev.db` + 代码路径」证据，**没有端到端 HTTP 点验**。本次补做：`docker start neo4j` + `uvicorn` + 真实 HTTP → `/health` ok（`1.4.0` / `database=up`）／ `/graph/overview` **`doc 6 / entity 2000 / rel 819`**（`kg_version=v-s71a-fe1c4dc3`，`nodes 500 / edges 36`）／ `/entities/{id}` 通（`type='ORG'` `category=org` `rel 6`）／ `/audit` `total 48`（含 `graph.overview` / `graph.entity` 落库）／ `/documents` `total 9`。**未点验**：`POST /agent/query` 会**真烧 LLM token**，¥0 纪律下本轮不做。② **新 bug A（Cypher 聚合嵌套）**：`_QUERY_ENTITY_DETAIL` 里 `count(collect({rel: r, neighbor: n})) > $neighbor_limit` —— Neo4j `SyntaxError`（*Can't use aggregate functions inside of aggregate functions*），被 `except Exception → GraphUnavailableError` 包成 **501「图谱不可用」**，即把**语法错**伪装成**基础设施故障**；演示第 3 步「点实体」**必现**。修：拆两段 `WITH`，先 `collect(...) AS all_neighbors`，再切片 + `size(all_neighbors) > limit`。③ **新 bug B（属性名错配）**：`kg/builder.py` 写 `n.entity_type`，读侧三处却读 `properties["type"]`——真库无 `type` 属性 ⇒ `entity_type` **恒空**、`category` **恒兜底 `topic`**（第 2 步全节点一个颜色、第 3 步类型列空白）。修：新增 `_entity_type_from_properties()`（`entity_type` 优先、`type` 仅旧数据兜底）统一三处读侧；分类表补**英文枚举**映射（`ORG` / `LEGAL_PERSON` → `org`，`REGULATION` / `CONTRACT_CLAUSE` → `norm`；真实抽取落的是英文枚举，原表只有中文 M4 mock 词）。**真机复验**：概览分类 **`org=264 / topic=236`**（此前全 topic）、类型 `ORG=264 / DATE=192 / MONEY=22 / PERSON=22`（此前全空）。④ **一次自我纠偏**：写助手时我加了 `str()` 强制转换，被既有用例 `test_fetch_document_subgraph_raises_on_contract_mismatch[entity-type-not-str]` 抓红——把契约不符的 `int` 静默转 `"123"` 属"假做"，改为**原样透传**由 schema 显式报错。⑤ **门禁**：`pytest` **395 → 398 passed** ／ `ruff check --fix` + `format` ／ `check_seams` ERROR 0 WARN 0 OK 9（`--strict` exit 0）／ 契约零漂移 ／ `gen:api` 无 diff。⑥ 详见 [`docs/release-notes/v1.4.0.md`](./release-notes/v1.4.0.md) §7.5.1。

**2026-09-26 追加 3（真机黄金路径步骤 6 —— 后端判据已实测达成，演示路径未闭合）**：① **做了什么**：用户放行烧 token 后，真机跑通黄金路径步骤 6——手工透传同一 `X-Trace-Id` 连走 7 步（`documents` → `overview` → `entity` → `document.graph` → `document.status` → `audit.list` → **`POST /agent/query` 真实 LLM**）→ `GET /api/v1/audit/trace/{tid}` 聚合 **7 条**（`document.list` / `graph.overview` / `graph.entity` / `document.graph` / `document.status` / `audit.list` / `agent.query`），PG 直读 `audit_log` 同值 = 7 ⇒ **「≥7 条共享同一 trace_id」后端侧实测达成**。② **真实 LLM 问答结果**（产生费用，用户已放行）：问「招商局蛇口工业区控股股份有限公司的法定代表人是谁？」→ `refused=false` / `route=m3_graphqa` / `citations=1` / 答案"蒋铁峰" + `[source: chunk-08905753912b]`；`qa_logs` 真落库（`refused=0`、trace 同值，累计 16 行）——矩阵 H4 行原写「`qa_logs` 打点未落」为**过期口径，已更正**。③ **仍未闭合（不粉饰）**：前端 `frontend/src/api/client.ts::request()` **只读不发** `X-Trace-Id`（仅用于 `ApiError.traceId`）⇒ 浏览器自然操作每请求一个新 trace，演示时审计页**不会自然聚合**。④ **为什么不在本版顺手透传**：让全站共用同一 `trace_id` 会让 per-request trace **失去排障价值**，与 **H4**（trace 全链路定位）直接冲突；正确解是引入**独立的「演示会话 trace」维度**（后端加 `session_trace_id` 列或前端仅演示态透传），属**新增设计** ⇒ **→ S11**（与 M5 三粒度同批）。⑤ **口径同步**：`docs/acceptance-traceability-matrix.md` 第 67 行（验收 6）与 M5 行均已从「未实测」更正为「后端实测达成 / 演示路径未闭合」。

**2026-09-26 追加 4（批次 D 第 1 项：种子数据集固化，¥0）**：① **产出**：`docs/demo-seed-dataset.md`——从本机库**反查实测**（`documents.filename_hash` = `SHA-256(切片文件名)` 逐条验证 `match=True`，切片实体在 `backend/storage/demo-slice/parts/`），固化 **3 份原件**（2 份募集说明书 + 1 份年报，含页数 / 字节数 / 内容 SHA-256）+ **按页切片规则**（`p1-190` + `p191-<末页>`）+ **6 个切片**（内容 SHA-256 / 文件名哈希 / 对应 `documents.id`）+ **重建步骤**（含关键坑：建图后 PG 只置 `ready`，**必须显式** `POST /graph/versions/{version}/activate` 才会同步 Neo4j 镜像）+ **¥0 复核判据**。② **口径修正（基于证据，非照计划凑数）**：原设想「选 2 份年报」，实测 active 图谱 `v-s71a-fe1c4dc3` 的源是 **3 份 / 6 切片** ⇒ 按实测固化为 3 份；只选 2 份会让重建结果与现有图谱**不同源**，§7.2 受控问题集换版就失去基准。③ **限制如实登记**：重建生成**新** `kg_version`（LLM 非确定性，实体数不逐字复现，现基线 2000 / 819 仅供参照）；切片经工具**重编码**（字节和 ≠ 原件，内容哈希不可由原件推导）；**无一键脚本**（本机切片由一次性脚本产生，痕迹在 `storage/demo-slice/logs/`，未归档为工具；脚本化与彩排脚本同属降级项）；**本版未真跑重建**（烧 MinerU + LLM 费用、会写演示库，建议独立 org）。④ notes §7.3 已同步为「种子集 ✅ / 彩排脚本 🟡」。

**2026-09-24 追加（Sprint 8.4 批次 E：集成接缝收口 —— `ExportSink` + `log_export` 合规占位）**：① **为什么排在收尾之前**：`check_seams.py` 接缝 6 的 `required_from = 1.4.0`——**bump 那一刻 WARN 就变 ERROR**（proposal.md:81 原话「1.4.0 到期，bump 时转 ERROR，**别拖到最后一天**」），且 plan §7.2 要求「**8 个接缝全部落地**」⇒ 本批次是 Sprint 8 收尾的**前置**。② **实现**：新增 `app/services/export/`（`ExportSink` 接口 + `ExportPayload` / `ExportResult` + `EXPORT_FORMATS` + `ExportFormatError`）+ **唯一实现 `JsonCsvExportSink`（json / csv 同属**一个类**，拆成两个会撞 `max_impls = 1` 判越界）**；**不做 HTTP 端点**——走端点即**集成**（须进契约 + 鉴权 + 审计），与 ADR-0004 §3 第 1 条「只预留不做集成」冲突 ⇒ 契约保持零漂移。③ **合规占位**：`settings.log_export`（唯一消费点 `core/logging.py::setup_logging`，`main.py` 传入），置 true 时抛 `AppError(NOT_IMPLEMENTED)`——**显式报错，不静默无效**（ADR-0004 §3 第 5 条例外登记）。④ **文档**：ADR-0004 §2.1 第 6 行补实现类名 `JsonCsvExportSink`（门禁 `adr_tokens` 仍逐字匹配）+ §4 补「当前实现 / 扩写纪律」；`backend/CODEBUDDY.md` §4 接缝清单 —— **8 个接缝全部已落**。⑤ **门禁**：`ruff check` 全过 + `ruff format --check` 125 files（1 file 已格式化）／ `pytest -q` **387 → 392 passed**（+5）／ `check_seams` **ERROR 0 / WARN 0 / OK 9**（接缝 6 两项由 WARN 转 OK，**WARN 归零**——不等 1.4.0 上闸就提前落地）／ `export_openapi.py --check` 零漂移。⑥ **不动**：`app_version`（仍 1.3.0，bump 属收尾单独一步）、契约、前端；**未完成**：批次 D 另两项（种子数据集固化 / 演示彩排脚本）仍待用户裁决。详见 [`changes/Sprint8.4/integration-log.md`](../changes/Sprint8.4/integration-log.md)。

**2026-09-24 追加（Sprint 8.3 批次 D：A16 settings 页「演示环境」标注）**：① **处置方式**：按决策 A16 **加标注、不隐藏路由**——隐藏会让 plan §7.2「演示剧本 6 步零假数据」硬门槛**失去可核性**（验收者分不清是"没有这个页面"还是"页面有假数据"）。`components/common/placeholder-page.tsx` 新增 `badge` / `notice` 两个插槽；`app/settings/page.tsx` 标题右侧挂「演示环境」`Badge` + 说明卡四条**可核**事实：契约**无** `/settings*` 路径 ⇒ 本页无配置项、也无 Mock 数据 ／ 演示语料 `docs/annualreport/`（招商局系 2025 年报 **10 份** PDF）／ 文档·图谱·问答·疑点·审计走真实接口且**多轮会话列表仍为 Mock（如实写明豁免）** ／ 身份走开发态请求头 `X-Org-Id`·`X-Actor-Id`（`LocalAuthProvider`）+ 限流 60/min（429 `RATE_LIMITED`）。② **顺手修一条假声明**：`lib/nav.ts` 中 `/audit` 去掉 `placeholder: true`（批次 A 后已是真实页；该字段当前无 UI 消费点，改动零风险）。③ **不动**：契约 / 后端 / 接缝 / `app_version`（仍 1.3.0）。④ **真机点验（¥0，纯静态页、零接口调用）**：`NEXT_PUBLIC_USE_MOCK=false` 起 `next dev` → `GET /settings` **HTTP 200**（29,322 B），HTML 含「演示环境」「功能预留」「docs/annualreport」「LocalAuthProvider」「RATE_LIMITED」「多轮会话」，且 `href="/settings"` 存在 ⇒ **未隐藏路由**；默认 Mock 态同样 200 且两条文案均可见。⑤ **门禁**：`tsc --noEmit` exit 0 ／ `npm run lint` exit 0 ／ `gen:api` 重生成后 `git diff --stat` 无输出（契约与类型**零漂移**）／ `pytest -q` **387 passed** ／ `check_seams` **ERROR 0 / WARN 2 / OK 8** ／ `export_openapi.py --check` OK。⑥ **批次 D 另两项（种子数据集固化 / 演示彩排脚本）未做**，待用户裁决。详见 [`changes/Sprint8.3/integration-log.md`](../changes/Sprint8.3/integration-log.md)。

**2026-09-24 追加（Sprint 8.2 批次 B 完成登记：M5 限流 + 逃生阀留痕 + S7.2-2 收口）**：① **契约**：ErrorCode 枚举新增 **`RATE_LIMITED`**（`errors.py` 六处登记 → `export_openapi.py` 重导 `contracts/openapi.yaml` **+7 / −1** → `gen:api` `api.d.ts` **+3 / −1**）；`429 → RATE_LIMITED` 兜底映射落位（否则任何 429 兜底成 `HTTP_ERROR`→500，违反矩阵判据）。② **限流装配**：`core/limiter.py`（`get_limiter`：每分钟每 IP 每接口 `rate_limit_per_minute` 次，默认 60，`.env.example` 同步）+ **自写纯 ASGI `RateLimitMiddleware`**（挂在审计之内）；`/health` 豁免（`EXEMPT_ROUTE_NAMES` 集中声明）。③ **A14**：同步 429 handler（`AppError(RATE_LIMITED).to_body(trace_id)` + `Retry-After` 按窗口粒度换算）+ 直写 `audit_log(action=rate_limit.triggered)`；`services/audit.py` 写入点登记制更新（中间件 + 429 handler + 逃生阀，新增调用方须先登记）。④ **A12**：`agents.py` fail-open 逃生阀放行时写 `tenant_leak.warn`；`backend/CODEBUDDY.md` 口径同步。⑤ **S7.2-2 偿还**：`list_in_flight_task_ids()` 补扫 `affiliation_tasks`（与 `recover_orphan_tasks` 同口径）。⑥ **实测三坑（源码逐行核对，详见 integration-log §2）**：FastAPI 0.141 `_IncludedRouter` 使 slowapi `SlowAPIMiddleware` **限流静默失效**（handler 恒 None → 全部被豁免）⇒ 自写中间件 + `_match` 下钻；slowapi 中间件对 **async 429 handler 静默回落**坏默认 ⇒ handler 必须同步；`@limiter.exempt` **导入时注册**会被换例弄丢 ⇒ 豁免集中声明。⑦ **真机**（`RATE_LIMIT_PER_MINUTE=3`，¥0）：限内 3 次 200 → 第 4/5 次 **429 + `Retry-After: 60` + 契约体**、`/health` 3 次全 200（豁免）；`dev.db` 直读 **`rate_limit.triggered` 2 行**（trace 与响应一致）。⑧ **门禁**：pytest **380 → 387 passed**（+7：限流 5 / S7.2-2 1 / A12 1）、`check_seams` **ERROR 0 / WARN 2 / OK 8**（与基线一致）、契约零漂移、`gen:api` 无 diff、ruff / lint / typecheck 全绿。⑨ **未做 / 未擅自动**：`alert` 表（P2）、RBAC / 脱敏 / RLS（S11）、`ExportSink`（批次 E）、受控问题集换版与 A16 settings 标注（批次 D）；**`app_version` 未 bump（仍 1.3.0）**。详见 [`changes/Sprint8.2/integration-log.md`](../changes/Sprint8.2/integration-log.md)。

**2026-09-24 追加（Sprint 8.1 批次 A 完成登记：M5 审计最小闭环）**：① **契约路径 14 → 16**（新增 `GET /api/v1/audit`、`GET /api/v1/audit/trace/{trace_id}`）；`git diff --stat contracts/openapi.yaml` = **368 insertions / 0 deletions**（既有 14 条路径一行未动）。② **两张表落地**（不做 migration，靠 `create_all`）：`audit_log`（M5 §4.4 11 字段）/ `qa_logs`（M3 §4.3 10 字段），均带 `org_id` 且复合索引 `org_id` 打头；**主键用 UUID 而非 spec 的 `BIGSERIAL`**，差异已登记 **`docs/adr/ADR-0003-tenant-isolation-rls.md` §3.1.1**（决策 A9）。③ **写入点**：`audit_log` 由新增纯 ASGI `AuditMiddleware` 全量写（allowlist 排除 `health`，决策 A1 / A2 / A5 / A6），**写失败只记日志不上抛**；`qa_logs` 在 `AgentService` 产出响应后落一条（成功 / 拒答都落，`question_hash` = SHA-256 不存原文，决策 A4）。④ **前端审计页关 Mock**：新增 `api/audit.ts` / `store/use-audit-store.ts` / `components/audit/*` 并重写 `app/audit/page.tsx`；**已同步 `CONTRACT_COVERED_PATTERNS`**；`NEXT_PUBLIC_USE_MOCK=false` 下 SSR 200（浏览器点验待用户）。⑤ **真机**：演示路径走一遍后直读 `dev.db` —— **`audit_log` 13 条 / 13 个 trace（判据 ≥7 ✅）、`qa_logs` 1 条**；**复用现有图谱未重建**（A13，active `v-s71a-fe1c4dc3`）。⑥ **门禁**：pytest **368 → 380 passed**、`check_seams` **ERROR 0 / WARN 2 / OK 8**（与基线一致）、契约零漂移、`gen:api` 无 diff、lint / typecheck / prettier 全绿、`ruff` 全绿。⑦ **花费**：LLM 提问 25512 tokens ≈ ¥0.053、受控问题集 14 问 ≈ ¥0.74（`EVAL_BASE_URL=:8123`），均低于 ¥1 护栏。⑧ **如实登记的未达成项**：受控问题集覆盖率 **100% 达成（3/3）**，但脚本 `拒答口径不符 11/14` ⇒ **NOT PASS**，归因**语料漂移**（问题集属于 Sprint 6 的年度报告语料，现 active 图谱为 Sprint 7.1 招商局系年报），与本批次 diff 无因果 ⇒ 登记为缺口「受控问题集需随演示语料换版」（批次 B / C）。⑨ **踩坑已登记**：首次真机打到了遗留旧进程（端口被占、新进程 `Errno 10048`），结果作废后换进程重跑。⑩ **未做 / 未擅自动**：RBAC 三粒度 / 脱敏器 / RLS（S11）、`alert` 表（P2）、`list_in_flight_task_ids()` 与 slowapi（批次 B）、A16 settings 页「演示环境」标注（批次 D）；**`app_version` 未 bump（仍 1.3.0）**。⑪ **2026-09-24 收尾已执行**：批次 A 提交 **`cb919ab`**（26 files ／ +3389 ／ −72）；**浏览器点验通过**（用户已看：`NEXT_PUBLIC_USE_MOCK=false` 下审计页 30 条记录 / 11 类 action / 每行 trace_id +「回看」）；`changes/Sprint8.1/` **已归档**至 `changes/archive/2026-09-24-Sprint8.1/` 并 push。详见 [`changes/archive/2026-09-24-Sprint8.1/integration-log.md`](../changes/archive/2026-09-24-Sprint8.1/integration-log.md)。

**2026-09-24 追加（Sprint 8 开工登记 + 长指南 §17.1 盘点结论）**：`changes/Sprint8.1/`（proposal / tasks / new-session-prompt）已建，`design.md` 按 A7 判定不需要（**该目录已于 2026-09-24 归档为 `changes/archive/2026-09-24-Sprint8.1/`**）。长指南 §17.1 要求的九项现状盘点**已于 2026-09-24 只读完成（未改码、未落盘）**，结论**带行号**写进 `proposal.md`「现状」表与「盘点结论」节。**四项改变方案的发现**：① `kg_nodes` / `kg_relations` / `token_usage` 是 `AgentQueryResponse` 响应字段（`schemas/agent.py:164/171/178`，契约 `openapi.yaml:584-595/621-625` 已有）**不是表** ⇒ 批次 C ① 是回填 spec / PRD 的契约层投影；② `GraphEdge.type` 代码 9 值（`schemas/document.py:27-37`）与 `m2:73-81` **逐字一致、无差异**，真正有出入的是 `LEGAL_REP` / `REGISTERED_AT`（不在契约枚举、读侧兜底 `MENTIONS`）；③ PRD 状态行"只复核"已由 `plan:310` 明写，`03-prd.md:5` 无需改，我先前担心的口径冲突**不存在**；④ 接缝 6 计数是 **`min=max=1`**（`check_seams.py:132-133`）⇒ `ExportSink` 实现类只能 1 个（拆 Json/Csv 两类即 ERROR）。决策由 A8 增至 **A16**（新增 A9–A16：UUID 主键 / 不复用 EventBus / slowapi 选型 / fail-open **保留**逃生阀 + 审计留痕 / 真机复用现有图谱不重建 / `rate_limit.triggered` 纳入批次 B / 受控问题集与现语料不同源如实登记 / settings 页加"演示环境"标注）。**两件开工阻塞项**：试装 `slowapi`（`pyproject.toml:10-23` 与 `uv.lock` 均无）、向用户确认 DeepSeek 余额（不许推测）。**两处口径已显式登记不静默**：① plan §7.2「≥7 条」**不**理解为"同一 trace_id 下 7 条"——后端任务由 `tasks/manager.py:233-241` 另生成 trace_id；② 疑点复核**不改** `patch_suspicion_status()` 签名（PATCH 是独立请求，审计中间件覆盖即可，改签名属范围蔓延）。**批次 C 漏项**：`plan:467` 第 5 项 `docs/multimodal_rag_backend_api_spec-v1.0.md` 6 处过期描述清理本次未盘点，批次 C 须补。

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
| **P2-3** | **`acceptance-traceability-matrix.md` 对账**：本 Sprint 承接的 spec §3 验收条逐个勾选 + 涉及的 H 行「现状」列刷新 | ✅ **S7 已完成（2026-09-24）；S6 已补做（2026-09-24，历史补做）** | 架构师 + 各模块负责人 | S7：2026-09-24；S6：**补做** 2026-09-24 | 已写入 §9.2 第 3 项；**任一行「判据」或「验收人」为空 → 不得收尾**。**2026-09-23**：S6 功能与门禁已达标但**本项未做**，随「tag 前 B 清单」执行（不得借"功能收尾"跳过）。**2026-09-24 S7 收尾**：矩阵新增 §3.3「M4 §3 验收 1–7 逐条对账」（结论：2 达成 / 2 部分 / 3 未做）；H1 / H3 / H4 / H5 / H10 / H12 与 C2-c 现状刷新；`plan.md` §15.2 / §15.3 的 M4 行同步；`specs/m4` 状态行 + 新增 §6「已登记的实现缺口」。**S6 侧旧账已于 2026-09-24 补做完成**：矩阵新增 §3.4「M2 / M3 §3 验收 1–7 逐条对账」（**14 条：5 达成 / 4 部分 / 5 未做**）；判据取自 `changes/archive/2026-09-23-Sprint6.{1,2,3,4}/integration-log.md` **并回到 2026-09-24 的当前代码复核**（不只抄当时结论）；M2 / M3 行与 **H4 / H8** 现状刷新；`plan.md` §15.3 M2 / M3 行同步；`specs/m2` / `specs/m3` 状态行 + 新增 §6「已登记的实现缺口」。**实质发现（口径更正）**：原先多处文档写的「M2 **`confidence` 不落库**」经代码核实为**错误**——已随 v1.2.0 写入节点 / 关系属性，三处一并更正并留更正理由。**另一条**：`qa_logs` 至今**未建表**，M3 验收 3 / 7 的「打点」今天仍不成立。⚠️ 本节为**历史补做**，核实日期统一标 2026-09-24，**不冒充** S6 当日结论 |

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