# P5-G · 任务拆解

> **边界**：[`proposal.md`](./proposal.md) §3（11 条 Non-goals）
> **执行模式**：无人值守，逐任务验证通过即提交

---

## T1 · 服务层 `backend/app/services/kg/correction.py`（新增）

- [ ] `merge_entities()` / `split_entity()` / `rename_entity()` 三个公开入口
- [ ] 共用编排 `_run_action()`：**读 active 版本** → **probe 作用域**（缺失 404 / 跨 org 403）
      → **落 `ontology_actions`（拿 `action_id`）** → **调 `rebuild_incrementally`**
      → **在新版本上施加校正变换**（P5G-1）→ 回填
- [ ] `merge`：右侧属性并入左侧（`aliases` 吸收右名 + 右别名、`confidence` 取 max），
      右侧关系按**原方向**重挂到左侧，右节点 `DETACH DELETE`（P5G-4）
- [ ] `split`：N 个新节点 + 「**默认同名**」关系迁移 + 原节点 `status='split'`（P5G-3）
- [ ] `rename`：`canonical_name` 改新名，旧名入 `aliases`（沿用 M2 §4.3）
- [ ] `merge` 后把 `entity_merge_candidates` 对应行置 `applied`（真 PG 写回）
- [ ] 增量重算 `status != "ready"` ⇒ 抛 `OntologyCorrectionError(result.error_code)`，**不**回落全量（Non-goal 9）
- [ ] 新版本 `source_doc_ids` 留空并登记（P5G-2）
- [ ] Neo4j 不可用 ⇒ `NOT_IMPLEMENTED`（**在任何写入之前**，不产生图变更）

## T2 · 路由接线 `backend/app/api/v1/routes/ontology.py`

- [ ] 三端点替换为真实现：调服务层 + 错误映射（路由层**不写** Cypher）
- [ ] 三端点挂 `dependencies=[require_permission(RESOURCE_ONTOLOGY, ACTION_WRITE)]`
- [ ] 删 `_placeholder` / `_BLOCKED_BY` / `_SPEC` 与 `PLACEHOLDER_NOT_IMPLEMENTED` 导入（已无消费点）
- [ ] `summary` / `description` / `responses` 去掉「占位骨架 / 501 未实现」措辞，换成真错误语义
- [ ] 模块 docstring 同步（不再写「merge / split / rename 仍是 501 占位」）

## T3 · RBAC 登记 `backend/tests/test_rbac.py`

- [ ] `PROTECTED_ENDPOINTS` +3 ⇒ **9 条**（`/ontology/merge` / `/split` / `/rename`，均 POST）
- [ ] 参数化拒绝用例**自动**覆盖（不改断言，只加登记）
- [ ] `tests/test_ontology_placeholder_endpoints.py`：三行从 `PLACEHOLDERS` **移走**（不删行）
- [ ] 反向守卫改为「不是**占位形态**的 501」（靠 `detail.blocked_by` 是否含 `P5-M6` 区分，
      F3 裁决既有口径）—— 真实现在 Neo4j 不可达时同样 501，那是基础设施口径

## T4 · 测试（新文件 `backend/tests/test_ontology_correction_actions.py`）

- [ ] 真 Neo4j 夹具 + 真 PG 夹具（基线 ready 版本 + 候选行 `human_review`）
- [ ] 判据 1 / 2：三端点各一条 200；**断言图里的节点 / 属性**，不是响应体
- [ ] 判据 3：`result_kg_version` 非空（PG 读回）+ `kg_versions` 新增 `ready` 行
- [ ] 判据 4：候选行 `human_review` → `applied`（PG 读回）
- [ ] 判据 6：RBAC 拒绝（由 T3 的参数化用例覆盖）
- [ ] 判据 7：跨 org ⇒ 403 且**图零变更**
- [ ] 判据 8：注入增量重算失败 ⇒ 明确错误 + `error_code` 落库 + `result_kg_version` NULL + 旧版本节点数不变
- [ ] 判据 9：P5F-4 显式断言「以新版本读图 ⇒ 只看到被校正节点」
- [ ] 判据 5：M2 spec 升版（架构师帽，单独提交）

## T5 · 升版 `specs/m2-extract-kg.md`（**架构师**角色）

- [ ] §4.5 注脚 `:132-136`：口径由「M6 前向预留、本阶段不实现」改为「M6 已落地」
- [ ] §3 验收 3 `:48` 末句注：补「M6 merge 后置 `applied`」
- [ ] **不重排编号**（`dev-doc-status.md` R5）

## T6 · 门禁与收口

- [ ] **D6 契约同步五步**：`export_openapi.py`（重导）→ `npm run gen:api` → 提交两生成物 → CI 零漂移
- [ ] `export_openapi.py --check` 零 diff、**26 路径不变**
- [ ] `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0
- [ ] `check_seams.py` 仍 ERROR 0 / WARN 0 / OK 12
- [ ] `ruff check` + `ruff format --check`
- [ ] `check_session_drift.py`（S1 读到 11 条；S3 预期无事；**S5 不该命中**）
- [ ] 矩阵 M6 模块行同步（三端点已接线 + P5F-4 缺口）
- [ ] integration-log 撰写（含 §2.2 三条不适用步骤的逐条说明）+ 提交推送 + CI 四 job 全绿
