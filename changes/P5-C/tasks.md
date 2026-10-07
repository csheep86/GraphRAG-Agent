# P5-C · 任务清单（D2 / M6 第一批）

> 边界见 [`proposal.md`](./proposal.md) §3（11 条 Non-goals）。
> 收尾一律跑 `uv run python scripts/check_session_drift.py`，S1 读到那 11 条才算对得上账。
> 实录见 [`integration-log.md`](./integration-log.md)。

## T1 · `ontology_actions` 审计表（spec §4.2） ✅

- [x] `backend/app/db/models.py` 增 `OntologyAction`（表 `ontology_actions`），含 CHECK
      （偏离 **X-2a** / **X-2b**，理由写进 docstring 与
      `ONTOLOGY_ACTION_TYPES` 常量处）
- [x] 迁移 `3f7c1b90ad24_add_ontology_actions_rls_tenant_table.py`：建表 + 索引 +
      **同文件落 RLS**（G-26 的 `*_rls_*.py` glob 会拿它的 `TENANT_TABLES` 参加并集核对）
- [x] `uv run alembic upgrade head` 在本机真跑；`test_g26_*` + `test_upgrade_head_matches_metadata`
      = 31 passed

## T2 · `GET /ontology/active` ✅

- [x] 接线 `load_active_ontology`；无 active ⇒ 409 `SCHEMA_VERSION_NOT_ACTIVE`
      （**不**静默返回默认 schema）
- [x] 真机（本地 demo 库）返回 `version=1 / status=active / 13 实体 + 14 关系`

## T3 · `POST /ontology/cold-start` → `POST /ontology/confirm` ✅

- [x] cold-start 调 `suggest_ontology_types`（**不写库**，沿用既有的结构保证）
- [x] confirm 写 `ontology_schemas(status='active')`：旧 active 行置 `superseded`；
      同一 `version` 已存在 ⇒ 409
- [x] 同一事务写一行 `ontology_actions(action_type='confirm')`（`kg_version` 恒 NULL，X-2b）
- [x] 解析失败（`OntologySuggestError`）⇒ 500 `INTERNAL_ERROR` + detail，不静默回落

## T4 · RBAC ✅

- [x] 三个已实现端点挂 `require_permission(RESOURCE_ONTOLOGY, read|write)`
      （**不挂** ⇒ 写端点对租户内任意主体开放，属本批自造越权面）
- [x] 同步 `tests/test_rbac.py::PROTECTED_ENDPOINTS` ⇒ 自动多出 5 条拒绝用例

## T5 · 测试改写 ✅

- [x] `test_ontology_placeholder_endpoints.py`：4 个未实现端点保留 501 断言；
      3 个已实现的移出占位清单，换成真行为断言 + 一条「不许退回 501」反向守卫
- [x] 新增 `tests/test_ontology_confirm_flow.py`（10 条）：冷启动不写库 / 解析失败报错 /
      无 active 409 / confirm→active 且落审计 / 重复确认 409 / 换域 supersede /
      跨租户不可见 / 401 ×3

## T6 · 收口 ⏳（**只差 CI**）

- [x] 三条门禁 + pytest（本地口径需补 `GRAPH_REAL_NEO4J_*`）+ ruff 两件套全跑：
      护栏 `[OK]` 17 / `[~~]` 0 / `[--]` 0；接缝 0/0/12；契约零漂移；
      pytest **1019 passed / 4 skipped / 2 failed**（2 failed = 已登记环境债）
- [x] Conventional Commits 分四笔提交（记载/迁移 / 接线 / 测试 / 契约再生）
- [ ] ⏳ **推送**：github.com:443 连不上（已重试 4 次），恢复后 `git push origin main`
- [ ] ⏳ `gh run watch <id> --exit-status` = 0，run id 回登 `integration-log.md` §8.3
- [x] `integration-log.md`：X-2a/b/c 与 **B-1** 偏离登记、D4 的 RBAC 债指针、§11 下一批指针
