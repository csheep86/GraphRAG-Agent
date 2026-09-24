# Proposal: Sprint 7.1 批次 A —— M4 数据与规则型疑点算法

> **状态**：**决策已拍板（2026-09-23）；代码未动工**——按既定分工，S7 各批次在 **Sprint 7 专属新会话**开工，本会话只产出规划、不动代码。
> **接手工序**（新会话照此开局，不需重读历史对话）：① **先做** `changes/Sprint7.0`（前置还债批次，已批准）；② 读本文「决策点」表确认口径；③ 按 `changes/Sprint7.1/tasks.md` 顺序执行，每项都在 `integration-log.md` 留真机证据。
> **定位**：本提案只覆盖 plan §6.2 的**批次 A**。批次 B / C / D 分别由 `changes/Sprint7.2` / `7.3` / `7.4` 承接，**不在本提案范围内**。
> **上游依据**：`docs/v1.1.0-demo-mvp-plan.md` §6（Sprint 7 = v1.3.0，2 周，分支 `feature/sprint-7`）、`specs/m4-affiliation-detection.md`、`docs/adr/0004-integration-seams.md` §2.1（接缝 5 / 7 / 8 落 S7）。
> **前置依赖**：`changes/Sprint7.0`（**抽取链路接真实 LLM**）——不先还清这笔债，本批次产出的疑点是伪数据，理由见决策点 **D3**。

## Why

M4（财务关联交易识别）当前 **0%**（矩阵 §3.1：`❌ 0%`），是 PRD 的核心场景，也是准入线 C1 / C2 的唯一载体。S7 要交付它的**最小闭环**：**只做 1 类规则型算法**——「同一法人 / 同一注册地址跨公司」（plan §6.1：数据现成、Cypher 两跳即可、演示冲击力强）。

三件必须在 S7 落地的硬事实：

1. **`check_seams.py` 的三条规则 `required_from = 1.3.0`**——S7 收尾 bump `app_version` 到 1.3.0 后，它们会从 **WARN 升为 ERROR**，不实现则 CI 必红：
   - 接缝 5：`EventSink` 接口 + **仅 `db` / `log` 两个**实现（`check_seams.py` `InterfaceRule` 第 119–127 行，`adr_tokens=("db","log")`）；
   - 接缝 5 存在性：`PresenceRule(table=domain_events, 1.3.0)`；
   - 接缝 7：`PresenceRule(table=external_refs, 1.3.0)`；
   - 接缝 8：`PresenceRule(path=app/services/external_data, 1.3.0)`。
2. **管线坑位已留好但未接线**：`settings.pipeline_stages` 默认值**已含 `risk.detect`**（`app/core/config.py` 第 70–75 行），`EXECUTOR_REGISTRY` 当前只有 `document.parse` / `document.extract` / `kg.build`——**未登记执行体的阶段自动跳过**（`tasks/pipeline.py` 第 6–8 行）。S7 要把 `risk.detect` 接上。
3. **表名已被 T14 锁死**：必须逐字用 `affiliation_tasks` / `affiliation_suspicions` / `unaligned_subjects`，**S9 不得再做表结构迁移**（plan §6.3 第 3 条）。

## What Changes

批次 A 范围内：

1. **抽取侧扩类型 = 新增 `prompts/kg_extraction_v2.md`**（**不覆盖 v1**）：把 v1 里写死在 JSON Schema 的 `entity_type` / `relation_type` 枚举提取为 `{{entity_types}}` / `{{relation_types}}` 占位符，注入 `LEGAL_PERSON` / `ADDRESS` 与 `LEGAL_REP` / `REGISTERED_AT`；`EXTRACTION_PROMPT_VERSION` 切 v2 生效，同步扩 `langextract.py` 的 `ENTITY_TYPES` / relation 枚举。
   > **纠正（2026-09-23）**：初稿写的「用 `entity_relation_extract_v1.md` 的参数化、不新增版本」**是错的**。核实结果——生产链路在 `langextract.py` 第 293–295 行**硬绑** `load_prompt("kg_extraction", …)`；而 `kg_extraction_v1.md` 的占位符只有 `{{text}}` / `{{language}}`，类型枚举**写死**（第 25 / 37 行）。那份带 `{{entity_types}}` / `{{relation_types}}` / `{{domain_description}}` 的 `entity_relation_extract_v1.md` **无代码消费者**（全仓仅出现在 `registry.py` 第 182 行注释里）——详见决策点 **D4**。
2. **图写入增量（D1 + D5 已定）**：**新建 `:Subject`**（**不复用 `:Entity`**），并按 spec §4.2 属性定义同批建 `:Address` / `:LegalPerson` 与 §4.3 的 `(:Subject)-[:REGISTERED_AT]->(:Address)` / `(:Subject)-[:LEGAL_REP]->(:LegalPerson)` 两条关系；三节点**带 `kg_version`**（与 M2 共享同一 active 版本，**不分裂版本**，M4 §3 验收 2 / ADR-0002）。**不建 `(:Entity)→(:Subject)` 桥接关系**；`:Invoice` / `:Voucher` / `:Contract` / `:Phone` 仍归 **S9 批次 B**（plan 第 580 行）。
3. **两类规则算法**：Cypher 两跳——「共享法人跨公司」/「共享地址跨公司」，返回 `{type, entities[], evidence[]}`。
4. **`risk.detect` 挂管线**：实现执行体 + 登记 `EXECUTOR_REGISTRY`，使 `settings.pipeline_stages` 能启停它（`PIPELINE_STAGES` 删除 `risk.detect` 即停用）。
5. **证据引用复用 S6**：疑点的 `evidence` 落到 `:Chunk`（`(c)-[:MENTIONS]->(e)` 反查），为批次 B 的「引用覆盖率 100%」打底——这是 **S6 → S7 的唯一耦合面**。

## 决策点（**必须你先拍板，我不擅自偏离 plan**）

| # | 决策 | 选项 | 我的建议 |
|---|---|---|---|
| **D1** | plan §6.2 写「补 `:Subject` 节点」，但现有图谱的公司实体是 `:Entity`（`entity_type=ORG`）。**新建 `:Subject` 还是复用 `:Entity`？** | ① 按 plan 新建 `:Subject`（同一公司会出现 `:Entity` + `:Subject` 两个节点）；② 复用 `:Entity` 只新增 `:LegalPerson` / `:Address` 与两条关系 | ✅ **拍板 = ① 新建 `:Subject`**。理由：spec §4.2 第 64–66 行逐字定义了 `:Subject` / `:Address` / `:LegalPerson`；`:Entity` 是**抽取层产物**（per-**Chunk**、同一实体多种 mention 会重复——S6 真机已出现），**不适合当对齐主键**。**不建两者桥接关系**（不为 S9 提前写东西）；「两层并存」登记进 release notes v1.3.0 已知限制，统一交 **S9 批次 D 实体消解**（plan 第 582 行） |
| **D2** | `risk.detect` 的触发方式 | ① 挂进 `EXECUTOR_REGISTRY`（上传链路自动跑，接缝 4 语义完整）；② 独立 task_type，由接口手工触发 | ✅ **拍板 = ①**（符合 plan §6.2「Matrix 自动接线」与接缝 4「阶段可启停」的设计意图） |
| **D3**（已定论，非悬而未决） | 抽取侧能否产出法人 / 地址 | **已核实**：当前链路走的是正则占位器（`_default_extract_chunk`，只出 ORG / PERSON / MONEY / DATE），**配了 `LLM_API_KEY` 也不调 LLM**——所以**现在抽不出**法人 / 地址 | **先执行 `changes/Sprint7.0`（抽取接真实 LLM）**，再开工本批次。若不批 7.0：plan §6.4 的「换演示文档」无效（根因是抽取器），须在 plan §6.2 登记「S7 的 M4 为 mockable 演示」并在 release notes v1.3.0 显式声明——**不得静默** |
| **D4**（新增） | `prompts/entity_relation_extract_v1.md` **无代码消费者**，与 `kg_extraction_v1.md` 语义重叠（两套抽取模板并存，其一悬空） | ① 本批次只管新增 `kg_extraction_v2.md`，悬空问题留给 **Sprint 8 批次 C 治理**统一裁决（销毁 / 合并）；② 现在就切用它（占位符名不同 `{{text_chunk}}` vs `{{text}}`，改动面更大） | **①**（S7 不扩战线；但须在 `dev-doc-status.md` / `CODEBUDDY.md §4` 登记这条欠账，防止长期悬空） |
| **D5**（新增） | 「同法人」算法是否要在 S7 就建 `:LegalPerson` 节点（plan 第 580 行把它归 Sprint 9 批次 B） | ① S7 一次建齐 `:Subject` + `:Address` + `:LegalPerson`，S9 只补其余四节点；② 沿用 S9 归属，S7 只拿 `:Subject` 属性字符串比对法人 | ✅ **拍板 = ①**。spec §5.4 第 159 行的「同法人」Cypher **必须经 `:LegalPerson` 节点**（`(s1:Subject)-[:LEGAL_REP]->(l:LegalPerson)<-[:LEGAL_REP]-(s2:Subject)`）；选②偏离 spec 图模型，且 S9 还得返工改图 |
| **D6**（新增） | 演示数据集从哪来——算法要「跨公司」命中，须 ≥2 家存在共同法人 / 地址的公司 | ① **2–3 份互为关联的真实公司年报**（母子公司 / 同集团）；② 用 CSV 供应商主数据；③ 单份年报硬凑 | ⚠️ **拍板 ① 已被 7.0 真机证伪，须改数据源形态（不换公司、换文档类型）**。Sprint 7.0 结论（`changes/Sprint7.0/integration-log.md` §4.4）：**D6① 能抽出法人 / 地址**（招商公路切片：`杨旭东` 抽为 `PERSON` + `EMPLOYED_BY` 0.95；注册 / 办公地址抽为 `VENUE` + `RELATED` 0.93）——但 v1 枚举**无** `LEGAL_PERSON` / `ADDRESS`，故扩类型（v2）**是批次 A 的必需项**。**D6② 零交叉**：三份年报法人三人各异（杨旭东 / 朱文凯 / 冯波鸣）、地址三地各异（天津 / 深圳蛇口 / 上海自贸区），根因是年报天然只披露一家公司；且 `东方广场`（会计师事务所地址，三份共有）在 llm 档**真的被抽了出来** → 用年报只会产出「共享中介机构地址」伪交叉，违反 G5。**新建议**：改用**关联交易公告 / 债券募集说明书 / 招股说明书**（同时披露多主体名称 + 法人 + 住所），需人工从巨潮下载（列表 API 已收紧）。**禁止**调阈值 / 编数据凑疑点 |
| **D7**（新增，属 `Sprint7.2`（批次 B）范围，结论先登记在此） | PG 三表 `affiliation_tasks` / `affiliation_suspicions` / `unaligned_subjects` 的归属 | ① 批次 B 建表，批次 A 只留 4 个预留列；② 批次 A 一并建表 | ✅ **拍板 = ①**（批次 A 不建表，疑点以算法返回为准；表名逐字锁死于 T14 / plan §6.3 第 3 条） |

## Impact

**影响的契约（`contracts/openapi.yaml`）**：**本批次无变更**（算法为内部能力，对外端点在批次 B 的 `GET /affiliation/suspects`）。

> **口径消歧（2026-09-24，Sprint7.2 决策 B1）**：此处的 `/affiliation/suspects` 已统一为 **`/affiliation/suspicions`**（以本文批次 B 的实际口径为准，四端点见 `specs/m4-affiliation-detection.md` §5.5）。本文件为已收尾批次的历史记录，**正文保持原样**，仅在此消歧。

收尾须仍能通过 `export_openapi.py --check`（无 diff）。

**影响的前端（`frontend/`）**：**无**（疑点清单页属批次 C，届时须同步 `CONTRACT_COVERED_PATTERNS`——S6 批次 B 在此栽过一次，见 release notes v1.2.0 §3）。

**影响的后端（`backend/`）**：`app/services/extraction/langextract.py`（扩 `ENTITY_TYPES` / relation 枚举 + v2 注入）、`app/services/kg/builder.py`（建 `:Subject` / `:Address` / `:LegalPerson` 三节点与两条关系，**含 `kg_version` 与 `acl_scope`**）、`app/services/graphs.py` 或新增 `affiliation.py`（两跳 Cypher 算法）、`app/tasks/registry.py`（`risk.detect` 执行体）、`app/services/documents.py`（阶段串联，若需）。

**影响的 Prompt（`prompts/`）**：**新增 `kg_extraction_v2.md`**（v1 保留不动，Prompt 版本管理规范禁止原地覆盖）。同步动作：更新 `dev-doc-status.md` §5 与矩阵 H9 行（S6 引入 `kg_qa_v2.md` 时已走过同一流程）、`.env.example` 的 `EXTRACTION_PROMPT_VERSION`。

## Non-goals

- **不做**三方金额不一致检出、连通分量 / 共享邻居 / 环路检测（→ **S9**，M4 完整化）；
- **不建** `affiliation_tasks` / `affiliation_suspicions` / `unaligned_subjects` 三张表（→ 批次 B），因此本批次疑点**不落库**（算法返回结果为准）；
- **不做**接缝 5 `domain_events` / 接缝 7 `external_refs` / 接缝 8 `external_data`（→ 批次 D / B / B）——但须牢记 **1.3.0 bump 后它们从 WARN 升 ERROR**；
- **不顺手修 S6 遗留**：实体消解（→ S9）、`Citation.char_offset` 恒 0 / `_snippet` 省略号（→ S10）、qa 会话副标题 `doc_count=24` Mock 文案（→ 会话端点进契约时）——范围纪律，避免 S7 diff 失控；
- **不做**任何真实外部系统对接（工商 / 涉诉 / 主数据），只留接缝。
