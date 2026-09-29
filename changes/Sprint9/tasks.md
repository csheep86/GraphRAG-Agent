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

## 批次 C（⏳ 后续｜**交接物**：2026-09-28 上下文切换时补写，供新会话直接上手）

> 这一段**不是计划，是已核的事实清单**。上一轮对话已把批次 A / B / B2 全部完成
> （**CP-T2 达成**，可宣称 L1 完成），并顺手清掉两批"存在但没人跑"的病
> （详见 `integration-log.md` §10.4 与 §11）。批次 C 是**全新的一块**，
> 需要读的文件与 A/B 几乎零交集 ⇒ **建议在此处开新对话**，新会话按本节列的线索开工，
> 不必重新探索。

### C0 勘察（**先别写代码**）

- [ ] `specs/m4-affiliation-detection.md` §4.3–4.5：三张表 + 四源主体对齐口径
- [ ] CSV 摄入链入口：已确证存在 `backend/scripts/ingest_attendance_csv.py`（考勤域）；
      **四源（发票 / 凭证 / 供应商主数据 / 合同）是否另有入口，待查**——别假设同一个文件
- [ ] `unaligned_subjects`：**已建表且零写入**（`backend/app/db/models.py:397`，
      迁移 `00f44b912817`），承接见 `specs/m4-affiliation-detection.md:204` 与
      `backend/CODEBUDDY.md:82`（登记号 **S7.2-1**，两边都已登记，不用再找）
- [ ] `entity_merge_candidates`：**表不存在**（migrations 全库检索无命中）；
      定义见 `specs/m2-extract-kg.md` §4.5，消解阈值 **≥0.90 自动合并 / 0.70–0.90 人工队列 / <0.70 独立**（§3 验收 3）；承接登记号 **S6.2-2**（同文件 `:252`）
- [ ] **待裁决口径（别猜）**：`specs/m2-extract-kg.md` §4.5 注脚写「`applied` 是 M6 前向预留值，
      **Sprint 9 不落该值**」；而 `docs/v2.0.0-ship-backward-plan.md` §5 的 S9 行写
      「已决议 **O-2**：S9 建表当日**一并改 Pydantic 枚举** + `export_openapi.py` + `npm run gen:api`」。
      调和的可能解释是：**"加枚举到代码并同步契约" ≠ "运行时写该值"**——但必须由
      开工者写明裁决，不能默认。

### C1 R14：CSV 四源字段 schema 冻结（**纪律：冻结后才写算法**）

> 出处 `docs/v1.1.0-demo-mvp-plan.md` §20 **R14**：四源列名 / 必填 / 校验规则**先冻结并落契约**，
> 字段缺失走 `unaligned_subjects` 记录，**不得静默丢弃**。

- [ ] 列名 / 必填 / 校验规则的冻结清单（落 `specs/m4-affiliation-detection.md` 或新提案 §1）
- [ ] 落契约：`uv run python scripts/export_openapi.py` 重导 → 提交生成物 →
      `cd frontend && npm run gen:api`（CI 有契约零漂移校验，漏拍即红）

### C2 四源对齐 + 三类图算法（承接 M4）

- [ ] 四源主体对齐（写 `unaligned_subjects`，对应 S7.2-1）
- [ ] 三类算法：**连通分量 / 共享邻居 / 环路检测** + **三方金额不一致**
      （`v1.1.0-demo-mvp-plan` §15.2 映射表：Sprint 7 只做 1 类，S9 补满）
- [ ] 每写一张表 / 加一列 ⇒ **必须带 Alembic 迁移**（`test_migrations_baseline.py` 会把忘写变 CI 红）

### C3 实体消解（`entity_merge_candidates`）

- [ ] 建表 + 迁移（逐字段对齐 `m2 spec` §4.5）
- [ ] 相似度算法与阈值按 §3 验收 3；这是**关键路径上的"一堵全堵"节点**
      （`v2.0.0-ship-backward-plan` §4 / §8：S9 实体消解是 **S12** 的前置）

### 交接时的其他欠账（**来自注意力检查，未动手**）

- [ ] **四个 MVP 目录没有"只读"标注**（**未做，且标注前必须先核实**）：
      `bridge_web_demo` / `mineru_mvp` / `langchain_mvp` / `langextract_mvp`（另有 `demo/`，
      是否同批待查）。来源结论是"均已转正进 `backend/app/`"（细则见
      `integration-log.md` §11.3 表）——**但这是转述，未经本轮核实**。
      ⚠️ **动手前必须逐个核实**是否真的已转正 / 有无代码仍在读这些目录：
      核实不实就写"已转正"标注，等于往仓库里添一条**新的假声明**，
      比不标注更糟（参照下面那条 `tests/` 的教训）。
- [x] **根 `tests/` 空壳（2026-09-29 已处置，且**推翻了"删"的选项**）**：起初判断是垃圾、
      打算删——核实后发现 `docs/03-prd.md:249` 与 `specs/_template/tasks.md:15,23`
      都把它定为**规划落点**，`tests/unit|integration|e2e` 至今仍按此分层下发任务
      ⇒ 删掉等于隐性违背 PRD。**改法**：`README.md` 表格行改为"规划落点 + 当前空壳 +
      实际在 `backend/tests/` + 勿删勿放"，并新增 `tests/README.md` 写明
      `testpaths` 相对 `backend/` 解析 ⇒ 放进去不会被收集。
      **教训**：这条与上一条都说明——**体检报告的结论要回到源头核实再动手**
- [ ] **`as_of` 未上 REST**（批次 B 唯一遗留）：按「暂无法匹配的功能先预留空位」铁律，
      不先造没有 UI 的参数

## 待办（批次 A 真机发现 → 已由 R2 覆盖）

- [x] 模型会**自行**给出 `valid_to`（变更句场景，张三边 `valid_to=2025-05-01`）。
      R2 已按「原文最后出现的 tail」独立判定，**不依赖模型的 `valid_to`**——
      模型给不给都一样，这正是 D-3「不依赖 LLM」要的性质。

## 降级登记（批次 B 实测发现，不得含糊）

- [ ] **通用 `[:RELATION]` 层暂无跨文档仲裁**：`:Entity` 的 id 是 `ent_<uuid>`（每次抽取都变），
      两份文档里的同一家公司是两个节点 ⇒ `(head, relation_type)` 无从匹配。
      需先有**实体消解**（S9 已排）。本期仲裁只对 **M4 主体层**（`sha256(name)` 稳定 id）生效。
