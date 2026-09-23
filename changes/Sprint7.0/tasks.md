# Tasks: Sprint 7.0 还债批次 —— 抽取链路接真实 LLM

> **状态**：**草稿（待裁决后开工）**；本批次为 **计划外插入批次**，见 `proposal.md`「范围变更登记」。
> **纪律**：勾选 ≠ 通过——每项须在 `integration-log.md` 留真机证据（命令 + 输出摘要）。禁止：静默回落 mock、把 LLM 失败伪装成空抽取、未核实就宣称"偿还了 S6-3"。

## 0. 事前核实（**未完成不得往后走**）

- [ ] **裁决**：是否插入本批次（否决则按 `proposal.md`「若你否决本批次」处置，并在 plan §6.2 登记口径）
- [ ] 复现事实①：`from_settings()` 不传 LLM client → 走 `_default_extract_chunk`（读 `langextract.py` 262 / 267–276 行确认未被改动）
- [ ] 复现事实②：拿 S6 真机的坏样例（"本报告汇总了集团"）喂给 `_RE_ORG`，确认它确实能命中（**证明是正则产物，不是 LLM**）
- [ ] 复现事实③：确认 `_evaluate_client_call_llm` 全仓仍无实现
- [ ] 确认 `LLM_API_KEY` 可用（`.env` 已填，长度 35）；**实际连通性留到 §4 真机验证**，此处不臆测
- [ ] `docker ps` 确认 Neo4j（重跑演示数据要用）
- [ ] **准备 D6 验证素材**：挑好 **2–3 份互为关联的真实公司年报**（母子公司 / 同集团）放本机——本批次要用它们回答 S7 的两个前置问题（能否抽出法人 / 地址、文档间是否存在可命中交叉）

## 1. 契约更新

- [ ] **本批次无契约变更**（内部链路替换，端点 / 响应体不变）
- [ ] 收尾 `uv run python scripts/export_openapi.py --check` **无 diff**

## 2. 后端实现（backend/）

### 2.1 显式开关（替代"隐式默认 mockable"）

- [ ] `app/core/config.py` 新增配置项（建议 `extraction_engine: str`，档位 `llm` / `mock`），**默认值待定**（建议 `llm`——演示 / 生产要真数据；CI 场景由测试注入覆盖）
- [ ] **未知档位显式报错**，不静默回退（与 `llm_provider` / `parser_provider` 同策略，plan §4.4 纪律）
- [ ] 确认 `check_seams.py` 判据 2 通过：新配置项**有消费者代码行**（提示：可能需要同步 `check_seams` 的 settings 白名单 / 期望集合，**先查再改，别硬塞**）

### 2.2 真实 LLM 抽取实现

- [ ] 新增单 chunk 抽取函数（替换 `_evaluate_client_call_llm` 占位语义），**走 `app/services/providers/llm.py` 的 `build_chat_model()`**，不新建第二套 LLM 客户端（接缝 3）
- [ ] Prompt 通过 `app.prompts.prompt_loader` 加载 `kg_extraction_v1`，**禁止硬编码模板文本**
- [ ] 输入超长按 `settings.extraction_max_chars_per_chunk` **先切再抽**，与 mockable 路径**共用同一套切分 / 裁剪 / 排序逻辑**（避免两条路行为不一致）
- [ ] 严格按输出 Schema 解析：
  - [ ] `entity_type` / `relation_type` 未命中枚举 → 降级 `RELATED`（原始名留痕，沿用 v1 第 47–48 行约束）
  - [ ] `confidence < 0.5` 丢弃 v1 第 50 行约束）
  - [ ] `char_start` / `char_end` **原样透传**（为 `S6-1` 的可能偿还留证据）
  - [ ] 空 / 不可解析 → `{"entities": [], "relations": []}` 由客户端侧按空处理（v1 第 59 行拒答兜底）
- [ ] 依赖注入友好：LLM client 与 chunk_extractor 均可注入，**单测不真连网络**

### 2.3 失败语义（纪律关键）

- [ ] LLM 调用失败 / 超时 / 返回非法 JSON → 抛 `LangextractError`，由外层 `document.extract` tenacity 统一重试（**内层不加第二层重试**，`langextract.py` 第 14–15 行纪律）
- [ ] **严禁**「LLM 挂了就静默回落 mock」——那会把基础设施故障伪装成业务结论（LC1-9）
- [ ] 日志禁止落：API key、完整 prompt 原文；只记 chunk 序号 / 实体数 / 失败原因摘要 + `trace_id`

### 2.4 单元测试

- [ ] 注入假 LLM client：正常 JSON → 正确解析并产出 `ExtractedEntity` / `ExtractedRelation`
- [ ] 注入假 LLM client：返回非法 JSON → `LangextractError`
- [ ] 未知类型 → 降级 `RELATED`；`confidence < 0.5` → 被丢弃
- [ ] 未知 `extraction_engine` 档位 → 显式报错（**断言错误消息含档位名**，防写"静默回退"糊过去）
- [ ] mock 档位行为与现有完全一致（防回归：现有 297 个用例不许因本批次红）

## 3. 前端实现（frontend/）

- [ ] **无改动**；`npm run typecheck` / `npm run lint` 保持通过

## 4. 验证（**真机，必须有对照组**）

- [ ] `uv run pytest -q` 全绿且**用例数 ≥ 297**（只增不减）
- [ ] `uv run ruff check .` / `uv run ruff format --check .` 通过
- [ ] **真机对照**：同一份文档分别以 `mock` 与 `llm` 跑抽取，把两组结果贴进 `integration-log.md`：实体样例、类型分布、是否出现可用的法人 / 地址类信息、单次耗时与 token 消耗量级
- [ ] **D6 可行性结论（两条，都必须给答案，不许含糊）**：
  - [ ] **① 能否抽出可用的法人 / 地址**（`LEGAL_PERSON` / `ADDRESS`）？抽不出要如实登记——这会直接改变批次 A 的做法
  - [ ] **② 2–3 份演示文档之间是否**真实存在**可被算法命中的交叉**（共同法人 / 共同地址）？零交叉就按 plan §6.4 换演示文档或上报，**绝不允许让批次 A 靠调阈值凑出疑点**
- [ ] 结论同步到 `changes/Sprint7.1/proposal.md` 的决策点 **D6**（作为批次 A 的开工依据）
- [ ] `trace_id` 贯穿：上传 → 抽取（含 LLM 调用段）→ 建图，同一 `trace_id`
- [ ] `uv run python scripts/check_seams.py` **ERROR = 0**：确认新增配置项有消费者、未引入登记外实现类

## 5. 收尾

- [ ] 补 `changes/Sprint7.0/integration-log.md`（前置核实 / 跑数 / 关键发现 / gap / 未触碰项 / 收尾确认）
- [ ] **口径订正（本批次的连带动作，不许漏）**：
  - [ ] `docs/release-notes/v1.1.0.md` §6.1（E1/E2 根因 + "未产出 / unresolved"）与 §6.3 承接行（"注入 provider 后启用"）→ 改为明确承接 Sprint
  - [ ] `docs/release-notes/v1.2.0.md` §6.1（实体质量归因）→ 订正为"抽取未接真实 LLM"
  - [ ] `backend/CODEBUDDY.md` §4 `S6-3`（→ S9）→ 按实际结果更新（已根治 / 部分改善 / 仍需 S9）
  - [ ] 若 `char_offset` 顺带可用：`S6-1`（→ S10）同步更新；**不可用则保持原登记，不硬凑**
- [ ] **演示数据重跑处置**（见 proposal 副作用）：给出"重抽 + 按 ADR-0002 重建 active 版本"的步骤；若本批次不重跑，须在 `integration-log.md` 显式登记"当前演示数据仍为正则产物"——**不得让旧数据冒充新链路成果**
- [ ] 更新 `backend/.env.example`（新配置项 + 注释说明档位语义）
- [ ] **范围变更留痕**：`plan §6.2` 附近加一行登记（插批次 + 估时 0.5–1 天 + 理由索引本文）
- [ ] **不得** bump `app_version`（v1.3.0 是 S7 四批次全完成后的动作）
