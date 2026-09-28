# KG Extraction Prompt v3（E1 实体抽取 + E2 关系抽取，共用模板）

> **Sprint 9 批次 A 新增版本**（`kg_extraction_v2.md` **保留不动**，按 CODEBUDDY.md
> 「Prompt 版本管理规范」只增不改）。相对 v2 的改动，全部来自
> **`ADR-0005` §4 / §6 L0**（知识时效）：
>
> 1. **关系时态字段**：每条关系新增 `valid_from` / `valid_to`（事实维，见下方字段硬约束 5）；
> 2. **文档日期兜底**：新增 `{{document_date}}` 占位符，供**没有显式日期**的关系取兜底值
>    （R4 不猜值纪律：没有就是不猜，取文档日期而不是模型推断的日期）；
> 3. **变更句 few-shot**（示例 4）：让模型学会在一句话里同时抽出旧值与新值，
>    并给两者各自的生效日期——下游 R2 仲裁（同 `valid_from` 取最新 `tail`）的输入前提。
>
> 其余（实体 Schema / 系统指令 / 去重 / 拒答兜底 / 上限裁剪 / 类型枚举参数化）**沿用 v2**。

---

## 输入约定

- `{{text}}`：待抽取的短文本片段（由 LangExtractClient 按 `settings.extraction_max_chars_per_chunk` 切分）
- `{{language}}`：`"chinese"` / `"english"`（影响 few-shot 样例语种）
- `{{entity_types}}`：`entity_type` 合法枚举（`|` 分隔，由代码注入）
- `{{relation_types}}`：`relation_type` 合法枚举（`|` 分隔，由代码注入）
- `{{document_date}}`：本文档的日期（`YYYY-MM-DD`；**未知时为字符串 `unknown`**）。
  仅作**兜底**用：关系没有显式生效日期时，`valid_from` 取它；**不得**用于回填 `valid_to`

## 输出约定（JSON Schema 严格）

```json
{
  "entities": [
    {
      "id": "ent_<uuid>",
      "canonical_name": "标准化实体名（去除冠词 / 敬称）",
      "entity_type": "{{entity_types}}",
      "mention": "原始文本中的关键短语",
      "char_start": 0,
      "char_end": 10,
      "confidence": 0.95
    }
  ],
  "relations": [
    {
      "id": "rel_<uuid>",
      "source_entity_id": "ent_<uuid>",
      "target_entity_id": "ent_<uuid>",
      "relation_type": "{{relation_types}}",
      "evidence": "原文支撑句子",
      "confidence": 0.92,
      "valid_from": "2025-05-01",
      "valid_to": null
    }
  ]
}
```

**字段硬约束**：

1. `entity_type` 必须命中 `{{entity_types}}` 枚举；未知类型降级为 `RELATED`。
   - `LEGAL_PERSON` **只用于自然人法定代表人**（`canonical_name` 填姓名，不要带"法定代表人"字样）；
     法人的职务 / 机构本身是 `ORG`，**不要**混用。
   - `ADDRESS` 用于**注册地址 / 住所 / 办公地址**这类完整地址串；
     **不含**会计师事务所、财务顾问、承销商等第三方的地址。
2. `relation_type` 必须命中 `{{relation_types}}` 枚举；未知类型降级为 `RELATED`，原始名保留到 `properties["relation_name"]`。
   - `LEGAL_REP`：`ORG → LEGAL_PERSON`（某机构的法定代表人是某人）。
   - `REGISTERED_AT`：`ORG → ADDRESS`（某机构注册 / 住所位于某地址）。
3. `char_start` / `char_end` 必须精确指向**原文中 `mention` 出现的位置**（用于证据回溯），
   必须与 `mention` 逐字对应；拿不准就留空，由程序按 `mention` 回查。
4. `confidence` ∈ [0.0, 1.0]，低于 0.5 的实体 / 关系**丢弃**。
5. **时态字段（ADR-0005 §4 四字段里的"事实维"两个）**——格式一律 `YYYY-MM-DD`：
   - `valid_from`：事实**开始成立**的日期。
     - 文本显式给出（"自 2025 年 5 月起"、"2024 年度营业收入"）⇒ 照抄为日期；
     - **没有显式日期** ⇒ 取 `{{document_date}}`（兜底值，不是"猜"出来的）；
     - `{{document_date}}` 为 `unknown` 且文本也没有 ⇒ 留 `null`（下游按不可定时效处理）。
   - `valid_to`：事实**失效**的日期。**只有文本明确写了失效日期 / 截止日期时才填**，
     其余一律 `null`（`null` = 仍有效）。
   - **禁止推断**：不得用常识、行业惯例、相邻文本推测起止日期；
     "2024 年度报告"不意味着有效期到 2025 年——没有明写就是 `null`。
   - 同一实体的**两个不同取值**（"由张三变更为李四"）要**各出一条关系**，
     分别带各自的 `valid_from`，**不要**合并、也不要替系统判定谁失效。

## 系统指令

你是一名严谨的法律 / 商业文档分析师。请按以下流程处理 `{{text}}`：

1. **E1（实体抽取）**——逐句扫描，标注实体类型、原始片段、字符偏移、置信度。
2. **E2（关系抽取）**——在已抽取的实体集合上，识别共现关系，给出支撑证据。
3. **时态标注**——按上面第 5 条给每条关系标 `valid_from` / `valid_to`，拿不准就 `null`。
4. **去重**——同一实体的不同写法合并为一条 `canonical_name`，`mention` 保留首次出现片段。
5. **拒答兜底**——文本为空 / 不可解析时返回 `{"entities": [], "relations": []}`，**严禁**臆测。

## Few-shot 示例（chinese）

### 示例 1：合同主体识别（无显式日期 ⇒ 取 `{{document_date}}`）

**输入**（`{{document_date}}` = `2024-03-18`）：

```
甲方：北京青云科技有限公司（统一社会信用代码 91110108MA0001ABC）。
乙方：张三，身份证 11010119900109XXXX，联系电话 13800001234。
```

**期望输出**：

```json
{
  "entities": [
    {"id": "ent_001", "canonical_name": "北京青云科技有限公司", "entity_type": "ORG", "mention": "北京青云科技有限公司", "char_start": 2, "char_end": 12, "confidence": 0.99},
    {"id": "ent_002", "canonical_name": "张三", "entity_type": "PERSON", "mention": "张三", "char_start": 35, "char_end": 37, "confidence": 0.97}
  ],
  "relations": [
    {"id": "rel_001", "source_entity_id": "ent_001", "target_entity_id": "ent_002", "relation_type": "PARTY_TO", "evidence": "甲方：北京青云科技有限公司；乙方：张三", "confidence": 0.95, "valid_from": "2024-03-18", "valid_to": null}
  ]
}
```

> 注：原文没写生效日期，`valid_from` 取 `{{document_date}}`——这是**兜底**，不是推断。

### 示例 2：财务指标（事件自带时间 ⇒ 照抄）

**输入**（`{{document_date}}` = `2025-04-20`）：

```
2024 年度公司营业收入为人民币 12.34 亿元，较上年同期增长 15.6%。
```

**期望输出**：

```json
{
  "entities": [
    {"id": "ent_003", "canonical_name": "2024", "entity_type": "DATE", "mention": "2024", "char_start": 0, "char_end": 4, "confidence": 0.99},
    {"id": "ent_004", "canonical_name": "公司", "entity_type": "ORG", "mention": "公司", "char_start": 7, "char_end": 9, "confidence": 0.7},
    {"id": "ent_005", "canonical_name": "12.34 亿元", "entity_type": "MONEY", "mention": "12.34 亿元", "char_start": 16, "char_end": 24, "confidence": 0.98}
  ],
  "relations": [
    {"id": "rel_002", "source_entity_id": "ent_004", "target_entity_id": "ent_005", "relation_type": "HAS_FINANCIAL_INDICATOR", "evidence": "公司营业收入为人民币 12.34 亿元", "confidence": 0.95, "valid_from": "2024-01-01", "valid_to": null}
  ]
}
```

### 示例 3：法定代表人与注册地址（v2 沿用）

**输入**（`{{document_date}}` = `2024-08-08`）：

```
发行人：北京青云科技有限公司，法定代表人：张三，住所：北京市海淀区中关村大街 1 号。
```

**期望输出**：

```json
{
  "entities": [
    {"id": "ent_006", "canonical_name": "北京青云科技有限公司", "entity_type": "ORG", "mention": "北京青云科技有限公司", "char_start": 4, "char_end": 14, "confidence": 0.99},
    {"id": "ent_007", "canonical_name": "张三", "entity_type": "LEGAL_PERSON", "mention": "张三", "char_start": 24, "char_end": 26, "confidence": 0.97},
    {"id": "ent_008", "canonical_name": "北京市海淀区中关村大街 1 号", "entity_type": "ADDRESS", "mention": "北京市海淀区中关村大街 1 号", "char_start": 31, "char_end": 45, "confidence": 0.96}
  ],
  "relations": [
    {"id": "rel_003", "source_entity_id": "ent_006", "target_entity_id": "ent_007", "relation_type": "LEGAL_REP", "evidence": "发行人：北京青云科技有限公司，法定代表人：张三", "confidence": 0.98, "valid_from": "2024-08-08", "valid_to": null},
    {"id": "rel_004", "source_entity_id": "ent_006", "target_entity_id": "ent_008", "relation_type": "REGISTERED_AT", "evidence": "发行人：北京青云科技有限公司，…住所：北京市海淀区中关村大街 1 号", "confidence": 0.96, "valid_from": "2024-08-08", "valid_to": null}
  ]
}
```

### 示例 4：跨期变更（v3 新增，**旧值与新值各出一条**）

**输入**（`{{document_date}}` = `2025-06-30`）：

```
该公司法定代表人于 2023 年 4 月起由张三担任；自 2025 年 5 月起，法定代表人由张三变更为李四。
```

**期望输出**：

```json
{
  "entities": [
    {"id": "ent_009", "canonical_name": "公司", "entity_type": "ORG", "mention": "公司", "char_start": 3, "char_end": 5, "confidence": 0.75},
    {"id": "ent_010", "canonical_name": "张三", "entity_type": "LEGAL_PERSON", "mention": "张三", "char_start": 31, "char_end": 33, "confidence": 0.97},
    {"id": "ent_011", "canonical_name": "李四", "entity_type": "LEGAL_PERSON", "mention": "李四", "char_start": 52, "char_end": 54, "confidence": 0.97}
  ],
  "relations": [
    {"id": "rel_005", "source_entity_id": "ent_009", "target_entity_id": "ent_010", "relation_type": "LEGAL_REP", "evidence": "该公司法定代表人于 2023 年 4 月起由张三担任", "confidence": 0.96, "valid_from": "2023-04-01", "valid_to": null},
    {"id": "rel_006", "source_entity_id": "ent_009", "target_entity_id": "ent_011", "relation_type": "LEGAL_REP", "evidence": "自 2025 年 5 月起，法定代表人由张三变更为李四", "confidence": 0.98, "valid_from": "2025-05-01", "valid_to": null}
  ]
}
```

> 注：**两条都留** `valid_to = null`。谁失效由下游**确定性仲裁**（ADR-0005 §5 R1 / R2）判定，
> 模型不替系统做这个判断——旧值保留且时间戳明确，既保证当前值唯一、又保证历史可回溯。

## 兜底

- 输入空白 / 编码错误 → `{"entities": [], "relations": []}`
- 实体超过 `settings.extraction_max_entities_per_doc` → 客户端裁剪，按 `confidence` 降序保留前 N 条
- 关系超过 `settings.extraction_max_relations_per_doc` → 同上
- `valid_from` / `valid_to` 格式非法（非 `YYYY-MM-DD`）→ 客户端丢弃该字段（置空），**不丢关系**
