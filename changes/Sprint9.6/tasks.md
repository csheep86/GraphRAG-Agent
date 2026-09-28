# Sprint 9.6 任务卡

- [x] **G1 入图器 GOVERNED_BY 汇合**（2026-09-28：单测 +8，全量 506 passed）
  - `fetch_policy_context(session, kg_version)`：读 `POLICY_CLAUSE` + 其 MENTIONS chunk 文本
  - `build_governed_by_relations(wts_names, policy_context)`：Python 确定性包含匹配，产出边行
  - 并入 `relation_rows`（复用自检 / 回滚）；count=0 时 FAIL（连通失败不得静默）
  - 单测 `tests/test_ingest_governed_by.py` ✅ 8 条全过
- [x] **G2 重建图 + 真机验证**（2026-09-28：GOVERNED_BY 80 条 / 3 跳链落条款 / 彩排全绿）
  - `ingest_attendance_csv.py --purge-csv`（同 `attendance-demo-v1`）✅ 3576 关系 / active
  - `verify_cases` 新增：E002 李静 → POSITION → WORK_TIME_SYSTEM → POLICY_CLAUSE 3 跳可达 ✅ 27 条
  - 真机 `/agent/query`：推理链终点 = POLICY_CLAUSE「加班规定」✅（顺带修 `_CYPHER_PATHS` LIMIT 截断缺陷）
  - 彩排 `--domain attendance --with-llm` 全绿 ✅
- [x] **G3 合规抽屉制度依据可读化**（2026-09-28：前端回查实体详情，契约不动，lint/tsc 过）
- [x] **G4 文档同步**（R10 已修复 / sprint-calendar S9.6 + v1.9 / integration-log）

## 纪律提醒

- span 噪声（`ent_*` 的 WORK_TIME_SYSTEM）**不得**出现在任何边的端点；
- 匹配文本源**只认** `MENTIONS → POLICY_CLAUSE` 的 chunk（CSV chunk 天然被排除）；
- 匹配失败（某工时制 0 条款）**要在输出里可见**，不许静默。
