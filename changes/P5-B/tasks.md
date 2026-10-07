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

- [ ] PG 建库 + 迁移
- [ ] `seed_attendance_ontology.py`
- [ ] `ingest_attendance_csv.py`（先于制度脚本，共用 `attendance-demo-v1`）
- [ ] `ingest_attendance_policies.py`（6 份 docx + `_bridge_window.py`）
- [ ] `Entity` / `Relation` 计数 > 0、`kg_versions.status=ready`、`verify_and_close` 四项 `[OK]`

## T4 — G3 受控题集回归（后端 B）

- [ ] 起后端（默认 `http://127.0.0.1:8002`）
- [ ] `eval_controlled_qset.py`（`QSET_VERSION=v4-2026-10-05`、`QSET_KG_VERSION=attendance-demo-v1`、40 题）
- [ ] 比对 P6-H 基线 C1 0.0294 / graph 0.875 / baseline 0.850

## T5 — D4 收口

- [ ] `pytest` 不降（CI 口径 1007 passed / 5 skipped / 0 failed）
- [ ] `check_seams.py` ERROR 0、`export_openapi.py --check` 零 diff
- [ ] `check_startup_readiness.py` 仍 `[OK]` 17 / `[~~]` 0 / `[--]` 0
- [ ] CI 四 job 全绿，run id 回登 `integration-log.md`
- [ ] 写 `changes/P5-B/integration-log.md`（含下一批必读指针）
