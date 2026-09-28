# Sprint 9 任务卡

## 批次 A（✅ 2026-09-28 完成）

- [x] **CP-T1 schema 冻结**：四字段 + `document_date` + 有效期策略表定义，登记于 `proposal.md` §1
- [x] `Document.document_date`（`Date`、可空、不进契约）+ 迁移 `7989c2c821da`
- [x] `prompts/kg_extraction_v3.md`（v1/v2 零改动）：`{{document_date}}` + `valid_from` / `valid_to` + 跨期变更 few-shot
- [x] 抽取侧：`ExtractedRelation` 扩字段 + 解析（非法日期只丢字段不丢关系）+ `to_json_dict` 导出
- [x] 调用侧：`tasks/registry.py` 把 `document.document_date` 喂给客户端
- [x] 测试 8 条（`tests/test_extraction_temporal.py`）+ 全绿 516；真机探针 `valid_from` 覆盖率 5/5

## 批次 B（⏳ 下批，＝ **CP-T2** 判定点）

> `sprint-calendar` §4 CP-T2：仲裁 R1–R4 落地，**`temporal_poc/run_track_s.py`
> 迁入 `backend/tests/`**，且 n≥3 达 3/3（当前值 / as-of 回溯 / 历史保留）——
> **未达即不得宣称 L1 完成**。

- [x] **四字段落 Neo4j 关系属性**（2026-09-28）：M4 两条 typed 边写 `valid_from` / `valid_to` / `created_at` / `source_document_id`；`expired_at` 由仲裁执行时打
- [x] **R1–R4 仲裁**（2026-09-28，纯函数 `app/services/kg/temporal.py` + 13 条单测）：严格晚于 / 原文最后出现的 tail / 禁同批互封 / 缺日期不参与比较
- [x] **`relation_expiry_policies` 落表 + 被消费**（2026-09-28，迁移 `4e7759c33526`）：消费者 = `policies.load_expiry_policies` → builder；未配置 ⇒ 并存，默认保守
- [ ] Cypher 概览 / 子图 / 问答三条链默认过滤 `valid_to IS NULL`；as-of 查询（**读侧，B2**）
- [ ] **L0 第三项**：答案模板加「依据截至 X 日的披露文件」（新 `kg_qa_vN.md`，**B2**）
- [ ] **PoC 迁入正式测试集**：`temporal_poc/run_track_s.py` 迁到 `backend/tests/`（CP-T2 强制项），**B2**
- [ ] 真机复跑 n≥3（当前 **n=1 已 3/3**），判据不变；**PoC 迁入后才有资格宣称 CP-T2 达成**

## 待办（批次 A 真机发现 → 已由 R2 覆盖）

- [x] 模型会**自行**给出 `valid_to`（变更句场景，张三边 `valid_to=2025-05-01`）。
      R2 已按「原文最后出现的 tail」独立判定，**不依赖模型的 `valid_to`**——
      模型给不给都一样，这正是 D-3「不依赖 LLM」要的性质。

## 降级登记（批次 B 实测发现，不得含糊）

- [ ] **通用 `[:RELATION]` 层暂无跨文档仲裁**：`:Entity` 的 id 是 `ent_<uuid>`（每次抽取都变），
      两份文档里的同一家公司是两个节点 ⇒ `(head, relation_type)` 无从匹配。
      需先有**实体消解**（S9 已排）。本期仲裁只对 **M4 主体层**（`sha256(name)` 稳定 id）生效。
