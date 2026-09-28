# Sprint 9 批次 A 集成日志（证据链）

> 2026-09-28 实跑（Windows / DeepSeek 真机 / SQLite）。

## 1. 抽取侧改造（零外部依赖测试）

`tests/test_extraction_temporal.py` 8 条全过：

- v3 模板声明 `{{document_date}}`，**v2 的占位符集合未被改动**（`test_v2_is_untouched`）；
- 真实文档日期被渲染进 Prompt（`2025-06-30` 出现在 LLM 输入里）；
- **日期未知渲染为 `"unknown"`**——不代填今天（R4）；
- `valid_from` / `valid_to` 解析并进 `to_json_dict`；
- **中文日期格式 ⇒ 只丢时态字段、关系本体保留**（`test_invalid_date_drops_field_but_keeps_relation`）；
- 模型没给日期 ⇒ `None`（不解读为"今天生效"）。

连锁修正（版本升级导致旧快照断言红，属预期）：

- `test_prompt_loader`「取最大版本」改为**按可用版本集合取 max**（写死 2 ⇒ 每次升版必红，
  把语义判断退化成数字游戏）；
- `test_extraction_prompt_v1` 的产物 shape 断言补 `valid_from` / `valid_to`。

全量：**516 passed**（批次前 508），ruff check / format 全绿。

## 2. 真机探针（DeepSeek，`document_date=2026-06-30`）

输入 5 句（含成立时间 / 变更句 / 注册资本无显式日期）。结果：

| relation_type | valid_from | valid_to | 备注 |
|---|---|---|---|
| `RELATED` | 2018-03-01 | None | 动词不在枚举，降级为 RELATED（符合 v3 硬约束 2） |
| `LEGAL_REP`（张三） | 2023-04-01 | None | 与下一条构成跨期矛盾，需仲裁 |
| `LEGAL_REP`（张三） | 2023-04-01 | **2025-05-01** | **模型自行给了失效日**（见 §3） |
| `LEGAL_REP`（李四） | 2025-05-01 | None | 当前值候选 |
| `HAS_FINANCIAL_INDICATOR` | **2026-06-30** | None | 文本无显式日期 ⇒ 取 `document_date` 兜底 ✓ |

**`valid_from` 覆盖率 = 5/5 = 100%**（ADR-0005 P3-L0 判据 ≥ 90%；注：本次 **n=1**，
「稳定性」按 PoC 口径要 n≥3，留批次 B 复跑）。

## 3. 本次实测的两个发现（登记，不装看不见）

1. **模型会自己填 `valid_to`**（变更句场景给了 `2025-05-01`）。这不算违反 R4
   （日期在文本里明写），但意味着**仲裁不能依赖模型输出**：模型并非每次都给，
   遗漏时只能靠 R2 规则兜底 ⇒ 批次 B 的规则仍是必需品，不是冗余。
2. **降级边仍占一席**（`RELATED`）：`"成立于 2018 年 3 月"` 这类句子在受控枚举里
   无处安放。它是"有依据的事实"，但 `(head, relation_type)` 精确匹配仲裁
   对 `RELATED` 无能为力（不同类型无法判定矛盾）⇒ **L1 的仲裁默认只管受力点明确的
   类型**（`LEGAL_REP` / `REGISTERED_AT` 等），`RELATED` 不参与——批次 B 落实。

## 4. 批次 B（写侧 + 仲裁）：真机 Neo4j 端到端，**n=1 达 3/3**

场景：同一租户先后构建两份披露文件（doc-A 2023-04-01 法人张三 / doc-B 2025-05-01 法人李四），
策略表里 `LEGAL_REP` 配成 `single_current`。真机 Neo4j + SQLite 实跑：

| 步骤 | affiliation_edges | expired | 说明 |
|---|---|---|---|
| build v-l1-a | 1 | 0 | 首份文档，没有可比旧边 |
| build v-l1-b | 1 | **1** | 李四取代张三 ⇒ R1 封旧边 |

图谱里的最终状态：

| tail | valid_from | valid_to | source_document_id | invalidated_reason |
|---|---|---|---|---|
| 张三 | 2023-04-01 | **2025-05-01** | doc-A | **R1** |
| 李四 | 2025-05-01 | NULL | doc-B | — |

判分（ADR-0005 P3-L1 口径）：**当前值唯一 = 李四 ✓ / as-of 2024-06-01 = 张三 ✓ /
历史保留 = 2 条边活着 1 条 ✓** —— 3/3。

**注意 n=1**：CP-T2 要求 n≥3，且要求 PoC 迁入 `backend/tests/`
（批次 B2 的剩余项）。这一轮先明确：**写侧闭环已被真机证实**，
"当前值唯一"不再是纸面结论。

## 5. 批次 B 的关键发现（降级登记，不装看不见）

1. **通用 `[:RELATION]` 层做不了跨文档仲裁**——`:Entity` 的 id 是 `ent_<uuid>`，
   **每次抽取都不同**，两份文档里的同一家公司是两个节点，`(head, relation_type)`
   匹配无从谈起。要做需先有**实体消解**（属 M4 完整化，`sprint-calendar` S9 已排）。
   ⇒ 本期仲裁**只对 M4 主体层**（`sha256(name)` 稳定 id）生效，这也是价值最高的两类边
   （`LEGAL_REP` / `REGISTERED_AT`）。
2. **同一事实的多份证据必须合并**，且 `valid_from` 取**最早**：dict 直接覆盖是
   "后来者赢"，会把 2023 年披露的事实改成 2025 年的生效日——悄悄改写历史。

## 6. 批次 B2（读侧 + 收口）：**CP-T2 达成**，n=3 达 3/3

### 6.1 读侧时态视图

`graphs.py` 新增 `_temporal_view(alias)` + `validate_as_of`，**判据只有一处**，接入五条链：
概览 / 实体详情 / 全实体子图 / **共享法人** / **共享地址**；`as_of` 一路透传到 `fetch_*` 签名。

判据本身是一段字符串常量：`as_of` 为 NULL ⇒ 只看当前（`valid_to IS NULL`）；
非空 ⇒ 把视图倒回那一天。两种视图**共用同一段字符串**，
这样"默认视图"与"as-of 视图"不可能各说各话。

其中**共享法人 / 共享地址是时态视图真正生效的地方**：疑点的判据是"现在是否仍由同一人
代表"，旧法定代表人早在当年就被 R1 封了边——不过滤有效期，这条疑点会**年年报警**。

### 6.2 L0 欠账结清：答案模板

新增 `prompts/kg_qa_v3.md`（**v1 / v2 零改动**）：`{{as_of_date}}` 取自 `documents.document_date`，
v2 的 chunk 引用纪律（chunk_id 必须逐字出现在 text_chunks、F3 引用覆盖率 100%）**一条不减**。
**顺带解决了另一个问题**：批次 A 落的那列此前一直是没有消费者的预留字段，现在它是
"答案说依据截至哪天"的唯一出处；不可得时给字面量 `unknown`，不许让 LLM 自己编。

### 6.2.1 一次必须记录的操作失误（已纠正）

动手时**误把改动写进了 `prompts/kg_qa_v2.md`**——而 v2 是 Sprint 6 批次 B 的既有版本
（chunk 级引用回查），等于**原地覆盖了历史版本**，直接违反 CODEBUDDY.md
「Prompt 版本管理规范」第 2 条；更糟的是它抹掉了「chunk_id 必须逐字出自 text_chunks、
禁止伪造」这条 F3 引用的机械判据。

**没有任何一道门禁拦得住**：测试全绿、ruff 全绿、契约零漂移——因为 loader 只校验占位符，
`test_prompt_loader` 里 KG_QA_VARS 加了 `as_of_date` 之后连渲染都是绿的。
最后是靠 `git status` 里那行反常的 ` M prompts/kg_qa_v2.md`（新文件本该是 `??`）
发现的，随即从 HEAD 逐字节取回原文，改动改投 v3。

教训：**prompt 目录里的任何文件变"已修改"都应当视为红灯**——它们只允许新增，
不允许修改。这条现在写在这里，下次谁看见 `M prompts/` 就该停手。

日期查询失败降级为 `None`（不是炸掉问答）——与既有语义一致：连 QaLog 写失败都不该影响回答。

### 6.3 PoC 迁入正式测试集（`sprint-calendar` §4 CP-T2 强制项）

`temporal_poc/run_track_s.py` 的判分口径迁入 `tests/test_temporal_track_s.py`，三处改造：
**不调 LLM**（relations 的 `valid_from` 写死，要验的不是抽取）、**默认零外部依赖**
（`conftest` 刻意把 Neo4j 指到不可达端口保 CI 确定性）、**重复 3 轮**（单次成功只证明能跑）。
`temporal_poc/README.md` 顶部已注明"判据改动一律走正式测试集"，PoC 目录转为实验原迹。

真机（设 `TEMPORAL_TRACK_REAL_URI` 后同一组断言跑三轮）：

| 轮次 | 当前值 | as-of 2024-06-01 | 历史保留（总边 / 存活） |
|---|---|---|---|
| v-track-s-1 | 李四 | 张三 | 2 / 1 |
| v-track-s-2 | 李四 | 张三 | 2 / 1 |
| v-track-s-3 | 李四 | 张三 | 2 / 1 |

⇒ **3/3**。pytest 全量 516 → 544。

### 6.4 真机抓到的一个真 bug（值得单独记一笔）

`_temporal_view` 的初版第二个条件写成
`($as_of IS NULL OR valid_to IS NULL OR valid_to > $as_of)`：
`$as_of` 为 NULL 时**整个条件恒真** ⇒ 默认视图变成了"什么都查得到"，docstring 声称的
"只看当前值"与实际行为**正好相反**。表现是当前法定代表人读到 `['张三', '李四']`。

它骗过了所有单元测试（8 分钟后它们不看 Cypher 语义），也骗过了肉眼review（读起来像对的），
只有**真跑一遍 Cypher**才暴露。教训：凡是"判据"，注释声称的语义必须有一条真机断言看着。
现在这段 warning 就写在 `_temporal_view` 的 docstring 里，防止有人为了"对称"改回去。

## 7. 迁移

`7989c2c821da_add_documents_document_date_adr_0005_l0.py`：autogenerate 后人工审阅，
仅一条 `add_column`，`downgrade` 对称。空库 `upgrade head` 通过，
等价性测试（`test_migrations_baseline`）自动把新列纳入比对——
这是 S9.7 纪律的第一次实战，**加列忘写迁移 ⇒ CI 必红**已被验证有效。
