# Sprint 7.0 实测记录（前置还债批次：抽取链路接真实 LLM）

> 每个结论都要能复跑，记录"怎么测的"。本文件随批次收尾移入 `changes/archive/<日期>-Sprint7.0/`。
> 门禁口径：接缝门禁 = **默认档 + ERROR = 0**（`--strict` 仅 v1.4.0 完成点）。
> **花钱纪律**：本批次真实扣费 **¥0.4062**（一次定向切片，12 个 chunk），明细见 §4.3；未做任何全量重抽。

---

## 1. T0 环境基线（2026-09-23）

| 项 | 实测 |
|---|---|
| 分支 / 基线 | `main`，`git status` 开工前 clean（用户给定：v1.2.0 已收尾） |
| 基线门禁 | `uv run pytest -q` **297 passed**（4.24s） |
| LLM 配置 | `llm_api_key_len=35`、`llm_base_url=https://api.deepseek.com`、`llm_model=deepseek-chat`（**只打长度，不落密钥**）；连通性留到 §4 真机验证，未提前假设 |
| 抽取配置 | `extraction_provider=langextract`、`extraction_prompt_version=kg_extraction_v1` |
| ⚠ `APP_VERSION` | `.env` 里仍是 **1.1.0**（`config.py` 默认已是 1.2.0）→ `check_seams.py` 读到的当前版本是 1.1.0，`required_from=1.3.0` 的三条因此仍记 WARN。本批次**不 bump**（纪律：v1.3.0 是 S7 四批次全完成后的动作），仅登记 |
| Neo4j | `docker ps` = **空**；`docker ps -a` = `neo4j  Exited (137) 5 minutes ago`。本批次**不重跑演示图谱**（属 Sprint 7.1 批次 A），故未启动容器 |
| 预算 | 用户给定 DeepSeek 余额 **¥8.37**；本批次只跑定向切片（预算护栏见 `tasks.md` §4） |
| 演示素材 | `docs/annualreport/` 8 个文件（公路 / 蛇口 / 轮船 / 银行 4 家各正文 + 摘要，约 47MB，`.gitignore` 已忽略）。预检结论见 `demo-docs-checklist.md` §8，**本批次不重跑预检** |

## 2. 事前核实：三条事实复现（**未完成不得往后走**）

### 事实① `from_settings()` 不传 LLM client → 走正则占位器

改动前 `backend/app/services/extraction/langextract.py`：

- 第 262 行：`self._chunk_extractor = chunk_extractor or _default_extract_chunk`；
- 第 267–276 行 `from_settings()` 只传 `provider / max_* / prompt_version`，**没有** `chunk_extractor`、也没有任何 LLM client 参数 → 生产链路必走 `_default_extract_chunk`；
- `_default_extract_chunk`（181–226 行）正则四类：第 191–196 行 `ORG / PERSON / MONEY / DATE`。

结论：**配了 `LLM_API_KEY` 也不调 LLM**（S6-4 成立）。

### 事实② `_RE_ORG` 能命中 S6 的坏样例（证明"整句成实体"是正则产物）

```
cd backend; uv run python -c "from app.services.extraction.langextract import _default_extract_chunk, _RE_ORG; ..."

RE_ORG hit1: ['本报告汇总了集团']
RE_ORG hit2: ['智能制造与数字服务两大板块合计贡献集团']
entities1: [('ORG', '本报告汇总了集团')]
entities2: [('ORG', '智能制造与数字服务两大板块合计贡献集团')]
```

两条 S6 真机坏样例**都被 `_RE_ORG` 原样命中** → 与模型无关，v1.2.0 §6.1 的"抽取质量偏低"归因需订正为"抽取未接真实 LLM"（§6 已改）。

### 事实③ `_evaluate_client_call_llm` 全仓无实现

全仓 grep 命中 11 处，**全部**在 `docs/release-notes/`、`backend/CODEBUDDY.md`、`changes/`、`tasks.md`、`proposal.md` 与 `langextract.py` 的 docstring / 注释里；**无 `def _evaluate_client_call_llm`**。

## 3. 实现（本批次改了什么）

| 落点 | 内容 |
|---|---|
| `app/core/config.py` | 新增 `extraction_engine: str = "llm"`（档位 `llm` / `mock`）；唯一消费点 = `LangextractClient.from_settings()` |
| `app/services/extraction/langextract.py` | 新增 `llm` 档：单 chunk 一次 LLM 调用（走接缝 3 `build_chat_model()`，**不新建客户端**）、Prompt 经 `prompt_loader` 渲染 `kg_extraction_v1`、严格解析（未知类型降级 `RELATED` / `confidence < 0.5` 丢弃 / 偏移透传）、失败 → `LangextractError`（**不回落 mock**）；引擎未知档位显式报错 |
| `app/tasks/registry.py` | `_do_extract` 里抽取调用改为 `await asyncio.to_thread(...)`：`llm` 档是同步阻塞的（实测 113.8s / 12 chunk），不能占住 uvicorn 事件循环 |
| `tests/conftest.py` | 补 `EXTRACTION_ENGINE=mock`（与既有 `MINERU_TOKEN=""` / `LLM_API_KEY=""` 同一条"中和外部凭据"纪律） |
| 既有 4 个测试文件 | 显式补 `engine="mock"`（`test_langextract_client` / `test_langextract_chunks` / `test_extraction_prompt_v1` + 执行体走 conftest 环境变量）——档位变显式后 CI 必须自己声明，**行为与改动前完全一致** |
| 新增 `tests/test_extraction_llm_engine.py` | 18 例：正常解析 / 模板渲染 / 多 chunk 绝对偏移 / mention 回查 / 非法 JSON / 空响应 / 调用失败不回落 / 空 JSON 非空结果 / 类型降级 / 低置信丢弃 / 未知档位报错（断言消息含档位名）/ mock 档回归 / 注入优先 / 默认 invoker 走 `build_chat_model` / token 与 trace_id 打点 |
| `backend/.env.example` | 补 `EXTRACTION_ENGINE=llm` 与档位语义注释 |

**日志纪律**：`langextract_llm_call` 每次调用打点 `elapsed_ms` + `prompt/completion/total_tokens`（取不到记 `None`，严禁造数据）；抽取循环用 `logger.contextualize` 带上 `trace_id` / `document_id` / `engine` / `chunk_index`。日志与异常**不落** prompt 原文与密钥（异常只取 `str(exc)[:200]`）。

## 4. 验证

### 4.1 门禁

| 门禁 | 结果 |
|---|---|
| `uv run pytest -q` | ✅ **315 passed**（基线 297，新增 18） |
| `uv run ruff check .` | ✅ All checks passed |
| `uv run ruff format --check .` | ✅ 96 files already formatted |
| `uv run python scripts/check_seams.py` | ✅ **ERROR 0 / WARN 6 / OK 7**（与 S6 基线一致）；"Settings 全部 45 个字段均有消费者代码行" → `extraction_engine` 有消费者 |
| `uv run python scripts/export_openapi.py --check` | ✅ 无 diff（本批次不进契约） |
| 前端 | 无改动（`npm run typecheck` / `lint` 无需重跑，本批次未触 frontend） |

### 4.2 定向切片（真机素材，非全量）

```
cd d:/AIProject/GraphRAG-Agent
uv run --with pypdf python -c "..."
  → docs/annualreport/招商公路：2025年年度报告.pdf 前 30 页
  → 定位：第 106 行「第二节 公司简介和主要财务指标」、115 行「公司的法定代表人 杨旭东」、
    116 行「注册地址 天津自贸试验区…」、123 行「办公地址 北京市朝阳区北土城东路…」
  → 切片 lines[100:460] = 12254 字（覆盖第二节 + 第三节开头）
  → 落盘 backend/storage/demo-slice/gonglu_slice.txt（backend/storage/ 已被 .gitignore 忽略）
```

### 4.3 真机对照（**同一份切片、同一 `from_settings()` 入口**，脚本 `changes/Sprint7.0/verify_slice.py`）

```
cd backend
uv run python ../changes/Sprint7.0/verify_slice.py --engine mock --chunk 1200
uv run python ../changes/Sprint7.0/verify_slice.py --engine llm  --chunk 1200
```

| 指标 | `mock`（正则占位器） | `llm`（真实 DeepSeek） |
|---|---|---|
| chunk 数 | 12 | 12 |
| 实体数 | **120** | **421** |
| 关系数 | 10（全是"前两个 ORG 共现"的 `PARTY_TO` 0.65） | **176**（`EMPLOYED_BY` / `AFFILIATED_WITH` / `RELATED`…带 evidence） |
| 类型分布 | ORG 58 / DATE 57 / MONEY 5（**3 类**） | MONEY 125 / ORG 107 / PRODUCT 88 / DATE 44 / REGULATION 27 / VENUE 21 / PERSON 5 / CONTRACT_CLAUSE 4（**8 类**） |
| 实体样例（top） | `本报告本公司`、`同意公司`、`2018年12月18日公司`、`控股股东服务有限公司`…（**整句碎片**，即 S6-3 坏样例形态） | `招商局公路网络科技控股股份有限公司`(0.99)、`2025年末`(0.99)、`杨旭东`…（**可读的公司名 / 日期 / 法人**） |
| 耗时 | 0.0s | **113.8s**（约 9.5s / chunk） |
| LLM 调用 | 0 | **12 次**，`prompt_tokens=31216`、`completion_tokens=42972` |
| **花费** | ¥0 | **约 ¥0.4062**（按 input ¥2/百万、output ¥8/百万 估算） |

**D6① probe（法人 / 地址是否被抽出来）**：

| 关键词 | `mock` | `llm` |
|---|---|---|
| `杨旭东`（法定代表人） | ❌ False | ✅ **True** |
| `天津自贸试验区`（注册地址） | ❌ False | ✅ **True** |
| `北京市朝阳区北土城东路`（办公地址，公司自身） | ❌ False | ✅ **True** |
| `东方广场`（⚠ 会计师事务所 / 财务顾问地址） | ❌ False | ✅ True（**误报陷阱被确认存在**，见 §5） |

真机关系样例（llm 档，逐字摘自脚本输出）：

```
杨旭东 --EMPLOYED_BY--> 招商局公路网络科技控股股份有限公司 (0.95)
招商公路 --AFFILIATED_WITH--> 招商局公路网络科技控股股份有限公司 (0.95)
招商局公路网络科技控股股份有限公司 --RELATED--> 天津自贸试验区（东疆保税港区）鄂尔多斯路599号东疆商务中心A3楼910 (0.93)
```

### 4.4 D6 两条结论（Sprint 7.1 批次 A 的开工依据）

**D6①「能否抽出可用的法人 / 地址」→ 能（内容可用，类型标签不够）。**

- 证据：`杨旭东`（法人）被抽为 `PERSON` 并与公司建 `EMPLOYED_BY`（0.95）；注册 / 办公地址被抽为 `VENUE` 并经 `RELATED` 关联到公司（0.93）——§4.3 probe 三项全 True。
- **但**：`kg_extraction_v1` 的枚举**没有** `LEGAL_PERSON` / `ADDRESS`。法人只能落 `PERSON`、地址只能落 `VENUE`，关系只能落 `RELATED`。所以"抽得到文本、**打不出专用标签**"——**批次 A 的扩类型（`kg_extraction_v2`）不是可选项，是必需项**。本批次按纪律**未改 Prompt 模板**。

**D6②「2–3 份演示文档之间是否真实存在可被命中的交叉」→ 零交叉。**

- **直接引用 `demo-docs-checklist.md` §8 的人类提取证据**（2026-09-23 预检，原始输出可复核），**未花费用 LLM 复验**——那属于"为确认已有结论而重复烧钱"，违反预算纪律：
  - 法定代表人三人各异：招商公路 **杨旭东** / 招商蛇口 **朱文凯** / 招商轮船 **冯波鸣**；
  - 注册 / 办公地址三地各异：天津自贸试验区（东疆保税港区） / 广东省深圳市南山区蛇口太子路 / 中国（上海）自由贸易试验区西里路；招商银行 pypdf 提取失败（须 MinerU）；
  - 直接控股股东也各异（招商局集团 / 招商局轮船 / 招商局蛇口工业区控股）——需股权穿透才汇合，那是 **S9** 的活。
- 根因不是挑错了公司：**年报天然只披露一家公司的信息**，换任何系都一样。
- **误报陷阱已在本批次被证实**：`东方广场`（会计师事务所 / 财务顾问地址，三份年报共有）在 llm 档**被抽了出来**（probe True）。若坚持用现有年报，两跳算法只会命中"共享中介机构地址" → 伪交叉，**违反 G5 诚实性**。

**建议（写到此处为止，不代找新素材）**：改用能同时披露**多个关联主体的名称 + 法人 + 住所**的材料形态——**关联交易公告**（巨潮 → 同一公司代码 → 公告类别「关联交易」→ 日常关联交易预计 / 确认）或**债券募集说明书 / 招股说明书**。这类文件页数少、多主体天然并列，才是 M4「关联交易识别」的原生数据形态。获取素材需人工介入（巨潮公开列表 API 已收紧），**由用户处理**。

## 5. 关键发现 / 遗留（**均如实登记，不硬凑**）

1. **`char_offset` 不能靠本批次顺带偿还**：llm 档 top20 实体里 `span_ok=False` 占 **14/20**——模型给的 `char_start` / `char_end` 大多**不指向** `mention`（虽在 chunk 范围内、被原样透传）。因此 `S6-1`（`Citation.char_offset` 恒 0 → S10）**保持原登记，不在本批次改口径**；建议批次 A 裁决「偏移与 `mention` 不一致时，改以 `mention` 回查为准」（当前实现已支持回查，只是优先级在透传之后）。
2. **成本实测远高于 tasks §4 的粗估**：12 chunk 花 **¥0.41**（其中 `completion_tokens=42972`——模型每 chunk 输出约 3.6K tokens，远超预估的 1K）。按此外推：**全量重抽一份 250 页年报（150–200 chunk）≈ ¥5–7**，3 份 + 迭代 ≈ **¥15–25+**，**高于 tasks §4「一份 ¥1.5–3」的估算**。Sprint 7.1 批次 A 全量重抽前**必须重新评估预算 / 考虑提高 `extraction_max_chars_per_chunk` 或加实体上限裁剪**。
3. **演示数据仍是旧正则产物**：本批次未重跑演示图谱（预算 + 属批次 A 范围）。重跑步骤（供批次 A 使用）：
   1. `docker start neo4j` 并等约 25 秒（`bolt://localhost:7687` `verify_connectivity`）；
   2. `.env` 确认 `EXTRACTION_ENGINE=llm` + `LLM_API_KEY` + `MINERU_TOKEN`；
   3. 上传 → `document.parse` → `document.extract` → `kg.build`（注意：在线链路**不自串联**，extract / kg.build 需按 S6 integration-log §4.3 的「复位阶段状态 + 直接调执行体」方式驱动）；
   4. 按 ADR-0002 重建 active 版本（`KgVersioningService` / `POST /graph/versions/{version}/activate`），旧版本置 `superseded`；
   5. **新旧不得混用**：旧正则产物与真 LLM 产物同库会让批次 A 的疑点变成伪数据。
4. **`.env` 的 `APP_VERSION` 仍是 1.1.0**（见 §1）：`check_seams.py` 的 1.3.0 三条因此尚未上闸。本批次不 bump，登记给 S7 收尾统一处理。
5. **Neo4j 容器 `Exited (137)`**：本机常态，重跑演示数据前需 `docker start neo4j`。本批次未启动（不重跑图谱）。

## 6. 未触碰项（范围纪律）

- **未改** `prompts/kg_extraction_v1.md`（一个字未动；扩类型属批次 A，须走 v2 + 配置切换）；
- **未动** Sprint 7.1 批次 A 的任何代码（`:LegalPerson` / `:Address` 图建模、两跳算法、`risk.detect` 执行体一律未碰）；
- **未改** `contracts/openapi.yaml`（`--check` 无 diff），前端零改动；
- **未 bump** `app_version`（v1.3.0 是 S7 四批次全完成后的动作）；
- **未 push** 仓库（按用户安排，推送由用户执行）；
- **未全量重抽**任何年报（尤其未碰招商银行那份 30MB / 数百页）；
- **未代下载**新演示素材（关联交易公告等需人工获取）。
