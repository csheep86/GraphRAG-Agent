# Proposal: Sprint 7.0 还债批次 —— 抽取链路接真实 LLM（ `${LLM_PROVIDER}` 落地）

> **状态**：**已批准（2026-09-23 拍板）；代码未动工**——按既定分工，本批次在 **Sprint 7 专属新会话**开工，不在 S6 收尾会话里动手（避免上下文污染）。
> **性质**：**范围变更**——`docs/v1.1.0-demo-mvp-plan.md` §6.2 的 S7 批次划分 **不含本批次**。本批次是插入 S7 之前的**前置还债**，须显式登记（见本文「范围变更登记」），不静默塞进批次 A。
> **附加职责**：本批次同时充当 **S7 的可行性验证**——必须回答 **D6**（见 `Sprint7.1/proposal.md`）：① 能否抽出**可用**的法人 / 地址；② 2–3 份演示文档之间是否**真实存在**可被算法命中的交叉。任一答案为否 → 按 plan §6.4 换演示文档或上报，**不得带病往下走**。
> **为什么必须前置**：S7 批次 A（M4 `:LegalPerson` / `:Address`）**依赖能抽出法人 / 地址**；当前链路抽不出，不先还这笔债，S7 的疑点就是伪数据。

## Why

### 三条已核实的事实（有文件行号，可复核）

1. **生产链路实际跑的是正则占位抽取器，不是 LLM。**
   - `backend/app/services/extraction/langextract.py` 第 267–276 行：`from_settings()` **不传 `chunk_extractor` / LLM client**；
   - 同文件第 262 行：`self._chunk_extractor = chunk_extractor or _default_extract_chunk`；
   - `_default_extract_chunk`（181–226 行）是**正则占位器**，只出 `ORG` / `PERSON` / `MONEY` / `DATE` 四类（第 191–196 行）。
   - **推论**：`LLM_API_KEY` 配了也没用——抽取阶段根本不调 LLM。

2. **S6「实体质量低」的根因被定位到正则，不是 Prompt。**
   - 正则 `_RE_ORG`（166–168 行）形如 `[\u4e00-\u9fffA-Za-z0-9]{2,30}(?:有限公司|…|集团|公司|…)`；
   - S6 真机那批"整句成实体"（如"本报告汇总了集团"、"智能制造与数字服务两大板块合计贡献集团"）**全部符合该正则**（长串 + `集团` 后缀），是**贪婪匹配产物**，与模型无关；
   - 因此 **v1.2.0 release notes §6.1 / `backend/CODEBUDDY.md` §4 `S6-3` 的归因需要订正**：不是"抽取质量偏低"，而是"抽取未接真实 LLM"。

3. **这笔债悬空，没有任何 Sprint 承接。**
   - 全仓 grep `_evaluate_client_call_llm`：**只有注释 / docstring / release notes 引用，无实现**；
   - `docs/release-notes/v1.1.0.md` §6.1 把 E1/E2 登记为 `unresolved`，根因写明"默认 mockable 正则占位"；§6.3 的承接写的是「**注入 provider 后启用**」——**未落到任何 Sprint**；
   - 结果：`EXTRACTION_PROVIDER=langextract` 这个"档位"至今没有真实实现，形成**名义上是 provider、实际是 stub** 的状态。

### 为什么 S7 批次 A 绕不过它

plan §6.2 批次 A 要为 M4 补 `:LegalPerson` / `:Address`。正则四类里**没有法人与地址**——plan §6.4 给的出路是"抽取质量不达标就换演示文档"，但这次**根因不是文档**，换任何文档都抽不出法人 / 地址。若不解决，S7 产出的疑点形如「A 公司与 B 公司共用法人『本报告汇总了集团』」，属伪数据，直接违反 G5 诚实性纪律。

**三条替代路径已评估，均不可行**：

| 替代方案 | 不可行理由 |
|---|---|
| 换演示文档（plan §6.4 兜底） | 根因是抽取器不是文档，换文档抽不出法人 / 地址 |
| 用接缝 8「外部数据导入」拿工商 / 股权离线包 | ADR-0004 §2.1 明确：**S7 只定义 schema + dry-run，不建表**，不能当数据源 |
| 等 CSV 供应商主数据对齐（M4 §3 验收 1） | csv 解析承接到 **S9**（release notes v1.1.0 §6.3），远水不解近渴 |

## What Changes

1. **实现真实 LLM 抽取**：沿用 `prompts/kg_extraction_v1.md` 的 JSON Schema，单 chunk 调一次 LLM（走 `app/services/providers/llm.py` 的 `build_chat_model()`，接缝 3，不绕开 provider）。输入超长按 `settings.extraction_max_chars_per_chunk` 先切再抽，与 mockable 路径共用切分逻辑。
2. **mockable 升级为「显式开关 + 测试注入」，不再是隐式默认**：
   - 建议新增显式配置项（如 `settings.extraction_engine`，档位 `llm` / `mock`），**未知档位显式报错、不静默回退**（plan §4.4 纪律，与 `llm_provider` / `parser_provider` 同策略）；
   - CI / 单元测试通过构造参数注入 mock，**保住零外部依赖**这条收益。
3. **失败语义不静默**：LLM 调用失败 / 超时 / 输出不可解析 → 抛 `LangextractError`（外层 `document.extract` 的 tenacity 统一重试，**不在内部加第二层重试**）；**严禁失败后静默回落 mock**——那等于把基础设施故障伪装成业务结论（LC1-9）。
4. **严格按 Schema 解析**：未知 `entity_type` / `relation_type` 降级 `RELATED`（原始名留痕），`confidence < 0.5` 丢弃，`char_start` / `char_end` 原样透传。

## 预期收益（超出 S7 本身的连带偿还）

| 项 | 现状 | 7.0 之后 |
|---|---|---|
| E1 / E2（`v1.1.0` §6.1 `unresolved`） | 无真实数据，不能产出 | **可产出**（是否立项评估另议，见 Non-goals） |
| `Citation.char_offset` 恒 0（`CODEBUDDY.md` `S6-1` → S10） | 恒为 chunk 起点 | 有机会**提前偿还**——前提是 `kg.build` 把实体的 `char_start` 写进 `:Entity`（**本批次先核实是否顺带成立，不成不硬凑**） |
| 整句成实体（`S6-3` → S9） | 正则贪婪命中 | 根治 |

## 范围变更登记（口径留痕）

- **变更内容**：在 S7 之前插入一个**计划外批次**（`Sprint7.0`），承接 v1.1.0 §6.3 悬空债务「抽取为 mockable 正则占位 → 注入 provider 后启用」。
- **估时**：约 **0.5–1 天**（不含演示数据重跑，见下方副作用）。
- **副作用（须提前接受）**：现有图谱是正则产物，接真 LLM 后**演示数据需重抽 + 按 ADR-0002 重建 active 版本**，否则演示数据仍是旧正则产物（新旧混用会污染 S7 的疑点）。本批次须给出重跑步骤，或明确"重跑属演示准备、不在本批次验收"。
- **若你否决本批次**：则 S7 批次 A 无法按 plan 交付真实疑点，需要在 `plan §6.2` 上登记「S7 的 M4 为 mockable 数据演示」，并在 release notes v1.3.0 显式声明——**不得静默**。

## Impact

**契约（`contracts/openapi.yaml`）**：**无变更**（内部链路替换，端点与响应体不变）；收尾须 `export_openapi.py --check` 无 diff。

**前端**：**无**。

**后端**：`app/services/extraction/langextract.py`（真实抽取实现 + 开关 + 解析）、`app/core/config.py`（新增配置项，**必须有消费者**）、`app/tasks/registry.py`（`document.extract` 执行体确认无需改动即受益）、单测与集成测试。

**Prompt**：**本批次不新增、不修改 Prompt 版本**（沿用 `kg_extraction_v1`；扩展类型枚举属批次 A 的事——见 `Sprint7.1/proposal.md` 已更正的方案）。

## Non-goals

- **不做**实体消解（→ **S9**）、三方金额不一致 / 环路检测（→ S9）、`:LegalPerson` / `:Address` 图建模（→ 批次 A）；
- **不改** Prompt 模板内容（`kg_extraction_v1` 的 entity_type 枚举若需扩法人 / 地址，属批次 A，须走「新增 v2 + 配置切换」）；
- **不立项评估 E1/E2**（属 Sprint 8 批次 C 治理范围；本批次只提供"能产出真实抽取物"的能力）；
- **不顺手修** S6 其余遗留（`_snippet` 省略号 → S10、qa 会话 `doc_count=24` 文案）。
