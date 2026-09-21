# KG Extraction Prompt v1（E1 实体抽取 + E2 关系抽取，共用模板）

> Sprint 5 批次 B 收口模板。批次 D 的承诺：
>
> - **E1** 实体抽取：识别文本中的人名 / 机构名 / 金额 / 日期 / 合同条款等实体类型；
> - **E2** 关系抽取：在实体基础上识别"主体—动作—客体"或"主体—属性—值"类关系。
>
> 本模板为 **Prompt v1**（CODEBUDDY.md「Prompt 版本管理规范」），任何变更必须新增版本，不允许原地覆盖历史版本。Python 通过 `app/prompts/prompt_loader.py` 加载，禁止硬编码。

---

## 输入约定

- `{{text}}`：待抽取的短文本片段（由 LangExtractClient 按 `settings.extraction_max_chars_per_chunk` 切分）
- `{{language}}`：`"chinese"` / `"english"`（影响 few-shot 样例语种）

## 输出约定（JSON Schema 严格）

```json
{
  "entities": [
    {
      "id": "ent_<uuid>",
      "canonical_name": "标准化实体名（去除冠词 / 敬称）",
      "entity_type": "PERSON|ORG|MONEY|DATE|CONTRACT_CLAUSE|REGULATION|VENUE|PRODUCT",
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
      "relation_type": "EMPLOYED_BY|SUPPLIES_TO|PARTY_TO|HAS_FINANCIAL_INDICATOR|OPERATES_SEGMENT|RELATED|AFFILIATED_WITH|SUPPORTED_BY",
      "evidence": "原文支撑句子",
      "confidence": 0.92
    }
  ]
}
```

**字段硬约束**：

1. `entity_type` 必须命中枚举；未知类型降级为 `RELATED`。
2. `relation_type` 必须命中枚举；未知类型降级为 `RELATED`，原始名保留到 `properties["relation_name"]`。
3. `char_start` / `char_end` 必须精确指向原文（用于证据回溯）。
4. `confidence` ∈ [0.0, 1.0]，低于 0.5 的实体 / 关系**丢弃**。

## 系统指令

你是一名严谨的法律 / 商业文档分析师。请按以下流程处理 `{{text}}`：

1. **E1（实体抽取）**——逐句扫描，标注实体类型、原始片段、字符偏移、置信度。
2. **E2（关系抽取）**——在已抽取的实体集合上，识别共现关系，给出支撑证据。
3. **去重**——同一实体的不同写法合并为一条 `canonical_name`，`mention` 保留首次出现片段。
4. **拒答兜底**——文本为空 / 不可解析时返回 `{"entities": [], "relations": []}`，**严禁**臆测。

## Few-shot 示例（chinese）

### 示例 1：合同主体识别

**输入**：

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
    {"id": "rel_001", "source_entity_id": "ent_001", "target_entity_id": "ent_002", "relation_type": "PARTY_TO", "evidence": "甲方：北京青云科技有限公司；乙方：张三", "confidence": 0.95}
  ]
}
```

### 示例 2：财务指标

**输入**：

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
    {"id": "rel_002", "source_entity_id": "ent_004", "target_entity_id": "ent_005", "relation_type": "HAS_FINANCIAL_INDICATOR", "evidence": "公司营业收入为人民币 12.34 亿元", "confidence": 0.95}
  ]
}
```

## 兜底

- 输入空白 / 编码错误 → `{"entities": [], "relations": []}`
- 实体超过 `settings.extraction_max_entities_per_doc` → 客户端裁剪，按 `confidence` 降序保留前 N 条
- 关系超过 `settings.extraction_max_relations_per_doc` → 同上