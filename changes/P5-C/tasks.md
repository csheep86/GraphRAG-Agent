# P5-C · 任务清单（D2 / M6 第一批）

> 边界见 [`proposal.md`](./proposal.md) §3（11 条 Non-goals）。
> 每个任务收尾跑 `uv run python scripts/check_session_drift.py`，S1 必须读到那 11 条。

## T1 · `ontology_actions` 审计表（spec §4.2）

- [ ] `backend/app/db/models.py` 增 `OntologyAction`（表 `ontology_actions`），含 CHECK
      （偏离 **X-2a** / **X-2b**，理由写进 docstring）
- [ ] 新迁移 `backend/migrations/versions/*_rls_*.py`：建表 + 索引 + **同文件落 RLS**
      （G-26 的 `*_rls_*.py` glob 会拿它的 `TENANT_TABLES` 参加并集核对）
- [ ] `uv run alembic upgrade head` 在本机真跑；`test_g26_1` / `test_g26_per_table_policy_present`
      / `test_upgrade_head_matches_metadata` 仍绿

## T2 · `GET /ontology/active`

- [ ] 接线 `load_active_ontology`；无 active ⇒ 409 `SCHEMA_VERSION_NOT_ACTIVE`
      （**不**静默返回默认 schema）

## T3 · `POST /ontology/cold-start` → `POST /ontology/confirm`

- [ ] cold-start 调 `suggest_ontology_types`（**不写库**，复用既有结构保证）
- [ ] confirm 写 `ontology_schemas(status='active')`：旧 active 行置 `superseded`；
      同一 `version` 已存在 ⇒ 409
- [ ] 同一事务写一行 `ontology_actions(action_type='confirm')`
- [ ] 解析失败（`OntologySuggestError`）⇒ 500 `INTERNAL_ERROR` + detail（不静默回落）

## T4 · RBAC

- [ ] 三个已实现端点挂 `require_permission(RESOURCE_ONTOLOGY, READ/WRITE)`
      （不挂 ⇒ 写端点对租户内任意主体开放，属自造越权面）
- [ ] 同步 `tests/test_rbac.py::PROTECTED_ENDPOINTS`（登记后**自动**获得两条拒绝用例）

## T5 · 测试改写

- [ ] `test_ontology_placeholder_endpoints.py`：4 个未实现端点保留 501 断言；3 个已实现的改断言真行为
- [ ] 新增 `tests/test_ontology_confirm_flow.py`：冷启动不写库 / active 409 / confirm→active /
      重复确认 409 / 换域 supersede / 跨租户不可见

## T6 · 收口

- [ ] 三条门禁 + pytest（本地口径需补 `GRAPH_REAL_NEO4J_*`）+ ruff 全跑
- [ ] Conventional Commits 分段提交、推送、`gh run watch --exit-status`
- [ ] `integration-log.md`：含 X-2a/b/c 偏离登记、D4 的 RBAC 债指针、下一批指针
