# Tasks: 知识时效改造（L0 + L1）

> **状态**：⏳ 待开工（S9 首日启用）。**勾选 ≠ 通过**，每项须有实测证据落同目录 `integration-log.md`。
> **分工**：`docs/v1.1.0-demo-mvp-plan.md` §16 是 Sprint 级范围；本文件是批次级拆解（"今天勾哪一项"）。
> **判据原型**：`temporal_poc/`（`corpus.py` / `run_track_s.py`）⇒ 迁入 `backend/tests/`，**n ≥ 3 要求 3/3**。

---

## 批次 A · schema 冻结（**S9 首日，硬闸门 CP-T1**）

> 不冻结即返工：四源对齐做完再补时间字段 = 全链路重做。

- [ ] A1 冻结四源节点 / 边 schema（`specs/m2` §4.1 / §4.2）
- [ ] A2 冻结时态四字段 + 血缘：`valid_from` / `valid_to` / `created_at` / `expired_at` / `source_document_id`（**ADR-0005 §4**）
- [ ] A3 冻结 `Document.document_date`（nullable；取不到置 `NULL`，**禁止猜测**）
- [ ] A4 冻结 `relation_type → 有效期策略` 表（初稿：`volatile` = `LEGAL_REP` / `REGISTERED_AT` / `AFFILIATED_WITH` / `OPERATES_SEGMENT`；`stable` = `PARTY_TO` / `HAS_FINANCIAL_INDICATOR`）
- [ ] A5 **核实 `Document` 响应 schema 是否在契约内** ⇒ 决定"进契约走同步 5 步"还是"只落库不进契约"（proposal Impact 第 1 条，**不许臆断**）
- [ ] A6 回写 `specs/m2-extract-kg.md` §4.1 / §4.6（字段口径与冻结值一致）

## 批次 B · L0（文档日期 + 抽取时态字段）

- [ ] B1 `db/models.py`：`Document.document_date` 加列（nullable）
- [ ] B2 新增 `prompts/kg_extraction_v3.md`（**只加** `valid_from` / `valid_to` + few-shot；**v2 文件不得修改**）
- [ ] B3 补单测：`kg_extraction_v2.md` 文件 `git diff` 为空（守 H9）
- [ ] B4 `EXTRACTION_PROMPT_VERSION` 切 v3 + `.env` / `.env.example` 同步
- [ ] B5 抽取侧解析与归一 `valid_from` / `valid_to`（口径复用 `temporal_poc` 的 `_norm_date`：`YYYY-MM-DD` / `YYYY年M月D日` / `YYYY年M月` / `YYYY`，**无法识别返回 `None` 不猜**）
- [ ] B6 实测：`valid_from` **覆盖率 ≥ 0.90**（PoC 基线 1.00）
- [ ] B7 答案模板加「依据截至 X 日的披露文件」（**无日期时不得编造**）

## 批次 C · L1（四字段落库 + 仲裁 + 查询过滤）· 闸门 CP-T2

- [ ] C1 `services/kg/`：关系写入四字段 + 血缘（**M2 仍是图谱层唯一写入入口**，不得旁路）
- [ ] C2 实现 **R1**（跨文档：新 `valid_from` **严格晚于**旧边 ⇒ 封 `valid_to` + 置 `expired_at`）
- [ ] C3 实现 **R2**（同文档变更句：同 `valid_from` ⇒ 保留原文中**最晚出现**的 `tail`）
- [ ] C4 实现 **R3**（**禁止同批次互封**）— 写单测专门守这条（去掉它就重现"当前值全线阵亡"）
- [ ] C5 实现 **R4**（不猜值）— 写单测：无显式日期 ⇒ `valid_from := document_date`、`valid_to := NULL`
- [ ] C6 `services/graphs.py`：概览 / 子图 / 问答**三条链**默认过滤 `valid_to IS NULL`
- [ ] C7 补 as-of 查询：`valid_from <= $d AND (valid_to IS NULL OR valid_to > $d)`
- [ ] C8 `relation_type → 有效期策略` 配置落 `config.py`，**确认有消费点**（无消费者不得提交）
- [ ] C9 **判据脚本迁入** `backend/tests/`（`temporal_poc/corpus.py` + `run_track_s.py` 判分逻辑）
- [ ] C10 跑 **n ≥ 3**，要求 **3/3**：当前值正确 + as-of 回溯正确 + 历史保留（闸门 **CP-T2**）
- [ ] C11 判分**去空格归一**（防"答对判成答错"，见 proposal 开工前必读第 3 条）

## 批次 D · M4 三类算法 + 金额不一致（原 S9 内容，本批次不含时效）

- [ ] D1 连通分量 / 共享邻居 / 环路三类算法（M4 §3 验收 3）
- [ ] D2 三方金额不一致 → `amount_mismatch`，`severity=high`（M4 §3 验收 5）

## 批次 E · 实体消解 + 四源对齐（原 S9 内容）

- [ ] E1 `entity_merge_candidates` 落地（M2 §3 验收 3，缺口 S6.2-2）
- [ ] E2 `unaligned_subjects` 写入（M4 §3 验收 1，缺口 S7.2-1）

---

## 验证（每批次都跑）

- [ ] `uv run ruff check . && uv run ruff format --check .`
- [ ] `uv run pytest -q`（**全绿**，含迁入的时态判据）
- [ ] `uv run python scripts/check_seams.py`（默认档 **ERROR = 0**）
- [ ] `uv run python scripts/export_openapi.py --check`（**零漂移**；若 A5 判定进契约则先重导）
- [ ] `cd frontend && npm run lint && npm run typecheck && npm run gen:api`（无 diff）
- [ ] 时态专项三查：① 旧事实 `valid_to` 被封**且仍可查**；② 「当前有效」查询**返回且仅返回一条**；③ as-of（2024-06-01）→ 旧值、当前 → 新值

## 收尾（Sprint 9）

- [ ] 补 `changes/Sprint9.1/integration-log.md`（实测证据链）
- [ ] 按 `docs/acceptance-traceability-matrix.md` §3.5 逐条对账（验收 8 / 9 / 10）
- [ ] 更新 `docs/dev-doc-status.md`（**P1-6** 状态）+ `docs/sprint-calendar.md` §5 S9 行
- [ ] 更新 `specs/m2-extract-kg.md` §6「已登记的实现缺口」（若有新缺口）
- [ ] `docs/release-notes/v1.5.0.md`
- [ ] tag `v1.5.0` + bump `settings.app_version`（**同一动作**）+ 同步重导契约 `info.version`
- [ ] 归档 `changes/Sprint9.1/` → `changes/archive/<日期>-Sprint9.1/`
- [ ] **L2 转入 S10**（路径时序一致性 + 页面失效视觉语义 + 验收矩阵追加项）
