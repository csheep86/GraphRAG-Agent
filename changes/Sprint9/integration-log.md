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

## 6. 迁移

`7989c2c821da_add_documents_document_date_adr_0005_l0.py`：autogenerate 后人工审阅，
仅一条 `add_column`，`downgrade` 对称。空库 `upgrade head` 通过，
等价性测试（`test_migrations_baseline`）自动把新列纳入比对——
这是 S9.7 纪律的第一次实战，**加列忘写迁移 ⇒ CI 必红**已被验证有效。
