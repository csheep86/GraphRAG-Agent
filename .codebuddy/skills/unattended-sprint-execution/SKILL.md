---
name: unattended-sprint-execution
description: 无人值守执行 Sprint：按 docs/v1.1.0-demo-mvp-plan.md + docs/sprint-calendar.md + CODEBUDDY.md 逐批次推进，默认采纳文档建议项，仅 4 类情况升级用户。适用于计划已定、用户要求"按计划做、需要确认按建议来"的连续开发场景。
---

# 技能名称：unattended-sprint-execution（无人值守 Sprint 执行）

## 用途

在**计划已定稿、用户已预授权**的前提下，无人值守地逐 Sprint / 逐批次执行开发：不向用户索要过程性确认，所有"需要确认"的点一律采纳规范文档中已写明的建议项（降级预案的建议路径 / 默认档 / 既定口径），只在文档明确要求发起人裁决的 4 类情况升级用户。本质是 `executing-plans` 的**预授权变体**，叠加固定的升级边界。

## 触发条件

- 计划真源已存在：`docs/v1.1.0-demo-mvp-plan.md`（v3.0）+ `docs/sprint-calendar.md` + `docs/v2.0.0-ship-backward-plan.md`。
- 用户已声明无人值守授权（"按计划来做，要确认的地方按建议来"或等价表述）。
- 当前处于某个 Sprint / 批次的执行阶段（非探索 / 澄清阶段——那走 `brainstorming`）。

## 执行步骤

1. **定位进度**：读 `docs/sprint-calendar.md` §5 状态列 + `changes/Sprint<N>.<M>/tasks.md`，找到第一个未勾选任务；每轮会话开始时不复述摘要、不请求确认，直接从该任务续跑。
2. **SDD 事前动作**（新批次开工时）：按 `docs/dev-doc-status.md` §9.1 建 `proposal.md` + `tasks.md`（模板 `specs/_template/`），分支 `feature/sprint-<N>`。
3. **执行单任务**：只做当前任务，遵守角色隔离（frontend/ 与 backend/ 分属不同角色）；接口变更走契约先行 5 步（`backend/CODEBUDDY.md` §3），预留字段遵守接缝纪律（ADR-0004 + `check_seams.py`）。
4. **默认采纳建议项**：遇到文档中存在降级预案 / 建议路径 / 默认档的决策点（如 MinerU 不可用 → 手工放置解析产物；chunk 引用不通 → 降级文档级引用；GUI 超时 → API + 简易表单），**直接按建议执行并在 integration-log.md 登记事实**，不停下询问。
5. **立即验证并提交**：任务完成即跑其声明的验证（pytest / ruff / lint / typecheck / `export_openapi.py --check` / `gen:api` 无 diff）；通过后**自动按 Conventional Commits 提交**（本技能授权免请求提交——覆盖 `executing-plans` 步骤 4 的"仅当用户要求提交时"）；失败先修复再继续，修复超 3 轮仍红 → 按第 8 步升级。
6. **勾选并留痕**：勾选 tasks.md 对应项；证据链写 `integration-log.md`（实测命令 + 输出摘要 + 关键发现）。
7. **Sprint 收尾**：按 `docs/dev-doc-status.md` §9.2 顺序执行（含 5a 更新 sprint-calendar §5）；收尾门禁全绿才 bump `settings.app_version` + 打 tag + `merge --no-ff` 回 main + release notes + 归档。
8. **升级边界（仅此 4 类停下找用户，其余一律自主推进）**：
   - **CP-2 PoC 不通**（S11 中段，schema-suggestion 未跑通）——闸门明确要求升级裁决；
   - **F1~F5 任一触发**（准入线实验失败 / 反证条件命中）——须显式降级决议，不得静默；
   - **文档未覆盖的决策**（无建议项可采纳、且不属于日常实现选择）；
   - **上线 gate 终审**（S13 收尾，`docs/acceptance-traceability-matrix.md` 签字项 + MVP 1.0 达成声明）。
9. **偏差处理**：计划与实际不符**且无既定建议项** → 停止并升级（第 8 类）；有建议项 → 按第 4 步执行并登记。

## 输出格式

- 每完成一个任务：一行进度（任务号、结果、验证摘要、commit hash）。
- 每批次收束：批次小结（完成数 / 降级登记数 / 升级数）。
- 触发升级时：**升级报告**（触发类别、文档依据、已尝试动作、可选路径与建议）。
- Sprint 收尾：执行总结 + release notes 路径 + sprint-calendar §5 已更新声明。

## 注意事项

- 本技能**不降低任何验收标准**：提前完成就提前验收，不跳验收（关 Mock 硬门槛、接缝登记、契约零漂移逐条过）。
- 降级必须落 release notes + integration-log，禁止静默降级（`docs/v1.1.0-demo-mvp-plan.md` §15.4）。
- 典型组合：本技能为主循环 → 批次内实现可叠加 `test-driven-development` → 大批次用 `subagent-driven-development` / `dispatching-parallel-agents` 并行 → 每个收尾前过 `verification-before-completion`。
