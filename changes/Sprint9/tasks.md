# Sprint 9 任务卡

> **✅ 2026-09-29 收尾**：批次 **A / B1 / B2 / C1 / C2 / C3 全部完成** ⇒ Sprint 9 **功能达标**
> （较计划区间 11-11→12-01 提前 43 天）。release notes **[`docs/release-notes/v1.5.0.md`](../../docs/release-notes/v1.5.0.md)**；
> `sprint-calendar.md` §5 S9 行转 ✅（`dev-doc-status.md` 已登记）。
> **仍显式未做（不伪装）**：① `as_of` **未上 REST**（批次 B 唯一遗留，等 UI 入口）；
> ② **M4 验收 6 场景准入**未过 → **S13**；③ 通用 `[:RELATION]` 层无跨文档仲裁 → **S9.13-2**。
> **收尾动作留口**：bump `app_version` 1.4.2 → 1.5.0 与 tag `v1.5.0` **待用户确认**（不可逆）。
>
> 批次 C1 / C2 / C3 的过程记录分别在 `changes/archive/2026-09-29-Sprint9.11` / `Sprint9.12` / `Sprint9.13`。

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

> **✅ 2026-09-29 已做（只读）**：结论落 [`c0-recon.md`](./c0-recon.md)——五条待办全部核实，
> 另记 4 条新发现（D-1 演示域≠四源域 / D-2 疑点类型常量 / D-3 三类算法判据须先定 / D-4 待真机核实 `:Subject` 节点数）
> 与 3 项 ⚠️ 待裁决（税号真源 / `unaligned_subjects` 读端点 / `applied` 契约侧空转）。**开工前先读它，别重跑下面的检索。**

- [x] `specs/m4-affiliation-detection.md` §4.3–4.5：三张表 + 四源主体对齐口径
- [x] CSV 摄入链入口：四源**原本没有入口**（唯一 CSV 摄入是考勤域的
      `ingest_attendance_csv.py`）⇒ 已在 **S9.11 批次 C1** 新建 `scripts/ingest_affiliation_sources.py`
- [x] `unaligned_subjects`：原「已建表且零写入」**已偿还（S9.11）**——写入方就位、
      真机落 4 行（见 `../archive/2026-09-29-Sprint9.11/integration-log.md`）。登记号 **S7.2-1** 在
      `backend/CODEBUDDY.md` 与 `specs/m4` §6 两处均已标"已偿还"
- [x] `entity_merge_candidates`：**表不存在**已核实（仍归 **C3**）；
      定义见 `specs/m2-extract-kg.md` §4.5，阈值 **≥0.90 自动合并 / 0.70–0.90 人工队列 / <0.70 独立**；登记号 **S6.2-2**
- [x] **待裁决口径已裁决（S9.11 proposal §2 D-C）**：`applied` = **C3 建表当日加 Pydantic 枚举、
      运行时不写该值、契约侧零改动**。理由（C0 实测）：`contracts/openapi.yaml` 里 `merge` 零命中 ⇒
      该表无契约落点，`export_openapi.py --check` 本来就**应该**无 diff；不为"走出 diff"而造端点。

### C1 R14：CSV 四源字段 schema 冻结（**纪律：冻结后才写算法**）

> 出处 `docs/v1.1.0-demo-mvp-plan.md` §20 **R14**：四源列名 / 必填 / 校验规则**先冻结并落契约**，
> 字段缺失走 `unaligned_subjects` 记录，**不得静默丢弃**。

> ✅ **2026-09-29 已完成（S9.11 批次 C1）**：冻结清单落 `specs/m4-affiliation-detection.md` **§4.6**
> （三张 CSV 的列名 / 必填 / 校验 / 三级对齐口径 / `reason` 三值 / 图模型落点）。
> 契约**零改动**（本批次不新增端点与字段），故后两条落契约动作**不适用**——
> 不是漏做，是"没有要落的契约变更"；`export_openapi.py --check` 实测无 diff。

- [x] 列名 / 必填 / 校验规则的冻结清单 ⇒ `specs/m4-affiliation-detection.md` **§4.6**
- [x] 落契约：本批次**无契约变更**（`--check` 无 diff；前端 `gen:api` 无 diff）

### C2 四源对齐 + 三类图算法（承接 M4）

- [x] 四源主体对齐（写 `unaligned_subjects`，对应 S7.2-1）——**S9.11 已做**，
      对齐率 86/90 = 0.9556（≥ 0.95）；真机 4 行未对齐带 `reason`
- [x] 三类算法：**共享电话 / 环路检测（2..4）** + **三方金额不一致** —— **S9.12 已做**
      （判据先冻结于 spec **§4.7**，真机产出 **9 条**：法人 1 / 地址 1 / 电话 1 / 环 3 / 金额 3，
      与植入 9 组一一对应、误报 0；证据见 `../archive/2026-09-29-Sprint9.12/integration-log.md`）
- [x] 每写一张表 / 加一列 ⇒ **必须带 Alembic 迁移**（`test_migrations_baseline.py` 会把忘写变 CI 红）
      —— 本次：`9c1b7d2ae4f3`（`affiliation_suspicions.details` 列 + 类型约束放宽到 6 类）

### C3 实体消解（`entity_merge_candidates`）

> ✅ **2026-09-29 完成（S9.13）**。判据**先冻结**于 `specs/m2-extract-kg.md` **§4.5.1**
> （范围 / blocking / 信号 / 三条否决 / 三档 / 真机判据），冻结后才写代码——
> 与 C1 / C2 同一条纪律。证据：`../archive/2026-09-29-Sprint9.13/integration-log.md`。

- [x] 判据冻结（§4.5.1）+ 八条裁决 D-A ~ D-H（`../archive/2026-09-29-Sprint9.13/proposal.md` §2）
- [x] 建表 + 迁移（逐字段对齐 `m2 spec` §4.5；迁移 `b3e5a1c70d42`）
      —— **偏离登记 S9.13-1**：`left/right_entity_id` 为 **TEXT** 而非 UUID
      （图侧实体 id 是稳定字符串，**没有 UUID 可存**；理由写在 spec §4.5 表下）
- [x] 相似度算法与阈值按 §3 验收 3（纯函数 `app/services/kg/entity_resolution.py`，零 LLM）：
      真机 **5 条候选** = `auto_merged` 1 / `human_review` 4，**误并 0**，终态对齐率 **87/90**
- [x] 偿还 **S6.2-2**（`specs/m2` §6）；剩余两项显式登记为 **S9.13-2**：
      ① `human_review` **无读端点**（同 S9.11 裁决 D-B）；② `:Entity` **通用层消解未做**
      （id = `ent_<uuid>` 每次抽取都变 ⇒ 无从配对，需先解决跨文档 id 稳定性）
- [x] 关键路径节点已解除（`v2.0.0-ship-backward-plan` §4 / §8：S9 实体消解是 **S12** 的前置）
      —— **S12 开工的硬闸门不再是"消解没做"，而是 M6 校正 GUI 是否接得上候选表**

### 交接时的其他欠账（**来自注意力检查，未动手**）

- [x] **四个 MVP 目录标注（2026-09-29 已做，且核实**推翻**了原结论的一半）**：
      原结论"均已转正进 `backend/app/`、目录里没有说明"——**"已转正可忽略"这部分不实**。
      实测引用关系（grep 得出）：`backend/scripts/import_to_neo4j.py:56` 默认输入
      = `bridge_web_demo/output.json`；`backend/app/services/parsing/mineru.py`、
      `parsing/page_index.py`、`extraction/langextract.py` 均写明"对齐 xxx_mvp 实测口径"；
      `backend/tests/` 三个测试直接引用这两个路径（产物未入库 ⇒ CI 上 skip）；
      链路 `mineru_mvp → bridge_web_demo → langchain_mvp`（`kg_tools.py:32`）。
      ⇒ **不能标"废弃"**，那样会诱导人删掉 `import_to_neo4j` 的默认数据源。
      **处置**：`README.md` 四行描述补全 + 表格后加一段「谁在消费它」引用表与警示；
      另补 `demo/` 行（**活跃**演示语料，与 MVP 性质不同，勿混为一谈）。
      **教训（与 `tests/` 那条同源）**：目录名给人的印象（"像 MVP 遗留"）不是证据，
      grep 出来的引用才是。两次都是先核实才避开了写入假声明。
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
