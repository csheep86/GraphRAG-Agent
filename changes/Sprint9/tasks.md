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

- [ ] 四字段落 Neo4j 关系属性（事实维来自抽取，**摄入维 / 血缘由写入侧打**）
- [ ] R1 跨文档（严格晚于 ⇒ 封旧边）/ R2 同文档变更句（同 `valid_from` 取原文最晚 `tail`）/ R3 禁同批次互封 / R4 不猜值（代码侧：不得回填 `valid_to`）
- [ ] `relation_expiry_policies` 落表 + 被仲裁消费（`(org_id, relation_type)` 键，`unknown` 兜底）
- [ ] Cypher 概览 / 子图 / 问答三条链默认过滤 `valid_to IS NULL`；as-of 查询
- [ ] **L0 第三项**：答案模板加「依据截至 X 日的披露文件」（新 `kg_qa_vN.md`）
- [ ] **PoC 迁入正式测试集**：`temporal_poc/run_track_s.py` 的逻辑迁到 `backend/tests/`（CP-T2 强制项），用本项目真实的仲裁接口跑，而不是在临时目录里自证；迁完 `temporal_poc/` 仅留 README 指向新位置
- [ ] 真机复跑 n≥3，判据：当前值正确 3/3、as-of 回溯 3/3、过期治理 3/3（**PoC 迁入后才有资格宣称**）

## 待办（本次真机发现，批次 B 处理）

- [ ] 模型会**自行**给出 `valid_to`（变更句场景，实测第 3 条：张三边 `valid_to=2025-05-01`）。
      这属"文本明示"、不违反 R4，但 **R2 仍必须存在**：模型并非每次都给，
      当两条同 `relation_type` 的旧值边都没被模型封口时，只能靠规则兜底 ⇒
      仲裁结论**不得**依赖模型输出。
