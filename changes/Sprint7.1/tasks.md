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

- [ ] **核对已拍板结论**（`proposal.md` 决策点表全文读一遍）：D1 建模 / D2 触发 / D5 节点范围 / D6 演示数据 / D7 表归属均已定，**不需再裁决**
- [ ] **口径登记检查**：D1 选的是「新建 `:Subject`」，与 plan §6.2 第 274 行文字一致，**无偏离**；但「`:Entity` + `:Subject` 两层并存」必须落 release notes（见 §2.2），漏登记即属静默
- [ ] **确认 `Sprint7.0` 已完成**（抽取链路已接真实 LLM）**且**它的真机结论是「能抽出可用的法人 / 地址」：本批次以此为前提。7.0 未完成 / 结论为否 → **停在这里上报**，按 D3 第二选项处置（plan 登记 + release notes 显式声明 mockable 演示），**不得照旧干活装作没问题**
- [ ] 若结论是「仍抽不出可用的法人 / 地址」：按 plan §6.4 **换演示文档**；仍不行则**立即上报**，不在 Sprint 内现场修抽取 / 改阈值凑数
- [ ] **D6 演示数据集到位**：准备 **2–3 份互为关联的真实公司年报**（母子公司 / 同集团），逐份确认含可读的法定代表人（自然人姓名）与注册地址字段；**不依赖 CSV**（绕开 R14 归 S9 的 schema 冻结）
- [ ] **⚠️ 上一条已被 7.0 真机结论推翻（2026-09-23，`changes/Sprint7.0/integration-log.md` §4.4），开工前先读**：D6①「能抽出可用的法人 / 地址」= **能**；D6②「文档间存在真实交叉」= **零交叉**——现有 `docs/annualreport/` 4 份年报法人三人各异、地址三地各异，原因是年报天然只披露一家公司的信息。→ **这 4 份不能用作本批次演示数据**，须改用**关联交易公告 / 募集说明书**（能同时披露多个关联主体的名称 + 法人 + 住所）。素材由**人工**获取（巨潮公开列表 API 已收紧），**不得由 AI 代下载**；素材未到位前**不得开工 §2.3**（D6 卡口必然失败，见 §2.3 第 59 行）
- [ ] **误报陷阱登记**：三份年报都含「北京市东城区东长安街 1 号东方广场东 2 座办公楼 8 层」——那是**会计师事务所 / 财务顾问**的地址，不是公司自身地址。若继续用年报跑数并产出「共享地址」疑点，先判断是否打到了这个**伪交叉**上
- [ ] `docker ps` 确认 Neo4j 容器在跑（**它会 `Exited (255)`**，异常就 `docker start neo4j` 并等 ~25s）

## 1. 契约更新

- [ ] **本批次无契约变更**（算法为内部能力；对外端点属批次 B）
- [ ] 收尾校验 `uv run python scripts/export_openapi.py --check` **无 diff**（有 diff 即为越界改动）

## 2. 后端实现（backend/）

### 2.1 抽取侧：扩实体 / 关系类型（**新增 Prompt 版本 v2**）

> **纠正**：初稿写「用 `entity_relation_extract_v1` 参数占位、不新增版本」有误——生产链路硬绑 `load_prompt("kg_extraction", …)`，而 `kg_extraction_v1` 的类型枚举是写死的。正确做法是**新增 v2**。

- [ ] 新增 `prompts/kg_extraction_v2.md`（基于 v1 复制改写，**v1 保留不动**）：把 `entity_type` / `relation_type` 枚举提取为 `{{entity_types}}` / `{{relation_types}}` 占位符，其余（few-shot / 兜底 / 字段约束）沿用
- [ ] `EXTRACTION_PROMPT_VERSION` 切到 `kg_extraction_v2`（`.env` + `.env.example`），传入包含 `LEGAL_PERSON` / `ADDRESS` 与 `LEGAL_REP` / `REGISTERED_AT` 的枚举参数
- [ ] 同步扩 `langextract.py` 的 `ENTITY_TYPES` 与 relation 枚举；**保留未知类型降级 `RELATED` 的兜底**（v1 第 47–48 行约束不得丢）
- [ ] **同步三处文档**（漏一处即 Prompt 账不平）：`dev-doc-status.md` §5（Prompt 版本账）、矩阵 H9 行、`.env.example`
- [ ] 单测断言：注入后 `ExtractionResult` 能产出新类型；原 6 类不回归；v1 模板文件**未被修改**（防止有人顺手改了 v1）
- [ ] **真机跑数**：抽一份含法人 / 地址的文档，核对 `entities.json` 出现 `LEGAL_PERSON` / `ADDRESS`；**把实际抽样结果贴进 `integration-log.md`**（好 / 坏都记，不粉饰）
- [ ] **`char_offset` 口径待裁决（7.0 真机发现，见 `Sprint7.0/integration-log.md`）**：llm 档实测 top20 中 14/20 的模型返回偏移**不指向** `mention`（LLM 自报偏移不可靠）。现实现以偏移为准、`mention` 仅作回退。若采纳「偏移与 `mention` 不符时**以 `mention` 回查为准**」，改动约 1 行 + 1 例单测——**建议本批次一并做掉**，否则 §2.3 `evidence` 的可点击回查会漂到错误位置

### 2.2 图写入：M4 增量节点与关系（**D1 / D5 已定：新建 `:Subject`，不与 `:Entity` 桥接**）

- [ ] `app/services/kg/builder.py` 增写**三种**节点，属性逐字按 `specs/m4-affiliation-detection.md` §4.2：`:Subject`（`id, name, tax_id, type, kg_version`，第 64 行）/ `:Address`（`id, full_address, region_code, kg_version`，第 65 行）/ `:LegalPerson`（`id, name, id_type, id_hash, kg_version`，第 66 行——**`id_hash` 仅哈希，不存原值**）
- [ ] 增写两条关系，端点按 spec §4.3（第 76–77 行）：`(:Subject)-[:REGISTERED_AT]->(:Address)` / `(:Subject)-[:LEGAL_REP]->(:LegalPerson)`
- [ ] **不复用 `:Entity`，也不新增 `(:Entity)-[...]->(:Subject)` 桥接关系**（D1 结论）：两层的统一交给 **S9 批次 D 实体消解**（plan 第 582 行）；本批次只负责产出 subject 层
- [ ] **把「`:Entity` + `:Subject` 两层并存」写进 release notes v1.3.0 的已知限制**——不登记等于默认它是"完成"，属静默
- [ ] 新节点 **带 `kg_version`**（与 M2 共享同一 active 版本，**不分裂版本**，M4 §3 验收 2 / ADR-0002）；`:Address` / `:LegalPerson` **继承 `acl_scope`**（沿用 S6 `:Chunk` 口径：**只落属性、查询不做穿透过滤** → S11）
- [ ] 沿用 S6 写侧整型归一（`_normalize_chunk_row` 那一套）处理新增节点的数值 / 位置属性，**不重复踩字符串入库的坑**
- [ ] 单测 + **真机 Neo4j 计数核验**（节点 / 关系条数、`valueType()` 类型、跨 kg_version 隔离）

### 2.3 规则算法（只做同法人 / 同地址两类）

- [ ] Cypher 两跳「共享法人跨公司」，**照 spec §5.4 第 159 行原文**：`MATCH (s1:Subject)-[:LEGAL_REP]->(l:LegalPerson)<-[:LEGAL_REP]-(s2:Subject)`（排除自环、限定同一 `kg_version`）
- [ ] Cypher 两跳「共享地址跨公司」，照 §5.4 第 154 行（同样约束）
- [ ] 返回结构对齐 M4 §3 验收 3：`{type, severity, entities[], evidence[]}`，`type ∈ {shared_legal_rep, shared_address}`
- [ ] `evidence` **复用 S6 `:Chunk`**（`(c)-[:MENTIONS]->(e)` 反查到具体 `chunk_id`），保证证据可回原文——这是批次 B「引用覆盖率 100%」的地基
- [ ] **演示数据集产出 ≥3 条疑点**（plan §6.3 第 1 条），每条含涉及公司 / 疑点类型 / 可点击证据；把列表贴进 `integration-log.md`
- [ ] **D6 前置卡口**：演示数据必须是 **2–3 份互为关联的真实公司年报**，且在 7.0 真机阶段已验证「文档间存在可被命中的法人 / 地址交叉」。**零交叉就上报并换数据——严禁调阈值凑够 3 条疑点**（凑出来的疑点 = G5 诚实性违纪）

### 2.4 `risk.detect` 挂管线（接缝 4）

- [ ] 先读 `document_parse_executor` **实际的下一阶段投递写法**再照做（**不臆测**），实现 `risk_detect_executor` 并登记 `EXECUTOR_REGISTRY`
- [ ] 验证 `settings.pipeline_stages` 删掉 `risk.detect` 即停用（接缝 4「阶段可启停」语义完整）
- [ ] 注意：登记后**上传链路会自动跑 M4**，需确认现有文档（无法人 / 地址）不会误报一堆疑点——若会，给出处置（如演示套餐切换或阈值），**不允许本地 Chrome 污染演示数据**

## 3. 前端实现（frontend/）

- [ ] **本批次无前端改动**（`npm run typecheck` / `npm run lint` 保持通过即可；疑点页属批次 C）
- [ ] 提醒（留给批次 C）：新接口上线时必须同步登记 `CONTRACT_COVERED_PATTERNS`——S6 批次 B 曾漏登记导致关 Mock 下仍走 Mock

## 4. 验证

- [ ] `uv run pytest -q` 全绿；新增测试集中在「抽取类型 / 图写入 / 算法正确性 / 管线登记」四处
- [ ] **真机端到端**：上传含法人 + 地址的演示文档 → 自动跑到 `risk.detect` → 产出 ≥3 条疑点（Neo4j 与日志双侧取证）
- [ ] `trace_id` 贯穿验证（H4）：上传 → 抽取 → 建图 → 疑点，四段同一个 `trace_id`
- [ ] `uv run python scripts/check_seams.py`：**ERROR = 0**（本批次不触碰接缝 5 / 7 / 8，它们仍属未到期 WARN；但**须确认没有因本批次引入登记外的实现类**）

## 5. 收尾

- [ ] 补 `changes/Sprint7.1/integration-log.md`（前置核实 / 跑数 / 关键发现 / gap / 未触碰项 / 收尾确认，六段对齐既有格式）
- [ ] 更新 `backend/CODEBUDDY.md` §4 缺口表（本批次新登记的缺口，注明承接 Sprint）
- [ ] 更新 `.env.example`（若新增配置项——**无消费者的配置不得提交**）
- [ ] 通过 ruff check / format（Black 风格由 ruff format 统一）
- [ ] **不得**在此时 bump `app_version`（那是 S7 四个批次全完成后的收尾动作，与 tag v1.3.0 同一动作）

## 附：本批次的三个"别踩"提醒（来自 S6 真机）

1. **别把基础设施故障伪装成业务结论**：Neo4j 不可达要报 501，不许降级为「无嫌疑 / 拒答」。
2. **别伪造数据**：地址缺失就 `null`/不建边，**严禁兜底生成**；疑点必须是证据驱动。
3. **Prompt 版本只增不改**：本批次确定**新增** `kg_extraction_v2.md`（v1 模板文件**不得被修改**），三步同步缺一不可——新增版本 + 更新 `dev-doc-status.md` §5 + 矩阵 H9 行；`.env.example` 的 `EXTRACTION_PROMPT_VERSION` 一并切换。
