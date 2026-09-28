# Sprint 9.5 · 考勤业务域 DEMO（任务清单）

> 提案：[`proposal.md`](./proposal.md)　|　状态：待开工
> **铁律**：本清单是**唯一执行口径**；与 `specs/` / `docs/` 冲突时以本清单为准。

## 执行纪律（沿用既有）

1. **契约同步 5 步走**（`backend/CODEBUDDY.md` §3）：改 spec → Pydantic 枚举 → `export_openapi.py` → `npm run gen:api` → 契约漂移检查。**任何接口/枚举变更必须走满 5 步**。
2. **零假数据**（A15）：图谱中每个节点必须能回溯到语料的具体行/页；**禁止**硬编码演示答案。
3. **数值不出 LLM**：所有数值结论（36h / 60h / 108h / 置信度）由**规则引擎确定性计算**，LLM 只做自然语言组织。
4. **演示语料标注**：产物全程标注「演示语料（仿真）」，**不得**称为真实客户数据（R9）。

---

## 批次 A · 语料与本体（架构师 + 后端 A）

- [x] **A1** 生成仿真语料包 —— **已完成**，`demo/attendance/generate_corpus.py`（seed 固定，零第三方依赖）
  - 4 份制度文档：`policies/*.md`（源）+ `corpus/*.docx`（M1 消费，标准库手写 OOXML 转换）
  - 9 张 CSV：`corpus/{employees,attendance_records,shifts,leave_requests,overtime_records,business_trips,work_orders,location_records,access_records}.csv`
  - **5 条演示用例已埋设并通过自检**（见 `README.md` §6）
  - 制度文档含 **2025→2026 版本更替**（外勤手工补卡 → 自动补卡），用于验证 ADR-0005 时效知识
  - `README.md` 已标注「演示语料（仿真），非真实客户数据」
- [x] **A2** 建 `ontology_schemas` 表 + 考勤 schema 种子 —— **已完成**
  - 模型：`backend/app/db/models.py::OntologySchema`，字段逐字照 M6 §4.1
  - **主键取 `(org_id, version)` 复合主键**（version 每 org 独立自增），
    与其余表的 UUID 单主键惯例不同——**以 spec 为准**；索引仍以 `org_id` 打头（ADR-0003）
  - 种子：`demo/attendance/ontology_schema.json`（实体 13 类 / 关系 14 类）
  - 写入：`backend/scripts/seed_attendance_ontology.py`，**幂等**（已有 `version=1` 则 SKIP）
  - 守 M6 §3.5 验收 12：`status=active` 视同已确认，`suggested_by_llm=false`，
    `confirmed_by_user` 取 `settings.default_actor_id`
  - **不做**冷启动 GUI / 校正界面 / 增量重算（保持 S12）
- [x] **A3** CSV→图谱映射配置 —— **已完成**，`demo/attendance/mapping.yaml`
  - 12 类节点 / 11 类关系；`POLICY_CLAUSE` 归 M2 抽取，汇合关系见文件末尾（B3 消费）

## 批次 B · 数据入图（后端 A）

- [x] **B1** 实现**结构化数据入图器**（接缝 8 扩展）—— **已完成**
  `backend/scripts/ingest_attendance_csv.py`
  - 读 `mapping.yaml`，CSV 行 → Neo4j 节点/关系，**确定性映射，不用 LLM**
  - **沿用真机图谱模型**（关键修正）：节点统一 `:Entity` + `entity_type` 属性、
    关系统一 `:RELATION` + `relation_type` 属性，与 `kg/builder.py` 逐字一致。
    *初稿按"每类一个标签"设计是错的*——`graphs.py` 全部查询只读 `:Entity`，
    多标签会导致数据**进得了库、查不出来、前端渲染不出**（2026-09-26 刚因同款
    错配出过"类型列空白、节点全一个颜色"的演示事故）。`mapping.yaml` 已升 v2
  - ADR-0002 三段式写入 + **写入自检**（回读计数不符即回滚）+ **演示用例可用性验证**
  - 实测：实体 2954 / 关系 3952 / `KgVersion=active` / 重跑幂等一致（870ms）
  - **不新建表**（延续接缝 8 范围纪律）
  - **B1-fix（2026-09-27 补，重要）**：脚本原先**只写 Neo4j `:KgVersion`、未登记 PG**
    ⇒ 按「PG 才是 kg_version 真源」（S6.3 收口，`graphs.py:496-500`）读侧拿到的是
    **旧的** active 版本 `v-s71a-fe1c4dc3`，考勤图**实测 `nodes = 0`**
    （数据写进去了却查不出来 —— 与 9-26 那次演示事故**同族错配**）。
    已补 `register_pg_kg_version()`：``pending → building → ready``，同版本幂等复用。
    复测：`kg_version=attendance-demo-v1` / 实体 2954 / 关系 3952 /
    **nodes 500 / edges 529**，分类分布 EMPLOYEE·DEPARTMENT·POSITION=`org`、
    WORK_TIME_SYSTEM=`system`（本体分类同时生效）。
    ⇒ 教训已写入脚本 docstring：**入图 ≠ 可查，两边都要登记**
- [x] **B1-follow** 图例分类**域化** —— **已完成**（选型 C：`category` 进本体，**契约零改动**）
  - `demo/attendance/ontology_schema.json` 每个 `entity_type` 补 `category` 字段
  - 新增 `backend/app/services/ontology.py`：`entity_type_categories()` 读该 org 的
    active 本体；**合法值由契约枚举反推**（`get_args(GraphCategory)`，不二次硬编码）
  - `graphs.py` 新增 `_resolve_category()`：**本体优先 → 内置表 → `topic` 兜底**；
    `_load_entity_type_categories()` **每请求解析一次**（不逐节点查库），
    失败则 warn 后回落，**不阻断查询**——图例是展示增强，不是数据正确性
  - 调用点注入：`fetch_entity_detail`、`fetch_graph_overview` → `_project_overview_nodes`
  - `seed_attendance_ontology.py` 增加**真源同步**：已存在但内容不一致时按 JSON 更新
    （`version` 不变、不擅自升版）——否则幂等 SKIP 会让新字段**静默不生效**
  - 实测：13 类 = `org` 3（EMPLOYEE/DEPARTMENT/POSITION）+ `norm` 1（POLICY_CLAUSE）
    + `system` 1（WORK_TIME_SYSTEM）+ `topic` 8（各类事实记录）；
    `EMPLOYEE` 有本体= `org` / 无本体= `topic`（覆盖生效），`ORG` 仍走内置表
  - 测试：`tests/test_ontology.py` 新增 6 项全绿，既有 16 项无回归；
    `export_openapi.py --check` 零漂移；`check_seams.py` ERROR 0 / WARN 0
  - **已知边界（方案 C 固有）**：`category` 仍是契约 4 值 ⇒ 8 类事实记录共享 `topic`
    一色。要逐类型分色须走方案 B（扩枚举，动契约 + 前端色板 + `gen:api`），**本 Sprint 不做**
- [x] **B2** 制度文档走既有 M1 解析 + M2 抽取链路，`entity_types` / `relation_types` **从 `ontology_schemas` 读**（M6 §5.2 参数化注入，**不新增 Prompt 版本**）—— **已完成**
  - 新增 `backend/scripts/ingest_attendance_policies.py`：注册 `Document` 行 → `document.parse`
    → `document.extract` → 汇合边（规则）→ `kg.build`，**完全复用既有执行体**；
    末段 `kg.build` 是 **MERGE 追加语义**（**不**先清版本）⇒ 与 B1 的 CSV 数据
    落在**同一个** `kg_version` 里天然汇合（若两边各建版本 ⇒ B3 那条跨源路径永远连不上）
  - **M1 支持 docx（本批次顺带打通，与 PDF 走同一条链路）**：`MineruClient.parse_pdf` → **`parse_document`**；
    后缀由 mime 映射（`registry._PARSE_MIME_TO_SUFFIX`），**实测确认 MinerU 云按文件名后缀选解析器**
    （".pdf / .docx 走完全相同四步流程"）⇒ **客户端不内置格式分支**，分支只留给调用方一份
  - **M6 §5.2 参数化注入**：新增 `services/ontology.py::extraction_type_vocabulary()` 读本体
    类型名；`LangextractClient` 新增 `TypeVocabulary`（Prompt 渲染与类型校验**同源**，
    避免"模型按新域抽、校验按旧枚举降级"的串味）+ `from_settings(entity_types=, relation_types=)`；
    **`prompts/kg_extraction_v2.md` 一行未改**（本来就有这两个占位符）⇒ 换域换数据、不改 Prompt 版本。
    本体读不到 ⇒ 空元组 → 回落内置枚举，两侧**独立**回落
  - **切片粒度随文档类型走**：`LangextractClient.from_settings(max_chars_per_chunk=)` +
    `document.extract` 的 payload 覆盖。**实测（真机，同一份 1478 字制度文档）**：
    4000 字切片 ⇒ 只抽到 **1** 条 `POLICY_CLAUSE`（把整份文档当成一个条款）；
    600 字切片 ⇒ **16** 条。故制度类按"条"切（脚本常量 `CLAUSE_CHARS_PER_CHUNK=600`）
  - 实测（4 份 docx，**真机 MinerU + 真机 LLM**）：full.md 799 / 1090 / 1570 / 1478 字符；
    抽取实体 49 / 43 / 54 / 64（其中 `POLICY_CLAUSE` 20 / 25 / 20 / 19 = **84**）
  - **清零关心的坑**：执行体吞错后只改状态列、不回抛 ⇒ 脚本每步后**回读 DB 状态列**判定；
    Cypher 对"端点不存在的边"是**静默跳过** ⇒ 校验按**关系 id 逐个核对**（114/114）
- [x] **B3** 校验两链路汇合：员工节点能沿 `APPLIES_WORK_TIME` → `GOVERNED_BY` 连到 `POLICY_CLAUSE` —— **已完成**
  - 汇合边**不由 LLM 生成**：`WORK_TIME_SYSTEM -[GOVERNED_BY]-> POLICY_CLAUSE` 按
    "条款所在自然段点名了某个工时制"匹配（确定性规则，可复核；id 用 `uuid5` ⇒ 重跑幂等）
  - 实测：`GOVERNED_BY` 共 69 条（规则桥接 21 + 模型自抽 48，按 id 前缀区分来源）；
    **B3 路径 288 条 / 员工 40 人 / 工时制 3 个 / 条款 15 条**
  - **入图 ≠ 可查**：每段文档的 `kg.build` 只登记**它自己**的计数 ⇒ 全部跑完后按 Neo4j
    **真实计数**重新 `mark_ready`（实体 **3164** / 关系 **4066**，= CSV 2954/3952 + 制度 210/114）
  - **真机 HTTP 复核（`uvicorn` + 真请求，非脚本打印）**：
    `GET /graph/overview` ⇒ `kg_version=attendance-demo-v1` / `doc_count=4` /
    `entity_count=3164` / `relation_count=4066` / `nodes 500` / `edges 527`、
    分类 `norm=17`（POLICY_CLAUSE）+ `org=58` + `system=6` + `topic=419`；
    `GET /entities/EMPLOYEE:E001` ⇒ `canonical_name=张伟`、`rel_count=97`、
    关系名 `SWIPED_AT` / `LOCATED_AT`（不再是裸 `RELATION` 令牌）
  - 顺手修的两处真机缺陷（见下方 L6 / L7）：① CSV 派生节点名字被表的 `name` 列污染；
    ② 实体详情关系名只读 `rel.type`（`:RELATION` 令牌），忽略 `properties.relation_type`

## 批次 C · 规则与归因（后端 B）

- [x] **C1** 实现**确定性规则引擎** —— **已完成**
  `backend/app/services/rules/`（`policy_values.py` 规则值 + `engine.py` 事实与规则）
  - **规则值从制度文本解析，不硬编码**（制度改了规则自动变）：7 个值**全部带出处**——
    ① 图谱 `POLICY_CLAUSE`（span 级）优先，② M1 产物 `full.md` 兜底。
    **为什么必须有第 2 级（实测，见 L8）**：真机 84 条条款里**只有 1 条**（36 小时）
    能解析出数值，只认图谱 ⇒ 5 条规则有 4 条直接哑掉。`full.md` 是**系统内产物**
    （M1 真实产出），不是代码旁的静态文件；实测 40h / 174h / 6h / 5 次 / 12 天 / 30 天
    全部命中（含被 MinerU 渲染成 HTML 的表格行）
  - **解析不到 ⇒ 该规则跳过并写进 `skipped_rules`，不用默认值兜底**（守 F3：无溯源即拒答）
  - **事实全部从图谱读**（不读 CSV，保证与前端同源），且**按 `id` 前缀过滤 CSV 派生节点**——
    同一个 `kg_version` 里混着 M2 抽取的噪声节点（实测 EMPLOYEE 47 个里只有 40 个是
    CSV 派生的，其余叫「全体在册员工」）
  - 五条规则 + **计算过程**（「月排班 216h（22 天）− 月标准 174h = 加班 42h > 上限 36h」）
    + 证据节点 id + 规则值出处
  - **口径分岔已实现**（§5.3）：综合制 = 月排班 − 月标准 174h；标准制 = 已审批加班单累计；
    不定时工作制不适用（跳过）
  - **一处口径细化（相对 §5.3，理由写在 `engine.py` docstring）**：「季度调休未消化」
    原写法把「季度剩余 < 30 天」当**触发条件**，但演示数据窗口末日 2026-10-31 ⇒
    季度剩余 **61 天** ⇒ **E004 陈敏永远不触发**（用例直接塌）。改为：
    **触发 = 已产生调休额度且已调休 0；等级 = 季度剩余 < 30 天 ⇒ high，否则 medium**
    （阈值仍来自制度；`--as-of 2026-12-15` 可演示「临期升级为高」）
  - 入口 `scripts/scan_attendance_compliance.py`：打印规则值出处 + 风险清单 +
    **断言 4 条已埋设演示用例**（不成立即 exit 1 —— 杜绝"扫了个寂寞还报成功"）
  - 实测（真机图谱）：员工 40 / **风险 44 条（high 21 / medium 23）**；
    E002 月加班 **42h** + 连续出勤 **22 天**、E003 弹性越界 **7 次**、E004 调休未消化 **22h**
    **全部命中**（4 条断言 OK）
  - 测试：`tests/test_rules_engine.py` **15 项全绿**（含口径分岔反向验证、
    「缺规则值 ⇒ 跳过而非崩溃」）；全量 **447 项无回归**；
    `export_openapi.py --check` 零漂移；`check_seams.py` ERROR 0 / WARN 0
  - **不建表、不动契约**（契约动在 D3，端点在 C3）
- [x] **C2** 扩展 M4（**只加不改**）—— **已完成（服务层与域化；落库 / 契约随 D3 一起做）**
  `backend/app/services/rules/attribution.py`
  - **新增 `causes`**：`{code, reason, weight, matched, evidence[]}` —— 原因排序 + 证据节点 id
  - **置信度 = Σ命中权重 / Σ全部权重**（**确定性加权，禁止 LLM 生成**）：
    `trip_approved 0.35 / order_closed 0.30 / location_match 0.22 / access_contrast 0.13`
    ⇒ 三项主证据命中 = **0.87**（对齐 proposal §5.4 的示例值）、四项全命中 = **1.00**、
    **零证据 = 0.00 且结论「不成立」**（不给"60% 凑合分"）
  - 反向守卫（单测钉死）：**未审批的出差单 / 未闭环的工单 / 与出差地不符的定位
    一律不算证据**，门禁对比（当日无门禁 + 前一日有门禁）只作**旁证**（制度四：门禁不作唯一判据）
  - **`suspicion_type` 域化**：`suspicion_types_for_domain()` —— 金融两个类型
    **保留不删**，考勤域给 `missing_check_in`；**未知域抛错**（不静默回落金融域，
    否则"考勤疑点"会被当成"关联交易疑点"解释）
  - **结论里的制度话术可溯源**：「自动补卡」**不硬编码**，走 `search_policy_sentences()`
    从制度文本取原句与出处 —— 实测命中两条，且正好含 **2025 手工补卡 → 2026 自动补卡**
    的版本更替 ⇒ 可直接喂 ADR-0005 时效演示
  - CLI `scripts/explain_attendance_anomaly.py`：列异常日 → 逐条证据（命中 / 权重 / 证据节点）
    → 置信度 → 结论 → 制度出处；**断言 E001 用例**
  - 实测（真机图谱）：E001 张伟 2026-10-16 缺卡 ⇒ 出差审批 ✓（武汉 10-16~10-18）+ 工单闭环 ✓
    （`SO-2026-0912`）+ 定位一致 ✓（武汉光谷 ×2）+ 门禁对比 ✓ ⇒ **100% / 外勤出勤成立 → 自动补卡**
  - 测试：`tests/test_rules_attribution.py` **9 项全绿**；全量 **456 项无回归**；
    `export_openapi.py --check` 零漂移；`check_seams.py` ERROR 0 / WARN 0
  - ~~**边界**：`causes` **尚未落库**、也未进契约~~ —— **已于 D3 同步时闭合（2026-09-28）**：
    已加 `affiliation_suspicions.causes` **JSON 可空列**（迁移脚本
    `scripts/migrate_add_suspicion_causes.py`，**无 Alembic** ⇒ 显式 DDL）、
    `ck_affiliation_suspicions_type` 放宽到三值、契约新增 `AffiliationCauseItem`、
    前端 `SUSPICION_TYPE_META` 增 `missing_check_in`。
    **可空语义**：金融域疑点与历史数据为 `null`（**未归因**），
    **不**用空列表冒充「归过因、零命中」——二者语义相反
- [x] **C3** 合规预警扫描端点 —— **已完成（2026-09-28）**
  `GET /api/v1/attendance/compliance/scan`（同步，**非**异步任务：纯读、不落库、不调 LLM，
  40 员工实测秒级）：
  - 参数 `as_of`（观察日，**临期判据开关**）/ `employee_id` / `rule` / `level`；
    只读 active 版本，无 active ⇒ **409** `KG_VERSION_NOT_ACTIVE`（不静默降级）
  - 响应含 `rule_values[]`（**每个值带制度出处**）+ `unresolved[]` / `skipped_rules[]`
    （无判据即跳过，**不用默认值兜底**）+ `findings[]`（calculation 可逐条念、证据为节点 id）
  - 新增错误码 `COMPLIANCE_NO_FACTS`（409）：版本内没有考勤事实 ⇒ **不是** 501、
    更不是「200 + 空清单」（后者会被前端读成"全员合规"）
  - 服务层入口 `GraphService.scan_attendance_compliance`（`kg_version` 一律走 PG 真源）
  - **真机实测**：默认观察日 8 条（high 2）；`--as-of 2026-12-15` 时调休升 high
    （季度剩余 16 天 < 30）⇒ 可演示「同一事实随观察日自动升级」
  - 测试 `tests/test_compliance_scan_endpoint.py` **7 项全绿**；全量 **463 项无回归**；
    `export_openapi.py --check` 零漂移；`check_seams.py` ERROR 0 / WARN 0

## 批次 D · 问答与推理路径（后端 B）

- [ ] **D1** M3 响应新增 `reasoning_path`（`proposal.md` §5.5 结构），多跳 Cypher 补全路径返回
- [ ] **D2** 定职责边界：**规则引擎出数值 → LLM 只出措辞**；无溯源即拒答（守 F3）
- [ ] **D3** 契约同步 5 步走（`reasoning_path` / `causes` / 合规端点 / 域化枚举）
  - **已完成 3 项（2026-09-28，随 C3 一次做完）**：合规端点（+3 个 schema）、
    `causes`（`AffiliationCauseItem` + 落库列 + 迁移脚本）、域化枚举
    （`suspicion_type` 增 `missing_check_in`，金融两类保留不动）
  - **未做 1 项**：`reasoning_path` —— 属 **D1**（`reasoning_path` 尚未实现），
    契约**不**先承诺后补实现，待 D1 完成后同步
  - 前端只做了 `npm run gen:api` + `SUSPICION_TYPE_META` 补齐（tsc / eslint 全绿）；
    合规预警**页面**属**批次 E**，不在本次范围

## 批次 E · 前端（前端）

- [ ] **E1** 业务域导航（对齐 `docs/demo.html` 侧栏）；非考勤域标「规划中」
- [ ] **E2** 政策问答子页：**推理路径链可视化** + 判定结论条
- [ ] **E3** 异常归因子页：用例列表 + 原因排序（含置信度条）+ 跨系统证据链
- [ ] **E4** 合规预警子页：风险清单表 + 依据 + 建议动作
- [ ] **E5** 页脚/页头标注「演示语料（仿真）」（R9）

## 批次 F · 彩排与文档（架构师）

- [ ] **F1** 彩排脚本 `demo_rehearsal.py --domain attendance`：全链路一条命令可复现，预期**全绿**
- [ ] **F2** 文档同步：`docs/03-prd.md`（业务域）、`acceptance-traceability-matrix.md`、`sprint-calendar.md`（登记 S9.5）、`dev-doc-status.md`（登记 R9~R13）
- [ ] **F3** 提交与 tag（按 §8.1 判据：tag 的树须包含 notes 声称的全部交付）

---

## 环境备注（2026-09-27 实测）

- [x] **B0-1 · 外网间歇不可达** —— **已解除**：`git push` 首次报 `Failed to connect to github.com:443`
  （DNS 抖动），**重试第二次成功**：`95eea160..85a92b32 main -> main`。
  ⇒ 后续网络操作**先重试再判定失败**。
- [x] **B0-2 · M1 解析走外网 MinerU** —— **定性为已接受的部署约束，不阻塞 B2**：
  文档解析（版面 / 表格 / OCR）与 LLM 抽取**无法本地自足**，依赖第三方是行业现实，
  **非本项目选型缺陷**。与 `docs/deployment-spec.md` 亦**不矛盾** —— 该文档要的是
  「数据不出内网」+「模型可内网、改配置即可」（§3 `PRIVATE_DEPLOY_ENABLED=true`、
  §8「模型可内网」走 ADR-0004 接缝 3，组件表更直接列了「内网 LLM / OCR：客户自备」），
  **从未要求第三方服务封装进镜像**。
  ⇒ **分阶段口径**：DEMO 阶段（本 Sprint）接受外网 MinerU / LLM，对齐 plan §3.4；
    交付阶段（v1.7.0 / S11）由客户内网等价物替换，切换位 = `parser_provider` 抽象
    —— **当前唯一实现 `mineru_cloud` 即正确的当下状态**（登记集合就该是 1，加实现须先
    扩 ADR-0004 §2.1 登记行再改门禁）。
  ⇒ **唯一需向客户明示的点**：MinerU 云是**文件本体出网**（上传至 OSS），比 LLM 文本
    出网更敏感，属**数据合规事项** —— 交付说明 / release notes 必须写明，**不得静默**。
    （`config.py:59`「内网本地解析通路未落地」的注释保留，它描述的是事实，只是不阻塞 DEMO。）

## 遗留问题（2026-09-27 登记，**均未处理**，非当前批次阻塞项）

> 登记目的：这些是动工途中暴露、但不适合当场展开的问题，**避免散落在对话里丢失**。
> 每条给了触发时点建议——**触发前不要顺手做**，L1 尤其：它是跨前后端的契约变更。

- [ ] **L1 · 图谱前端区分度不足（动契约，需先拍板）**
  `category` 是契约级 4 值枚举 ⇒ 8 类事实记录共享 `topic` 一色，13 类只呈现 4 种颜色。
  这是选型 C 的**固有边界**（详见「批次 B · B1-follow」条）。要逐类型分色只能走方案 B：
  同步 `schemas/graph.py:22` → `contracts/openapi.yaml:1276-1281` 与 `:1562-1566` 两处
  enum → `npm run gen:api` → `globals.css:53-58` 加色 → `graph-legend.tsx` 加色板与图例。
  ⇒ **触发时点**：B3 汇合跑通、看到真实 13 类分布后再评估；**动之前必须说明跨前后端代价**。

- [ ] **L2 · 概览节点抽样刷屏**
  `_QUERY_GRAPH_OVERVIEW` 按度数降序取 500 节点，实测 `ATTENDANCE_RECORD` 独占
  **442/500**，员工仅 38 ⇒ 图上几乎全是打卡记录，演示观感差。
  ⇒ 可评估按类型配额抽样；但须保留「保护前端渲染」的初衷——此前无序截断曾导致
  500 节点仅 36 条边、全是孤点噪云（成因见 `graphs.py:354-360` 注释），别改回去。

- [ ] **L3 · 前端图例类型未挂契约同步链**
  `graph-legend.tsx:1` 的 `GraphCategory` 从 `@/types/mock.ts` 导入，而非契约生成的
  `types/api.d.ts` ⇒ 契约改了枚举，前端**不会报错**，属静默失配隐患。
  ⇒ 收口到生成类型、删掉手写重复定义；与 L1 一起处理最经济。

- [x] **L4 · MinerU 文件出网的合规留痕（待办动作，B0-2 的落地项）** —— **已完成（触发条件已到：B2 真调用了 MinerU）**
  留痕落点 **`docs/deployment-spec.md` §8.1「第三方出网事实登记」**（交付说明的直接引用源，
  下一步就该由它进 release notes）：三行表把 M1 **文件本体出网（最高敏）** / M2 / M3
  文本出网分开写，标明**切换位**（`parser_provider` / ADR-0004 接缝 3）与当前状态
  （DEMO 阶段用外网）+ 给客户的三句话（含"替换完成前不得宣称数据不出内网"）。

- [ ] **L5 · 网络抖动应对（纪律，非代码改动）**
  外网间歇不可达（DNS 抖动）：`git push` / 外部 API 调用失败时**先重试再判定失败**，
  不得一次失败就改方案（已实测重试第二次即成功）。

> 以下 2 条是 **B2 / B3 真机过程中暴露并当场修复**的，登记为**已修复**而非待办，
> 免得下沉同一坑的人误以为它们还没处理。

- [x] **L6 · CSV 派生节点的名字被表的 ``name`` 列污染（已修）**
  `DEPARTMENT` / `POSITION` / `WORK_TIME_SYSTEM` 由 `employees.csv` 去重派生，
  而该表自带 `name` 列（员工姓名）⇒ 原 `_canonical_name` 会把**第一个员工的名字**
  当部门 / 岗位 / 工时制的名字（图上出现「张伟」既是员工又是部门）。
  改：取值优先级 `派生节点的键列值 > row["name"] > 类型模板 > node_id`。
  真机复验：员工详情由 `EMPLOYEE:E001` 变回 `张伟`。
- [x] **L7 · 实体详情关系名只读 Neo4j 令牌（已修，§7.5.1 同族错配）**
  建图侧统一写 `:RELATION` 令牌、真实语义在 `properties.relation_type`
  （`kg/builder.py` stage-3），而 `fetch_entity_detail` 只取 `rel.type`
  ⇒ **所有关系名都显示成 `RELATION`**（考勤真机：员工 50 条出边全叫 `RELATION`，
  `HAS_SHIFT` / `GOVERNED_BY` 一个都没露出来）。改：新增 `graphs.py::_relation_name()`
  **语义优先、退化令牌**（详情是自由 `str` 字段，**不走** `_relation_type` 的契约投影，
  否则域关系名会被一律兜底成 `MENTIONS`，是另一种信息失真）。
  补回归守卫 3 例（`tests/test_graph_overview_and_entity.py`）。

- [x] **L8 · ``POLICY_CLAUSE`` 是 span 级实体，不是「条款单元」** —— **已决策（C1 立项时拍板，选项 ①）**
  M2 是**跨度抽取**，模型给的 `POLICY_CLAUSE` 常常是条号（「第十一条」）/ 被引用的法规名
  （「《国务院关于职工工作时间的规定》」）/ 值（「月标准工时 174 小时」）——
  都是语料里真实存在的文本、可复核，**不是假数据**，但**粒度不是「一条可执行的条款」**
  （不像 AIOps 那种「第五条 综合计算工时制以月为计算周期…」整条）。
  影响面主要在 **C1 规则引擎**：要从条款里读数值（如 174 小时 / 36 小时 / 40 小时）
  得容忍这种粒度；现有 84 个条款节点里确实**含**这些数值节点。
  ⇒ **触发时点：C1 立项时**。**已选 ①**（接受 span 粒度 + 补一个完整句子来源）：
  C1 实现为「图谱 span 优先 + M1 产物 `full.md` 兜底」两级解析（详见 C1 条）。
  **未做**结构化条款切分（选项 ②）——它是新增能力，且当前需求（读 7 个数值）用 ① 已满足。
  ⇒ **L8 的教训要记住**：span 级抽取**不能**被当作「条款全文」用，
  谁要按条款做语义判断（M3 问答同理）都得先问一句"这条 span 够不够"。

> 以下 2 条是 **C1 真机扫描后暴露的「语料 ↔ 规则」对齐缺口**，都属 **A1 语料侧**取舍，
> **引擎侧已按制度正确实现**，改不改语料须用户拍板（我不越过角色隔离去改 `demo/`）。

- [x] **L10 · 「周工时超限」零命中** —— **已决策（选 ① 埋设）并闭合（2026-09-28，用户授权改 `demo/`）**
  规则 = 标准工时制周实际工时 **> 40h**。语料给标准制员工排的是「工作日 8h × 5 天」，
  正好 40h（且 12h 连班只给生产部 ⇒ 标准制永远 8h）⇒ **严格大于永不成立**，实测 0 条。
  ⇒ **已埋设第 5 个演示用例 E005 刘洋**（研发部 / 标准工时制）：第 42 周（10-12 周一 ~
  10-17 周六）连上 **6 天 × 8h = 48h > 40h**。生成器自检 + 扫描 CLI 均断言该用例成立。

- [x] **L11 · 「月加班超限」命中面过宽（21/22 全中）** —— **已决策（选 ① 改语料）并闭合**
  原排班「周一至周六全排 + 周日 35%」⇒ 月排班 ≈216h，21/22 名综合制员工全员超限。
  ⇒ **背景综合制员工改「做五休二」**（周三 + 周日轮休、月排班 ≈22 天 / ≈176h），
  12h 连班每人每月**上限 3 天**（防随机叠加重新顶过 210h 触发线）。
  改的是**排班强度**而非核算口径（综合制按**月**核算，制度二第七条，跨周排班本就合规）。
  **实测**：背景综合制 21 人月最高 **196h**（触发线 210h），**超限 0 人**；
  全量风险 **44 → 8 条**（high 2 / medium 6），**五条规则全部有命中**。
  生成器新增**背景护栏**自检（防止回归），扫描 CLI 新增第 5 条用例断言。

> **改语料过程中发现并修掉的两个真缺陷（2026-09-28，重要）**：
>
> 1. **入图器 `--purge` 会连带删掉 M2 抽取的 span 实体**：同一 `kg_version` 里住着 CSV 派生
>    节点（id 形如 `EMPLOYEE:E001`）与 `ent_*` span（规则值的图谱侧来源），而 purge 按
>    `:Entity{kg_version}` 全删 ⇒ 一次就清空 210 个 span，重建要重烧 MinerU + LLM。
>    已新增 **`--purge-csv`**（只清 CSV 派生前缀），并把**失败补偿**一并改为只撤销本次写入
>    （原先失败回滚也会全清 span，本次实际就踩到了、已重跑 `ingest_attendance_policies.py
>    --force` 恢复）。
> 2. **写入自检口径错**：自检按整个 `kg_version` 计数，把 span 算进实际数 ⇒
>    两来源共存时**恒报**「写入自检失败」。已改为按**本次提交的 id** 计数。
>    （副作用：`ingest_attendance_policies.py` 头部原登记的「重跑 CSV 须全 purge 再重跑本脚本」
>    这一别扭约束**就此解除**。）
- [ ] **L9 · 抽取结果非确定性（LLM 固有，非缺陷）**
  同一份文档前后两次抽取结果不同（实测 `POLICY_CLAUSE` 63 → **84** 条、关系数亦变）。
  ⇒ 演示语料一旦固化就**尽量不再重跑**；若重跑必须先 CSV `--purge` 再跑制度脚本、
  最后重算 `mark_ready`（脚本已按此顺序设计）。**不要**为了对齐旧数字去改阈值兜底。

## 门禁

| 闸门 | 判据 |
|---|---|
| **CP-A1** | 仿真语料齐备且四个演示用例数据成立（批次 A 收尾） |
| **CP-A2** | 两链路数据入图成功且汇合可查（批次 B 收尾） |
| **CP-A3** | 规则引擎数值**可手工核算验证**（批次 C 收尾）——**不可核查即判定失败** |
| **CP-A4** | `demo_rehearsal.py --domain attendance` **全绿**（交付前） |

> **CP-A2 实测结论（2026-09-27）：达成** —— 判据两侧都有证据：**入图成功**
> （Entity 3164 / Relation 4066，关系按 id 逐个核对 114/114 无静默丢失）+ **汇合可查**
> （B3 路径 288 条 / 40 名员工 / 3 个工时制 / 15 条条款，且经真机 HTTP 复核）。
> 逐条依据见上方批次 B 的 B2 / B3 两项。**两处保留短板已登记为 L8 / L9**，不影响该闸门。

## 不做（再次划界）

其他 6 个业务域 / M6 冷启动 GUI / 校正界面 / 增量重算 / 真实客户数据 / License / RLS / RBAC / 部署 / SSO。
