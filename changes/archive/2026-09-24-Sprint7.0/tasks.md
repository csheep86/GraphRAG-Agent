# Tasks: Sprint 7.0 还债批次 —— 抽取链路接真实 LLM

> **状态**：**已批准（2026-09-23 拍板）；本批次在 Sprint 7 专属新会话执行**。
> **纪律**：勾选 ≠ 通过——每项须在 `integration-log.md` 留真机证据（命令 + 输出摘要）。禁止：静默回落 mock、把 LLM 失败伪装成空抽取、未核实就宣称"偿还了 S6-3"。
> **⚠ 花钱纪律**：本批次会**真实调用 LLM 扣费**。DeepSeek 账户余额 **¥8.37**（2026-09-23 实测）——**够完成本批次，不够全量重建演示图谱**。真机验证必须按 §4「预算护栏」**跑定向切片**，禁止全量重抽整份年报。

## 0. 事前核实（**未完成不得往后走**）

- [x] ~~**裁决**：是否插入本批次~~ → **已批准**（2026-09-23 拍板），无需再裁决；plan §6.2 的登记见 §5 收尾
- [x] **核对 D6 验证素材**：已读 `demo-docs-checklist.md` §8 预检结论（**未重跑**）；本机 `docs/annualreport/` 8 个文件在位（公路 / 蛇口 / 轮船 / 银行，各正文 + 摘要）
- [x] 复现事实①：`langextract.py` 262 / 267–276 行确认——`from_settings()` 不传 `chunk_extractor` / LLM client → 走 `_default_extract_chunk`
- [x] 复现事实②：实测 `_RE_ORG.findall('本报告汇总了集团') = ['本报告汇总了集团']`；第二个样例「智能制造与数字服务两大板块合计贡献集团」同样命中 → **是正则产物，不是 LLM**
- [x] 复现事实③：全仓 11 处命中**全在** md / docstring / 注释里，**无 `def _evaluate_client_call_llm`**
- [x] 确认 `LLM_API_KEY` 可用：`len=35`，`llm_base_url=https://api.deepseek.com`、`llm_model=deepseek-chat`（**不落密钥**）；连通性由 §4 真机验证给出
- [x] `docker ps` 确认 Neo4j：**空**；`docker ps -a` = `neo4j Exited (137)`。本批次**不重跑演示图谱**，故未启动容器（登记见 integration-log §5.5）
- [x] **准备 D6 验证素材**：用本机现有年报（招商公路）「第二节 公司简介和主要财务指标」定向切片 12254 字（**不下载新素材**）
- [x] **确认 LLM 预算**：余额 ¥8.37 足够；**实际扣费 ¥0.4062**（12 chunk，见 integration-log §4.3）。⚠ 实测单份全量重抽约 ¥5–7，**高于本条原估 ¥0.1–0.5 与 tasks §4 的 ¥1.5–3**

## 1. 契约更新

- [x] **本批次无契约变更**（内部链路替换，端点 / 响应体不变）
- [x] 收尾 `uv run python scripts/export_openapi.py --check` **无 diff** → ✅ `[OK] 契约与模型一致`

## 2. 后端实现（backend/）

### 2.1 显式开关（替代"隐式默认 mockable"）

- [x] `app/core/config.py` 新增 `extraction_engine: str = "llm"`（档位 `llm` / `mock`）——默认 `llm`（演示 / 生产要真数据）；CI 场景由测试注入覆盖（`conftest.py` 置 `EXTRACTION_ENGINE=mock`，与既有 `MINERU_TOKEN=""` 同纪律）
- [x] **未知档位显式报错**：`LangextractError(f"未知 extraction_engine={engine!r}（当前仅支持 'llm' / 'mock'）")`，不静默回退
- [x] `check_seams.py` 判据 2 → ✅ **ERROR 0 / WARN 6 / OK 7**；输出「Settings 全部 45 个字段均有消费者代码行」（消费点 = `LangextractClient.from_settings()` 第 1 个读取处）。**未改门禁脚本**

### 2.2 真实 LLM 抽取实现

- [x] 新增 `_build_llm_chunk_extractor()` + `_default_llm_invoke()`（替换 `_evaluate_client_call_llm` 占位语义），**走 `app/services/providers/llm.py` 的 `build_chat_model()`**，不新建第二套 LLM 客户端（接缝 3）
- [x] Prompt 通过 `app.prompts.prompt_loader` 加载 `kg_extraction_v1` 并渲染 `{{text}}` / `{{language}}`，**无硬编码模板文本**（单测断言渲染结果以 `# KG Extraction Prompt v1` 开头）
- [x] 输入超长按 `settings.extraction_max_chars_per_chunk` **先切再抽**，两档**共用** `_split_into_chunks` / `_clamp_entities` / `_clamp_relations`（`_build_llm_chunk_extractor` 只替换"文本 → 实体"这一步）
- [x] 严格按输出 Schema 解析：
  - [x] `entity_type` / `relation_type` 未命中枚举 → 降级 `RELATED`（原始名由 `langextract_*_type_downgraded` 日志留痕，沿用 v1 第 47–48 行约束）
  - [x] `confidence < 0.5` 丢弃（v1 第 50 行约束）；缺失 / 非数值同样丢弃，**不猜值**
  - [x] `char_start` / `char_end` 合法则**原样透传**（仅加回块起点）；缺失 / 越界则用 `mention` 回查，回查不到丢弃。**⚠ 实测模型偏移大多不指向 mention（top20 里 14/20 `span_ok=False`）→ `S6-1` 保持原登记（→S10），不硬凑**
  - [x] 合法但为空的 `{"entities": [], "relations": []}` → 正常空结果（v1 第 59 行拒答兜底，**不是**错误）；空响应 / 非法 JSON / 顶层非对象 → `LangextractError`
- [x] 依赖注入友好：`llm_invoker` 与 `chunk_extractor` 均可注入，**单测不真连网络**（18 例全注入假实现）

### 2.3 失败语义（纪律关键）

- [x] LLM 调用失败 / 超时 / 返回非法 JSON → 抛 `LangextractError`，由外层 `document.extract` tenacity 统一重试（**内层无第二层重试**）
- [x] **严禁**「LLM 挂了就静默回落 mock」——单测 `test_llm_engine_call_failure_raises_not_mock_fallback` 固化
- [x] 日志不落 API key / prompt 原文：只记 `chunk_index` / `chunk_offset` / 实体数 / 关系数 / `elapsed_ms` / token 用量 + `trace_id`（`logger.contextualize` 贯穿）；异常只取 `str(exc)[:200]`
- [x] 附：`_do_extract` 改为 `await asyncio.to_thread(...)`——`llm` 档同步阻塞（实测 113.8s / 12 chunk），不能占住 uvicorn 事件循环

### 2.4 单元测试

- [x] 注入假 LLM：正常 JSON → 正确解析并产出 `ExtractedEntity` / `ExtractedRelation`（含 id 重生成、跨 chunk 绝对偏移）
- [x] 注入假 LLM：返回非法 JSON → `LangextractError`（另覆盖空响应 / 代码围栏 / 调用抛异常）
- [x] 未知类型 → 降级 `RELATED`；`confidence < 0.5` → 被丢弃
- [x] 未知 `extraction_engine` 档位 → 显式报错，**断言错误消息含档位名**（`match="bogus_engine"`）；另测 `from_settings()` 真的读 `settings.extraction_engine`
- [x] mock 档位行为与现有完全一致（防回归）：`pytest -q` **315 passed**（基线 297，新增 18），既有用例未红

## 3. 前端实现（frontend/）

- [x] **无改动**（本批次未触 `frontend/`；契约零漂移已由 `export_openapi.py --check` 证明，前端类型无需 `gen:api`）

## 4. 验证（**真机，必须有对照组**）

> **预算护栏（2026-09-23 登记，先读再做）**
> DeepSeek 账户余额 **¥8.37**。按 deepseek-chat 现价（input ¥2/百万 tokens、output ¥8/百万 tokens）**粗估**：一份 250 页年报约 150–200 chunks，每 chunk 约 2K input + 1K output → **全量抽一份 ≈ ¥1.5–3**；跑 3 份 + 调试迭代 2–3 轮 = **¥10–25，超预算**。因此本批次定死以下三条：
> 1. **§4 真机验证只跑定向切片**：取年报「第二节 公司简介和主要财务指标」或前 5–10 页（10–20 个 chunk），单次量级 **¥0.1 以内**；
> 2. **禁止在本批次全量重抽整份年报**——那属于 Sprint 7.1 批次 A（重建演示图谱），动工前须先确认预算充足；招商银行那份 30MB / 数百页的尤其不要碰；
> 3. **D6②「是否存在交叉」不需要靠 LLM 全量抽取证明**：人工预检已确认零交叉（`demo-docs-checklist.md` §8），照抄证据即可，别烧钱重复确认。

- [x] `uv run pytest -q` **315 passed**（≥297，只增不减）
- [x] `uv run ruff check .`（All checks passed）/ `uv run ruff format --check .`（96 files already formatted）
- [x] **真机对照**（`changes/Sprint7.0/verify_slice.py`，同一份 12254 字切片 / 同一 `from_settings()` 入口 / 12 chunk）：mock = 120 实体 / 3 类 / 0.0s / ¥0；llm = 421 实体 / 8 类 / 113.8s / 12 次调用 / `prompt 31216` + `completion 42972` tokens / **¥0.4062**。明细与实体样例见 `integration-log.md` §4.3
- [x] **D6 可行性结论（两条）**：
  - [x] **① 能抽出可用的法人 / 地址**（probe：`杨旭东` / `天津自贸试验区` / `北京市朝阳区北土城东路` 三项 llm 档全 True，mock 档全 False）。**但 v1 枚举无 `LEGAL_PERSON` / `ADDRESS`**（法人只能落 `PERSON`、地址只能落 `VENUE`、关系落 `RELATED`）→ **批次 A 的 `kg_extraction_v2` 扩类型是必需项，不是可选项**
  - [x] **② 零交叉**（直接引用 `demo-docs-checklist.md` §8 的人类提取证据，未花费用 LLM 复验）：法人三人各异、地址三地各异、控股股东各异 → 根因是年报天然只披露一家公司。**误报陷阱已证实**：`东方广场`（会计师事务所地址，三份年报共有）在 llm 档被抽出 → 用年报只会产出「共享中介机构地址」伪交叉。建议改**关联交易公告 / 募集说明书**，素材由用户人工获取
- [x] 结论已同步到 `changes/Sprint7.1/proposal.md` 决策点 **D6**（含"拍板①被证伪、须换文档形态"的标注）
- [x] `trace_id` 贯穿：`logger.contextualize` 把 `trace_id` / `document_id` / `engine` / `chunk_index` 带到 LLM 调用段；单测 `test_llm_call_log_carries_trace_id` 断言 `langextract_llm_call` 日志的 `trace_id` 一致
- [x] `uv run python scripts/check_seams.py` **ERROR 0 / WARN 6 / OK 7**：新配置项有消费者、未引入登记外实现类

## 5. 收尾

- [x] 补 `changes/Sprint7.0/integration-log.md`（T0 基线 / 三条事实复现 / 实现 / 门禁 / 定向切片 / 真机对照 / D6 两结论 / 关键发现 / 未触碰项）
- [x] **口径订正**：
  - [x] `docs/release-notes/v1.1.0.md` §6.1（E1/E2 根因 + unresolved）加"已由 Sprint 7.0 偿还"订正块；§6.3 承接行由"注入 provider 后启用"改为 ✅ 已偿还（Sprint 7.0）
  - [x] `docs/release-notes/v1.2.0.md` §6.1（实体质量归因）→ 订正为「`_RE_ORG` 贪婪匹配（非 LLM 质量问题）」+ 已根治 + 残余归 S9 / S10
  - [x] `backend/CODEBUDDY.md` §4 `S6-3` → 🟡 **部分偿还**（整句成实体已根治；数值独立成节点 / 同实体重复仍归 S9）；`S6-4` → ✅ **已偿还**
  - [x] `char_offset`：**不可用**（实测模型偏移 top20 里 14/20 不指向 mention）→ `S6-1` **保持原登记（→S10）**，并在 integration-log §5.1 给出建议，**未硬凑**
- [x] **演示数据重跑处置**：本批次**未重跑**（预算 + 属批次 A）；已在 `integration-log.md` §5.3 显式登记「当前演示数据仍为正则产物」并给出重抽 + ADR-0002 重建 active 版本的 5 步步骤
- [x] 更新 `backend/.env.example`（`EXTRACTION_ENGINE=llm` + 档位语义注释）
- [x] **范围变更留痕**：`docs/v1.1.0-demo-mvp-plan.md` §6.2 批次表后新增"范围变更登记"块（插批次 + 估时 0.5–1 天 + 理由索引本文）
- [x] **未** bump `app_version`（仍 1.2.0 默认 / `.env` 为 1.1.0 —— 后者已登记为发现，交 S7 收尾统一处理）
