# P7-F · TBD-7 阈值回填（C3 从 provisional 转 MEASURED）

> **日期**：2026-10-13 ｜ **来源**：[`docs/release-readiness-audit-2026-10-13.md`](../../docs/release-readiness-audit-2026-10-13.md) §3 A3
> **一句话**：把**你已裁决的** TBD-7 阈值落进配置与文档，让 C3-a 不再只是 `PASS(provisional)`。
> ⚠️ **本批的阈值来源是用户裁决，不是脚本算出来的**（纪律：AI 不得代填）。

## 1. 起点与坐标

| 项 | 坐标 |
|---|---|
| 阈值本体 | `backend/app/core/config.py:302` `EVAL_SINGLE_DOC_TOKEN_CEILING = 32000`（标记 `provisional`） |
| 模板同步点 | `backend/.env.example:328` |
| 消费者 | `backend/app/evaluation/runner.py:805` / `:825` |
| 实测真值 | C3-a = **7574.0000 token/doc**、C3-b = **0.2727**（`backend/reports/eval/eval-live-20261012T065005Z.json`） |
| `--calibrate` 建议值 | **9100**（P90×1.2）—— ⚠️ **已被否**：n=1、文档仅 1019 字，代表性不足 |
| 锚点断言 | `backend/tests/test_eval_acceptance_cli.py:76-78,125-126,52` |
| 决策权属 | `changes/P6-V5/tasks.md:52`（「D2 未由 AI 代填」是**刻意**的，不是遗漏） |

## 2. 做什么（**严格三步，不许跳步**）

1. 读取用户输入：`ceiling = <你裁决的值>` + 一句话理由（写进集成日志决策表）。
2. 改 `config.py:302` + `.env.example:328`，**只改这一个值**，并把 `threshold_source` 由 `provisional` 改为 `decided`（若字段名不同，先据实登记再改）。
3. 回写 `docs/acceptance-traceability-matrix.md` 的 C3-a / C3-b 行（`:205` / `:206`）与审计文档 §2.2。

## 3. Non-goals（**改一条都要先回来登记理由**）

1. **不替用户选值**——"先写上再复核"也不行（历史纪律）。
2. **不再跑一次 `--calibrate` 去"优化"数值**。
3. **不动 C3-b 的同量纲裁决**（图元素个数，P6-V3 已定）与「`0.0` 语义」。
4. **不做 `stage` 切片契约变更 / 仪表盘改造**（P6-V3 §6.3 遗留，属契约变更）。
5. **不新建全量重建入口**（会撞 `incremental.py:16-18` 护栏）。
6. **不做交付动作**（P6-X / release notes / tag 一律不碰）。

## 4. 出口判据

1. `ceiling` 值 = 用户裁决值，且集成日志里**有裁决人 + 理由 + 日期**。
2. `pytest` 不降（尤其 `test_eval_acceptance_cli.py` 三条锚点）。
3. 矩阵 C3-a / C3-b 行状态由 `PASS(provisional)` 改为 MEASURED，且与 `--live` 读数一致。
4. 三件套 + CI 四 job 全绿。

## 5. 升级用户的四种情况

1. **用户未裁决** ⇒ 本批不得开工（这是唯一的"没输入就停"的情形）。
2. 裁决值会让现有长文档一处直接判红 ⇒ 报告受影响范围，**不许先改判据让它绿**（纪律 R-10）。
3. 需要连同 F4 熔断一起评估 ⇒ 停下升级 F4 议题。
4. CI 红且复核两遍仍红 ⇒ 带 job 名 + 失败行 + 归因。
