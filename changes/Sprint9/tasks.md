# Sprint 9 任务卡

## 批次 A（✅ 2026-09-28 完成）

- [x] **CP-T1 schema 冻结**：四字段 + `document_date` + 有效期策略表定义，登记于 `proposal.md` §1
- [x] `Document.document_date`（`Date`、可空、不进契约）+ 迁移 `7989c2c821da`
- [x] `prompts/kg_extraction_v3.md`（v1/v2 零改动）：`{{document_date}}` + `valid_from` / `valid_to` + 跨期变更 few-shot
- [x] 抽取侧：`ExtractedRelation` 扩字段 + 解析（非法日期只丢字段不丢关系）+ `to_json_dict` 导出
- [x] 调用侧：`tasks/registry.py` 把 `document.document_date` 喂给客户端
- [x] 测试 8 条（`tests/test_extraction_temporal.py`）+ 全绿 516；真机探针 `valid_from` 覆盖率 5/5

## 批次 B（✅ 2026-09-28 完成，＝ **CP-T2** 判定点）

> `sprint-calendar` §4 CP-T2：仲裁 R1–R4 落地，**`temporal_poc/run_track_s.py`
> 迁入 `backend/tests/`**，且 n≥3 达 3/3（当前值 / as-of 回溯 / 历史保留）。
> **B1 + B2 全部完成 ⇒ CP-T2 达成，可以宣称 L1 完成。**

- [x] **四字段落 Neo4j 关系属性**（2026-09-28）：M4 两条 typed 边写 `valid_from` / `valid_to` / `created_at` / `source_document_id`；`expired_at` 由仲裁执行时打
- [x] **R1–R4 仲裁**（2026-09-28，纯函数 `app/services/kg/temporal.py` + 13 条单测）：严格晚于 / 原文最后出现的 tail / 禁同批互封 / 缺日期不参与比较
- [x] **`relation_expiry_policies` 落表 + 被消费**（2026-09-28，迁移 `4e7759c33526`）：消费者 = `policies.load_expiry_policies` → builder；未配置 ⇒ 并存，默认保守
### B2：读侧 + 收口（✅ 2026-09-28）

- [x] **Cypher 默认视图 + as-of 查询**（2026-09-28）：`graphs.py` 新增 `_temporal_view`（唯一判据）+ `validate_as_of`，接入概览 / 实体详情 / 全实体子图 / **共享法人 / 共享地址**五条链；`as_of` 透传到 `fetch_*` 签名
- [x] **L0 第三项答案模板**（2026-09-28）：新增 `prompts/kg_qa_v3.md`（**v1 / v2 零改动**；v2 是 Sprint 6 批次 B 的 chunk 引用回查版，曾被误覆盖后已按 HEAD 逐字节恢复），`{{as_of_date}}` 取自 `documents.document_date` —— **这也让批次 A 落的那列有了真实消费点**；不可得时字面量 `unknown`，不许让 LLM 编
- [x] **PoC 迁入正式测试集**（CP-T2 强制项）：`tests/test_temporal_track_s.py` 承载原 `run_track_s.py` 判分口径，不调 LLM、默认零外部依赖、判据重复 3 轮；`temporal_poc/README.md` 顶部已注明「判据改动走正式测试集」
- [x] **真机复跑 n=3 达 3/3**：设 `TEMPORAL_TRACK_REAL_URI` 后同一组断言跑三轮真机，当前值=李四 / as-of 2024-06-01=张三 / 历史保留 2 条边活 1 条
- [ ] **as-of 未上 REST**：`as_of` 目前是服务层参数（无 API 入口）。是否进契约要连前端 UI 一起设计，按铁律「暂无法匹配的功能先预留空位」，**不**先造没有 UI 的参数；谁能用现在由内部调用决定

## 批次 C（⏳ 后续）

## 待办（批次 A 真机发现 → 已由 R2 覆盖）

- [x] 模型会**自行**给出 `valid_to`（变更句场景，张三边 `valid_to=2025-05-01`）。
      R2 已按「原文最后出现的 tail」独立判定，**不依赖模型的 `valid_to`**——
      模型给不给都一样，这正是 D-3「不依赖 LLM」要的性质。

## 降级登记（批次 B 实测发现，不得含糊）

- [ ] **通用 `[:RELATION]` 层暂无跨文档仲裁**：`:Entity` 的 id 是 `ent_<uuid>`（每次抽取都变），
      两份文档里的同一家公司是两个节点 ⇒ `(head, relation_type)` 无从匹配。
      需先有**实体消解**（S9 已排）。本期仲裁只对 **M4 主体层**（`sha256(name)` 稳定 id）生效。
