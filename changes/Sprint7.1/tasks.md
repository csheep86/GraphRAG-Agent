# Tasks: Sprint 7.1 批次 A —— M4 数据与规则型疑点算法

> **状态**：**决策已拍板（2026-09-23）；代码未动工**——按既定分工，S7 各批次在 **Sprint 7 专属新会话**开工，本会话只做规划登记。
> **拍板结论**（详见 `proposal.md` 决策点表，开工前须全文读一遍）：
> - **前置**：先完成 `changes/Sprint7.0`（抽取接真实 LLM），且它的真机结论必须是「能抽出可用的法人 / 地址」；
> - **D1 建模**：**新建 `:Subject`**，不复用 `:Entity`；**不建两者的桥接关系**；图谱短期出现「`:Entity` + `:Subject` 两层并存」这一事实**必须在 release notes 显式登记**，统一交给 S9 批次 D 实体消解（plan 第 582 行）；
> - **D5**：本批次一次建齐 `:Subject` + `:Address` + `:LegalPerson`（算法闭环的最小三节点）；`Invoice` / `Voucher` / `Contract` / `Phone` 仍归 Sprint 9 批次 B（plan 第 580 行）；
> - **D6**：演示数据集用 **2–3 份互为关联的真实公司年报**（母子公司 / 同集团），**不依赖 CSV**（绕开 R14 的 S9 schema 冻结）；
> - **D2**：`risk.detect` **挂 `EXECUTOR_REGISTRY`**（上传链路自动跑，接缝 4「阶段可启停」语义完整）；
> - **D7**：PG 三表（`affiliation_tasks` / `affiliation_suspicions` / `unaligned_subjects`）归批次 B（`Sprint7.2`），本批次不建表。
>
> **纪律**：勾选 ≠ 通过——每项须在 `integration-log.md` 留下真机证据（命令 + 输出），收尾时逐项对账。
> **与 plan 的分工**：plan §6.2 / §6.3 是 Sprint 级范围与验收；本文件是批次级拆解与勾选。

## 0. 事前核实（**未完成不得往后走**）

- [x] **核对已拍板结论**（`proposal.md` 决策点表全文读一遍）：D1 建模 / D2 触发 / D5 节点范围 / D6 演示数据 / D7 表归属均已定，**不需再裁决** → `integration-log.md` §2
- [x] **口径登记检查**：D1「新建 `:Subject`」与 plan §6.2 第 274 行一致，**无偏离**；「`:Entity` + `:Subject` 两层并存」须落 release notes 一事**本批次尚未有 v1.3.0 notes 可落**（bump 属 S7 四批次全完后的收尾动作）→ 已登记为缺口 **S7.1-7**（`backend/CODEBUDDY.md` §4），待 S7 收尾写 notes 时必含，**不构成静默**
- [x] **确认 `Sprint7.0` 已完成**且真机结论可用 → `integration-log.md` §2（`Sprint7.0/integration-log.md` §4.4 / §7 为据；本批次重抽沿用其结论）
- [x] 无需处置：本批次重抽已确认**能抽出**可用的法人 / 地址（`integration-log.md` §7.1–7.2，法人 25 节点 / 地址 45 节点落图）
- [x] **D6 演示数据集到位**（按第 22–27 行的修正口径）→ `integration-log.md` §3；**全量 6 片 = 3 份原始 PDF 切片**（蛇口 / 公路募集说明书 + 招商轮船年报），素材由**人工**取得，未由 AI 代下载；**不依赖 CSV**
- [ ] **⚠️ 上一条已被 7.0 真机结论推翻并再次修正（2026-09-23，`changes/Sprint7.0/integration-log.md` §4.4 + **§7**），开工前必读**：
  - **年报不可用**：D6② 对 4 份年报为**零交叉**（法人三人各异、地址三地各异，年报天然只披露一家公司）；
  - **改用募集说明书，已真机验证通过（§7）**：用户已人工取得 **招商蛇口 + 招商公路 2024 年公司债募集说明书**（`docs/annualreport/`）。定向切片真机结果——两家均抽出 `ORG 招商局集团有限公司` + `PERSON 缪建民`（同一控股股东、同一法定代表人）→ **共享法人交叉成立**；但**共享地址不成立**（公路全文未披露集团注册地址，0 处命中「建国路」）；
  - **素材已齐，疑点 ≥3 条可满足（无需调阈值）**：第三份 = **招商轮船 2025 年报 p90–91「控股股东及实际控制人情况」**（零成本文本核对已确认：控股股东招商局轮船 / 实控人招商局集团，法定代表人**同为缪建民**；且招商局集团成立日期 1986-10-14 与蛇口募集说明书一致 → **同名消歧有据**）。三家两两组合 → 蛇口↔公路、蛇口↔轮船、公路↔轮船 **共 3 条**「共享法人」疑点；
  - **重要**：年报的「公司简介」部分零交叉，但**控股股东章节含交叉**——若沿用年报作素材，切片 / 抽取范围**必须限定到该章节**，否则仍落回零交叉；
  - 素材由**人工**获取（巨潮公开列表 API 已收紧），**不得由 AI 代下载**；第三份未到位前开工 §2.3 需先确认疑点条数能否达标，**严禁调阈值凑数**（G5）
- [x] **误报陷阱核查**：产出的 9 条「共享地址」**未命中**「东长安街 1 号东方广场」那类中介地址；但打到了**另一类弱信号**——共享值是粗粒度地名（利比里亚 / BVI / 香港特别行政区 / 上海，来自年报「主要经营地 / 注册地」栏），**不是门牌级地址**。已如实登记为质量局限并给出根因（抽取不拆粒度 + 本批次不做地址归一化 → S9 批次 D），见 `integration-log.md` §7.3
- [x] `docker ps` 确认 Neo4j 容器在跑（`neo4j  Up`；`health_check() = True`，`integration-log.md` §1）

## 1. 契约更新

- [x] **本批次无契约变更**（算法为内部能力；对外端点属批次 B）
- [x] 收尾校验 `uv run python scripts/export_openapi.py --check` **无 diff** → `[OK] … 与模块一致`

## 2. 后端实现（backend/）

### 2.1 抽取侧：扩实体 / 关系类型（**新增 Prompt 版本 v2**）

> **纠正**：初稿写「用 `entity_relation_extract_v1` 参数占位、不新增版本」有误——生产链路硬绑 `load_prompt("kg_extraction", …)`，而 `kg_extraction_v1` 的类型枚举是写死的。正确做法是**新增 v2**。

- [x] 新增 `prompts/kg_extraction_v2.md`（v1 **保留不动**）：枚举参数化为 `{{entity_types}}` / `{{relation_types}}`，其余沿用 v1 → `integration-log.md` §4
- [x] `EXTRACTION_PROMPT_VERSION` 切到 `kg_extraction_v2`（`.env` + `.env.example`，默认随 `app_version` 走 coder MODEL_LIST），注入 `LEGAL_PERSON` / `ADDRESS` 与 `LEGAL_REP` / `REGISTERED_AT` → `backend/app/core/config.py`
- [x] 扩 `langextract.py` 的 `ENTITY_TYPES` 与 relation 枚举；未知类型降级 `RELATED` 兜底保留（单测 `test_extraction_llm_engine.py` 守着）
- [x] **文档三处已同步**：`dev-doc-status.md` §5（2026-09-23 追加段）＋ 矩阵 **H9** 行 ＋ `.env.example`
- [x] 单测：新类型产出 / 原 6 类不回归 / `test_v1_template_is_untouched` 守住 v1 未被改
- [x] **真机跑数**：6 片全抽，抽样结果已贴 `integration-log.md` §7.1（**含"5 片触 2000 上限被裁剪"的不粉饰说明**）
- [ ] **`char_offset` 口径待裁决（7.0 真机发现）**：本批次**未裁决**（属用户侧口径决策，非本批次能自行拍板）。**缓解措施**：§2.3 的 `evidence` 不依赖实体级 `char_offset`——证据走「主体层节点 → `source_entity_ids` → `:Entity` → `(:Chunk)-[:MENTIONS]->` → 原文片段 + 区间」，定位用的 chunk 区间（pg / char_start / char_end），**不是 LLM 自报的实体偏移**，故此项未决不影响本批次证据可点击性。建议 S8 批次 A 一并裁决

### 2.2 图写入：M4 增量节点与关系（**D1 / D5 已定：新建 `:Subject`，不与 `:Entity` 桥接**）

- [x] `builder.py` 增写**三种**节点，属性逐字按 spec §4.2（`:Subject` 第 64 行 / `:Address` 第 65 行 / `:LegalPerson` 第 66 行；`id_hash` 本批次为 `None`——**没有信用代码就 null，严禁兜底造哈希**）→ `integration-log.md` §5
- [x] 增写两条关系（spec §4.3 第 76–77 行端点）；**修**：边 id 由「抽取侧 relation id」改为**按端点生成**（真机发现 F：并行边 → 疑点重复出条）→ `integration-log.md` §7.4
- [x] **不与 `:Entity` 桥接**（无 `(:Entity)-[...]->(:Subject)` 边；`:Entity` ↔ `:Subject` 的联系只以 `source_entity_ids` **字符串列表**形式留在主体层节点上，用于证据回原文，**不建图边**）→ 两层统一仍交 S9 批次 D
- [ ] **release notes v1.3.0 已知限制**（两层并存）：⏳ v1.3.0 notes 属 S7 四批次全完后的收尾动作（§5 第 5 条明令此处不 bump）→ 已登记为缺口 **S7.1-7**（`backend/CODEBUDDY.md` §4），收尾写 notes 时必含
- [x] 新节点带 `kg_version`（与 M2 共用 active 版本）+ 继承 `acl_scope`（**只落属性、查询不过滤**）→ 单测 `test_kg_builder_affiliation.py::test_rows_carry_kg_version_and_acl_scope`
- [x] 数值 / 位置属性写侧归一化：M4 节点数值属性本批次**全为 None**（无 `tax_id` / `region_code` / `id_hash` 可写），位置属性不适用；新增列表属性 `source_entity_ids` 已用 `valueType()` **现场抽检通过**（`LIST<STRING NOT NULL>`，见 §7.2）
- [x] 单测 + **真机 Neo4j 计数核验** → `integration-log.md` §7.2；跨 kg_version 隔离另证于 §7.5（旧版本 `v-3e381d36` 无 `:Subject`，`detect` 返回 0 条、不串数据）

### 2.3 规则算法（只做同法人 / 同地址两类）

- [x] Cypher 两跳「共享法人跨公司」照 spec §5.4 第 159 行；两点偏离写在注释里：`s1 <> s2` → **`s1.id < s2.id`**（压掉 (A,B)/(B,A) 对称重复）+ 追加 `org_id` 租户过滤（ADR-0003；`kg_version` ≠ 租户边界）
- [x] Cypher 两跳「共享地址」照 §5.4 第 154 行（同样两处偏离）
- [x] 结构对齐 M4 §3 验收 3：`Suspicion{type, severity, entities[], entity_names, evidence[]}`，`type ∈ {shared_legal_rep, shared_address}`
- [x] `evidence` **复用 S6 `:Chunk`**（`(c)-[:MENTIONS]->(e)` 反查 `chunk_id` + `doc_id` / `page` / `char_start` / `char_end` / 原文）；链路 = 主体层节点 → `source_entity_ids` → `:Entity` → `(:Chunk)-[:MENTIONS]->`
- [x] **演示数据集产出 10 条疑点**（>3），每条含涉及公司 / 类型 / 可点击证据，清单已贴 `integration-log.md` §7.3
- [x] **D6 前置卡口**：6 片文档跨文档交叉**先在本地零成本核对再动手**（`changes/Sprint7.1/cross_check.py`），结论：前 4 片为**零交叉**（所有共享节点都只挂 1 个主体），6 片齐全后才有交叉——也就是说这份语料**天然只有 1 组共享法人 + 5 组共享地址**，刚好构成疑点，事先核过才没去做「为什么不够」的补救动作（§7.3）；**未调任何阈值**（严重度固定 `medium`、无相似度 / 次数门限）→ 疑点条数不是凑出来的

### 2.4 `risk.detect` 挂管线（接缝 4）

- [x] 先读再写：读完 `document_parse_executor` / `document_extract_executor` / `kg_build_executor` 后确认——**仓库里根本没有"下一阶段投递"的写法**（`integration-log.md` §6.3：上传只提交 `first_pipeline_stage()`，`TaskManager.submit()` 绑请求级 `BackgroundTasks`）。据此实现 `risk_detect_executor` 并登记 `EXECUTOR_REGISTRY`；**未臆造**投递机制，缺口登记为 **S7.1-5**
- [x] `settings.pipeline_stages` 删掉 `risk.detect` 即停用 → 单测 `test_risk_detect_executor.py::test_disabled_stage_drops_out_of_pipeline`（+ `test_seams_a2.py` 同步更新为新登记集合）
- [x] **"自动跑 M4"这条前提在本仓库不成立**（见第 1 条），故不会自动误报；另**显式**验证了"就算显式跑也不误报"：旧演示文档（4 KB dummy，kg_version `v-3e381d36`，图内无 M4 节点）→ `detect` 产出 **0 条**、不抛错、不改状态机（`integration-log.md` §7.5）。**演示数据未被污染**：本批次跑数全程走同一份人工素材 + 同一 DB/Neo4j，未用本地浏览器会话写数据

## 3. 前端实现（frontend/）

- [x] **本批次无前端改动**（未触碰 `frontend/` 任何文件；`git status` 可核）
- [ ] 提醒（留给批次 C）：新接口上线时必须同步登记 `CONTRACT_COVERED_PATTERNS`——S6 批次 B 曾漏登记导致关 Mock 下仍走 Mock

## 4. 验证

- [x] `uv run pytest -q` → **352 passed**；新增测试集中在四处：抽取类型（`test_extraction_sprint71.py`）/ 图写入（`test_kg_builder_affiliation.py`）/ 算法正确性（`test_affiliation_detect.py`）/ 管线登记（`test_risk_detect_executor.py` + `test_seams_a2.py`）
- [x] **真机端到端**：上传 6 片 → 解析 → 抽取 → 建图 → `risk.detect` → **10 条疑点**（>3），Neo4j 计数 + 日志双侧取证（`integration-log.md` §7.2 / §7.3 / §7.4）
- [x] `trace_id` 贯穿（`documents.trace_id = c2f02151-9989-46f3-b1c2-33789ef8b7e4`）：upload → parse → extract → build（build 日志该片 trace_id）→ detect（`suspicions.json` 内 trace_id）**四段同值**（`integration-log.md` §7.3）
- [x] `check_seams.py` → **ERROR 0 / WARN 6 / OK 7**（未触碰接缝 5 / 7 / 8；本批次未引入任何登记外的接缝实现类）

## 5. 收尾

- [x] 补 `integration-log.md`（§1 基线 / §2 事前 / §3–4 抽取 / §5 图写入 / §6 算法＋管线 / §7 真机结果）
- [x] 更新 `backend/CODEBUDDY.md` §4 缺口表：新增 **S7.1-5**（无跨阶段投递）/ **S7.1-6**（疑点无持久化）/ **S7.1-7**（两层并存未落 release notes，待 S7 收尾）
- [x] `.env.example` 已随 §2.1 更新（`EXTRACTION_PROMPT_VERSION` → `kg_extraction_v2`）；**本批次未新增配置项**
- [x] ruff check **All checks passed** / ruff format **101 files already formatted**
- [x] **未 bump `app_version`**（仍为 `1.2.0`）

## 附：本批次的三个"别踩"提醒（来自 S6 真机）

1. **别把基础设施故障伪装成业务结论**：Neo4j 不可达要报 501，不许降级为「无嫌疑 / 拒答」。
2. **别伪造数据**：地址缺失就 `null`/不建边，**严禁兜底生成**；疑点必须是证据驱动。
3. **Prompt 版本只增不改**：本批次确定**新增** `kg_extraction_v2.md`（v1 模板文件**不得被修改**），三步同步缺一不可——新增版本 + 更新 `dev-doc-status.md` §5 + 矩阵 H9 行；`.env.example` 的 `EXTRACTION_PROMPT_VERSION` 一并切换。
