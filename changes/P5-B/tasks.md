# P5-B 任务清单

> 来源：[`proposal.md`](./proposal.md)　Non-goals **10 条**（S1 会读它）
> 每段收尾跑：`cd backend && uv run python scripts/check_session_drift.py`

## T1 — J3 判定函数（前端 A）

- [x] `frontend/src/lib/reasoning.ts`：新增 `todayISO()` + `isHopExpired(validTo, today)`
- [x] 口径与后端 `reasoning.py:545-546` 同构（纯字符串比较，字典序 == 日期序），**不为前端重写过滤条件**（D1）

## T2 — J3 渲染（前端 A）

- [x] `frontend/src/components/qa/reasoning-path.tsx`：过期跳 ⇒ 卡片 `border-dashed` + 置灰 + 「已失效」标签
- [x] 不碰 `attribution-panel` / `evidence-panel` 的空状态卡片边框（D2）
- [x] `npm run typecheck` / `build` / `lint` 三条 exit 0
- [x] `npm run gen:api` 后 `git diff --stat` 为空（Non-goal 1）

## T3 — 演示图谱恢复（后端 B）

- [x] PG 建库（`graphrag`）+ public schema 授权 + 迁移到 head（11 个）+ RLS 14 表
- [x] `seed_attendance_ontology.py`（13 实体类 / 14 关系类）
- [x] `ingest_attendance_csv.py`（先于制度脚本，共用 `attendance-demo-v1`）
- [x] `ingest_attendance_policies.py`（6 份 docx + `_bridge_window.py`）
- [x] Entity 2855 / Relation 3643、`kg_versions.status=ready`、`verify_and_close` **四项全 OK**
- [x] ⚠️ 登记差异：`valid_to` 非空 30 vs J1 基线 69（成因未追，见日志 §3.3）

## T4 — G3 受控题集回归（后端 B）

- [x] 起后端（`uvicorn :8002`）；补齐 dev License 后才不是 403
- [x] `local_embedding_server.py :8009`（基线侧 embedding）
- [x] `eval_controlled_qset.py`：引用覆盖率 100% / 拒答口径不符 0 / PASS
- [x] `eval_acceptance.py --live --criteria c1_graph_gain`：**C1 = 0.1765**（graph 1.000 / baseline 0.850 / L2 / pool 213）
- [x] ⚠️ 登记：P6-H 的 0.0294 不可直接比（判分表已被 P6-I 改写，见日志 §4.4）

## T5 — D4 收口

- [x] `pytest`：补 env 后 **1006 passed / 4 skipped / 2 failed** = §8 本地基线逐位一致
- [x] `check_seams.py` ERROR 0 / WARN 0 / OK 12、`export_openapi.py --check` 零 diff
- [x] `ruff check` / `ruff format --check` 均过；`check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0
- [x] 写 `changes/P5-B/integration-log.md`（含 §6 环境债台账 + 下一批指针）
- [ ] CI 四 job 全绿，run id 回登 `integration-log.md`（R-10：CI 才是终裁）
