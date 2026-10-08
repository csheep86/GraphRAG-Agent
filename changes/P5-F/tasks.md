# P5-F · 任务拆解

> **边界**：[`proposal.md`](./proposal.md) §3（11 条 Non-goals）
> **执行模式**：无人值守，逐任务验证通过即提交

---

## T1 · 增量重算服务 `backend/app/services/kg/incremental.py`

- [x] `rebuild_incrementally()`：入参 = `db` / `org_id` / `action_id` / `affected_entity_ids` /
      `source_doc_ids` / `trace_id` / `graph_service` / `batch_size`
- [x] 版本号：`<base>-inc-<suffix>`，同 org 唯一（撞号重生成）
- [x] 状态流转**复用** `KgVersioningService`：`create_pending → mark_building → mark_ready`（P5F-1）
- [x] 图侧**只重写受影响子图**：`:Entity` 节点按 `{id, kg_version}` 幂等键 MERGE 到新版本；
      两端都受影响的关系按 `:RELATION {id, kg_version}` 迁移（沿用 `builder.py:432` 的幂等键口径）
- [x] 分批执行，批大小 = `settings.increment_rebuild_batch_size`（**真实消费者**，D2）
- [x] 应用层 org 过滤：受影响节点必须 `n.org_id = $org_id`，否则 `KG_TENANT_LEAK`（不静默跳过）
- [x] 成功 ⇒ 回填 `ontology_actions.result_kg_version`
- [x] 失败 ⇒ `mark_failed` + 回填 `error_code` / `error_detail`，`result_kg_version` 保持 NULL；
      **不**回落全量重建（Non-goal 9）；日志不输出 `error_detail` 原文（P5-E 脱敏口径）
- [x] 无 active 版本 ⇒ `KG_VERSION_NOT_ACTIVE`

## T2 · 配置 `INCREMENT_REBUILD_BATCH_SIZE` + `.env.example` 同步

- [x] `config.py` 新增 `increment_rebuild_batch_size: int = 100`（挨着既有 KG 配置落成同款）
- [x] `backend/.env.example` 同步（S3 必须不报）
- [x] `check_seams.py` 仍 **ERROR 0 / WARN 0**（新配置在 `app/` 内有真实读取点）

## T3 · 测试（新文件 `backend/tests/test_kg_incremental_rebuild.py`）

- [x] 真 Neo4j 夹具：N=5 个 `:Entity`（同一 org、同一旧版本），其中 M=2 个为「受影响」
- [x] 判据 2：新版本节点数 == M；旧版本节点数前后不变；未受影响节点 `id` / 属性逐条不变；M ≠ N
- [x] 判据 3：PG 读回 `kg_versions` 新增一行，`source_doc_ids` == 受影响文档集（≠ 全量）
- [x] 判据 4：PG 读回 `ontology_actions.result_kg_version` 由 NULL → 新版本号
- [x] 判据 5：注入失败 ⇒ `error_code` / `error_detail` 落库、`result_kg_version` 仍 NULL、
      版本行 `status='failed'`；断言**没有**全量重建迹象（旧版本节点数不变）
- [x] 配置判据：断言**读到的值**（不只断言"设了"）——`extra="ignore"` 陷阱
- [x] 跨 org 实体 ⇒ `KG_TENANT_LEAK`（不静默跳过）
- [x] 既有正向守卫保持绿且**不改为绿而改断言**

## T4 · 门禁与收口

- [x] `export_openapi.py --check` 零 diff、26 路径不变（D6）
- [x] `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0
- [x] `ruff check` + `ruff format --check`
- [x] `check_session_drift.py` 逐条对照（S1 读到 11 条；S3 必须 OK；S5 命中按 P5F-5 登记）
- [x] 矩阵 M6 模块行同步（写明三端点仍占位、P5F-4 待下一批裁决）
- [x] integration-log 撰写 + 提交推送 + CI 四 job 全绿
