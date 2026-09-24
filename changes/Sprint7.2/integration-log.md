# Integration Log: Sprint 7.2 批次 B —— M4 疑点持久化与对外端点

> **状态**：骨架已建（2026-09-24），**待签字后填入真机证据**。
> **填表纪律**（沿用 Sprint7.1）：每条勾选必须有**命令 + 原始输出**；失败 / 不粉饰 / 不编数据；一次.getContext(this) 的值必须与下一次对得上（如 task_id / trace_id）。

## 0. 本文件结构约定

| 章节 | 承载内容 | 对应 tasks.md |
|---|---|---|
| §1 | 基线：`docker ps` / pytest / `check_seams.py` / 当前 `app_version` / 现有 task table | §0 |
| §2 | 事前核实：B1–B7 裁决结论 + SQLite↔PG 类型表达惯例 + 现有 TaskManager 可复用性结论 | §0 |
| §3 | 契约先行：schema → export → gen:api → `CONTRACT_COVERED_PATTERNS` 登记证据 | §1 |
| §4 | 建表：三表 DDL + 索引以 `org_id` 打头 + 迁移输出 | §2 |
| §5 | `risk.detect` 落库 + 任务状态机 + 启动回收 | §3 |
| §6 | 四端点行为（含越权 / 失败 / 400 非法状态迁移） | §4 |
| §7 | 接缝 7 / 8 落地 + `check_seams.py` 转 OK 证据 | §5 |
| §8 | 真机端到端：任务 → 10 条疑点回填 → 状态流转落库 | §7 |
| §9 | 收尾：门禁全绿 + 缺口登记 + 「未擅自处置」声明（是否有超出本批次范围的动作） | §8 |

## 1. 基线（签字后第一时间取）

```
$ docker ps                                   # TODO
$ uv run pytest -q                            # TODO（基线通过数）
$ uv run python scripts/check_seams.py        # TODO（接缝 7 / 8 当前应为 WARN）
$ uv run python scripts/export_openapi.py --check   # TODO（应无 diff）
```

**当前 `app_version`**：`1.2.0`（本批次不 bump）。

## 2. 事前核实结论

| 编号 | 裁决内容 | 结论（**用户 2026-09-24 全部按建议签字**） | 证据 |
|---|---|---|---|
| B1 | 路径口径 `suspicions` vs `suspects` | ✅ **以 spec 的 `/affiliation/suspicions` 为准** | 已同步改 `plan.md:275` / `plan.md:289`；`Sprint7.1/proposal.md:48` 加口径消歧（历史正文不改） |
| B2 | `affiliation_suspicions` 是否加 `task_id` | ✅ **加**（并已补 spec 登记） | `specs/m4-affiliation-detection.md` §4.3 增列 + 文末「字段变更登记」注记（含 JSONB→JSON 降维说明） |
| B3 | 重复 detect 语义 | ✅ **每次新建任务**，幂等由任务承载 | — |
| B4 | `reviewed_by` 来源 | ✅ 取 dev 脚手架 `X-Actor-Id`，不新造 AuthProvider | — |
| B5 | `unaligned_subjects` 只建表不写 | ✅ 只建表，写入点交 S9 批次 D；登记为预期缺口 | — |
| B6 | 接缝 7 / 8 拆 sub-batch | ✅ 排在 B 尾段独立做 | — |
| B7 | 不动自动投递 | ✅ 不动（`risk.detect` 是终点阶段，请求级 `BackgroundTasks` 足够） | §2.2 |
| **B8** | **实施期发现**：`TaskManager.submit()` 硬绑 `document_id`、task_id 恒为 `documents.id` | ✅ **扩展 `submit()` 双分支**（payload 带 `affiliation_task_id` 走新路径），既有三种 task_type 行为不变 | `tasks/manager.py:75-104`；违反点 = ADR-0001 要求 2「业务代码只依赖 TaskManager 接口」 |

### 2.1 spec §4.4 字段核对（**ADR-0001 变更点已执行**）

`specs/m4-affiliation-detection.md:109-111` **已含** `retry_count` / `error_code` / `error_detail` → ADR-0001 §「需变更点」第 2 条**已被执行**，本批次无需再走一次 spec 变更。（2026-09-24 复核）

### 2.2 TaskManager 可复用性结论（B7 技术依据）

TODO（读 `app/tasks/manager.py` / `registry.py` 后写；要点：请求级 `BackgroundTasks` 对「显式触发的终点阶段」足够）

### 2.3 SQLite ↔ PG 类型表达惯例

TODO（查 `documents` 表既有写法，沿用不自创）

## 3. 契约先行（`git diff --stat` 节选）

```
backend/app/schemas/affiliation.py        新建（10 个模型，8 个进契约）
backend/app/schemas/__init__.py           导出新模型
backend/app/api/v1/routes/affiliation.py  新建（四端点）
backend/app/api/v1/router.py              注册 + docstring 同步（8 个 → 列全 14 条）
backend/app/api/v1/responses.py           新增 AFFILIATION_TASK_NOT_FOUND / _SUSPICION_NOT_FOUND
contracts/openapi.yaml                    export_openapi.py 生成（paths 10 → 14）
frontend/src/types/api.d.ts               npm run gen:api 生成
frontend/src/api/client.ts                CONTRACT_COVERED_PATTERNS +4 条
```

```
$ uv run python scripts/export_openapi.py
[OK] 已生成 contracts/openapi.yaml
$ uv run python scripts/export_openapi.py --check
[OK] contracts/openapi.yaml 与后端模型一致
$ uv run pytest -q tests/test_openapi_contract.py
12 passed
```

**一处「教科书式」返样本**：首次导出后 `test_openapi_contract.py` 仍有 2 条失败——
`CORE_PATHS` 与 `operation_id` 数量是**硬编码断言**（10 条），新端点必须在那里登记。
已同步到 14 条并在注释写明由来的 Sprint（这是「契约演进必须显式登记」的机械判据，不是负担）。

## 4. 建表

```
$ uv run python -c "from app.db.models import ...; init_db(); print(Base.metadata.tables.keys())"
tables ok: ['affiliation_suspicions', 'affiliation_tasks', 'documents', 'external_refs',
            'kg_versions', 'unaligned_subjects']
```

- 三表均 `CheckConstraint` 约束状态/类型/严重度取值，复合索引**一律以 `org_id` 打头**（ADR-0003）；
- `affiliation_suspicions` 另建 `ix_..._org_id_task_id`（B2 的「按批次取」主查询路径）；
- **无 Alembic**：表由 `init_db()` 的 `create_all` 生成（既有机制，`main.py:31`）；
- 复杂列一律跨方言 `JSON`（`doc_ids` / `entities` / `evidence` / `result_summary`），
  UUID 数组元素转字符串——沿用 `kg_versions.source_doc_ids` 的既有写法，**未引入** `postgresql.JSONB` / `ARRAY(UUID)`（会让 SQLite 测试库建表失败）。

## 5. 落库 + 任务状态机

- 新增 `app/services/affiliation.py`（PG 侧读写）；`app/services/kg/affiliation.py` 仍是**纯算法**，未被塞 PG 依赖；
- `app/tasks/registry.py`：`affiliation_detect_executor` + 登记 `EXECUTOR_REGISTRY["affiliation.detect"]`；重试回写 `retry_count`（H8：有列必须有消费者），失败写 `error_code` / `error_detail`（后者**敏感**，只留异常首行）；
- `app/tasks/manager.py`：`submit()` 拆为 `_submit_document` / `_submit_affiliation` 双分支（B8），`recover_orphan_tasks()` 扫两张表，`RecoveryReport` 加 `document_reclaimed` / `affiliation_reclaimed`（分表计数才看得见哪类被回收）。

**无 active kg_version 时的行为**（刻意不静默）：任务置 `failed` + `error_code = KG_VERSION_NOT_ACTIVE`，**不**产出 0 条假装「没有疑点」（ADR-0002 §3.2）。

## 6. 四端点行为自测（12 例）

```
$ uv run pytest -q tests/test_affiliation_endpoints.py
12 passed
```

覆盖：双载体投递 / 启动回收扫两张表 / 202+落库 / 重复提交生成两个任务 / 跨租户文档 403 /
跨租户任务 403 / 任务不存在 404 / 默认取最近 completed 批次 / 空批次 200+null / 复核落 actor / 二次复核 400 / 跨租户复核 403。

## 7. 接缝 7 / 8

```
$ uv run python scripts/check_seams.py
--- 接缝落点到位 ---
  [WARN] 接缝 5 事件出口：表 domain_events 未在 ORM 模型声明  ［未到期：1.3.0］
  [WARN] 接缝 6 数据输出：app/services/export/ 不存在        ［未到期：1.4.0］
汇总：ERROR 0 / WARN 4 / OK 7        ← 批次前为 WARN 6
```

CLI 冒烟（JSON 三条记录，其中 1 条 `object_type=bogus` 故意坏）：

```
$ uv run python -m app.services.external_data.cli --org-id 00000000-...-0001 --file demo_refs.json
[BAD ] 第 3 条 object_type 非法: 'bogus'（应为 ['document', 'entity', 'org']）
[INFO] 可导入 2 条，坏行 1 条
[DRY-RUN] 未写库；加 --apply 才落 external_refs
$ ... --apply        → [ OK ] 写入 2 条，跳过已存在 0 条
$ ... --apply（再跑）→ [ OK ] 写入 0 条，跳过已存在 2 条   ← 幂等，**不**静默覆盖
```

## 8. 真机端到端

```
$ uv run python ../changes/Sprint7.2/e2e_detect.py --org 00000000-0000-4000-8000-000000000001 \
      --actor 00000000-0000-4000-8000-0000000000aa
[0] active kg_version = v-s71a-fe1c4dc3 (app_env=development)
[1] POST /affiliation/detect → 202
    task_id = 9be54ebd-fb3a-4c50-b6fc-dc97ec8e3490
[2] GET /affiliation/tasks/{id} → status=completed
    result_summary = {'total': 10, 'by_type': {'shared_legal_rep': 1, 'shared_address': 9},
                      'top_5_severity': ['medium', 'medium', 'medium', 'medium', 'medium']}
    error_code = None
[3] GET /affiliation/suspicions → 200   task_id=9be54ebd-... total=10
    - shared_legal_rep / medium / 招商局集团有限公司 & 招商局轮船有限公司 (evidence=6)
    - shared_address / medium / 旺景置业有限公司 & 中国经贸船务(香港)有限公司 (evidence=4)
    …（其余 8 条略，见日志）…
    无证据疑点数 = 0（必须为 0）
[4] PATCH /affiliation/suspicions/{id} → 200  → status=confirmed, reviewed_by=...-0000000000aa
[5] confirmed 过滤后条数 = 1
```

**与批次 A 对账**：10 条 = 共享法人 1 + 共享地址 9，**条数与类型分布与 Sprint7.1 §7.3 完全一致**——
既没有重复出条（旧并行边已修 / 边 id 按端点生成），也没有丢条。

```
$ uv run python -c "…校验 trace_id 与批次隔离…"
task.trace_id = f661801d-2b37-4320-b0bf-90383c54d1e5 | status = completed
suspicions = 10
trace_id 一致 = True
org_id 唯一 = True
evidence 最小条数 = 3
其它任务疑点数 = 0 (不得串批次)
```

## 9. 收尾

```
$ uv run pytest -q           → 364 passed（批次前 352）
$ uv run ruff check .        → All checks passed!
$ uv run ruff format .       → 100 files left unchanged
$ uv run python scripts/check_seams.py → ERROR 0 / WARN 4 / OK 7
settings.app_version         → 仍 1.2.0（**未 bump**）
本批次新增 settings.* 配置项 → 0 个
```

**无擅自处置声明**：本批次只做 `plan.md` §6.2 批次 B 范围内的事 + 决策 B1–B8 明确列出的动作。
唯一「计划外」的是 **B8**（`TaskManager` 双载体）——它是实施期发现的既有阻塞，已登记进
`proposal.md` 决策点表并经用户签字，**未**静默绕过。路径口径冲突（B1）已在 §2 裁决表登记，历史批次正文**未**被改写（只加消歧注记）。<｜hy_place▁holder▁no▁813｜><arg_key:opensource>old_str</arg_key:opensource><arg_value:opensource>## 3–9. 待实施后填充
