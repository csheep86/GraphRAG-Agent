# KG Extraction Prompt v2（E1 实体抽取 + E2 关系抽取，共用模板）

> **Sprint 7.1 批次 A 新增版本**（`kg_extraction_v1.md` **保留不动**，按 CODEBUDDY.md
> 「Prompt 版本管理规范」只增不改）。相对 v1 的两处改动：
>
> 1. **类型枚举参数化**：`{{entity_types}}` / `{{relation_types}}` 由代码注入
>    （`langextract.py::_render_extraction_prompt`），新增 `LEGAL_PERSON`（法定代表人，
>    自然人）/ `ADDRESS`（注册地址）与 `LEGAL_REP` / `REGISTERED_AT` 两条边；
> 2. **新增一条「法定代表人 / 注册地址」few-shot**（示例 3），让新类型有样例可依——
>    v1 的 few-shot 里没有这两类，模型几乎不会主动产出。
>
> 其余（字段硬约束 / 系统指令 / 去重 / 拒答兜底 / 上限裁剪）**沿用 v1**。

---

## 输入约定

- `{{text}}`：待抽取的短文本片段（由 LangExtractClient 按 `settings.extraction_max_chars_per_chunk` 切分）
- `{{language}}`：`"chinese"` / `"english"`（影响 few-shot 样例语种）
- `{{entity_types}}`：`entity_type` 合法枚举（`|` 分隔，由代码注入）
- `{{relation_types}}`：`relation_type` 合法枚举（`|` 分隔，由代码注入）

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
      "confidence": 0.92
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

### 示例 3：法定代表人与注册地址（v2 新增）

**输入**：

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
    {"id": "rel_003", "source_entity_id": "ent_006", "target_entity_id": "ent_007", "relation_type": "LEGAL_REP", "evidence": "发行人：北京青云科技有限公司，法定代表人：张三", "confidence": 0.98},
    {"id": "rel_004", "source_entity_id": "ent_006", "target_entity_id": "ent_008", "relation_type": "REGISTERED_AT", "evidence": "发行人：北京青云科技有限公司，…住所：北京市海淀区中关村大街 1 号", "confidence": 0.96}
  ]
}
```

## 兜底

- 输入空白 / 编码错误 → `{"entities": [], "relations": []}`
- 实体超过 `settings.extraction_max_entities_per_doc` → 客户端裁剪，按 `confidence` 降序保留前 N 条
- 关系超过 `settings.extraction_max_relations_per_doc` → 同上
