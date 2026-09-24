# Tasks: Sprint 8.3 批次 D —— 演示打磨之 A16：settings 页「演示环境」标注

> **状态**：**实现已改完，门禁（lint / tsc / 真机点验）待跑**——执行时 shell 审批未通过，命令被取消，未跑门禁前不得宣称完成。
> **前置**：批次 A（`cb919ab`，已归档）、批次 B（`36d4c26` + `94113f02`，CI 4/4 绿）均已完成。
> **范围**：proposal 决策 **A16**（settings 页处置）+ 顺手修一条假声明（`nav.ts` 里 `/audit` 的 `placeholder: true`）。
> **边界**：批次 D 另两项——**种子数据集固化**与**演示彩排脚本**——**本轮不做**（见 §6 待裁决）；不动契约、不动后端、不动接缝、不 bump `app_version`。

## 0. 事前核实（未完成不得往后走）

- [x] **核实 A16 原文**（`changes/archive/2026-09-24-Sprint8.1/proposal.md:73`）：settings 页处置 = **加「演示环境」标注**，不选"隐藏路由"；理由：隐藏会让「零假数据」硬门槛**失去可核性**
- [x] **核实 plan §7.1 批次 D 三项**：种子数据集固化 / 演示彩排脚本 / settings 页处置（隐藏路由或加标注）⇒ 本轮只做第三项
- [x] **核实 settings 页现状**：`app/settings/page.tsx` = 纯 `PlaceholderPage`（全站唯一使用该组件）；`lib/nav.ts` 的 `/settings` 标 `placeholder: true`
- [x] **核实契约无 `/settings*` 路径** ⇒ 标注里写"无配置项、无 Mock 数据"是事实，不是粉饰
- [x] **核实演示语料**：`docs/annualreport/` = 招商局系 2025 年度报告 10 份 PDF（标注中写明目录，可核）
- [x] **核实 `/audit` 已非预留位**：批次 A 后是真实页（`GET /api/v1/audit` 进契约），`nav.ts` 仍写 `placeholder: true` ⇒ **假声明**，与 A16「诚实可核」冲突，顺手修（该字段当前无 UI 消费点，改动零风险）

## 1. 实现（A16）

- [x] `components/common/placeholder-page.tsx`：新增 `badge` / `notice` 两个插槽（标题右侧标签位 + 占位卡上方的说明卡），组件注释写明 A16 出处
- [x] `app/settings/page.tsx`：标题右侧「演示环境」`Badge`（`variant="muted"` + `Info` 图标）+ `DemoEnvironmentNotice` 说明卡，四条可核事实：
      ① 契约无 `/settings*` ⇒ 本页无配置项、**也无 Mock 数据**；② 演示语料 `docs/annualreport/`（10 份）；③ 文档/图谱/问答/疑点/审计走真实接口（**多轮会话列表仍 Mock，属已知豁免**）；④ 身份走开发态请求头（`LocalAuthProvider`）+ 限流 60/min（429 `RATE_LIMITED`）
- [x] `lib/nav.ts`：`/audit` 去掉 `placeholder: true`（批次 A 后已是真实页），留注释说明为何改

## 2. 门禁（2026-09-24 已跑，全部通过）

- [x] `npm run lint`（ESLint）→ 无告警，**exit 0**
- [x] `npm run typecheck`（`tsc --noEmit`）→ 无输出，**exit 0**
- [x] `npm run gen:api` → 重生成后 `git diff --stat ... api.d.ts contracts/openapi.yaml` **无输出** ⇒ 契约与类型**零漂移**
- [x] 后端不受影响：`uv run pytest -q` = **387 passed**（与批次 B 后基线一致，本批次未动后端）
- [x] `uv run python scripts/check_seams.py` = **ERROR 0 / WARN 2 / OK 8**；`export_openapi.py --check` → `[OK]` 零漂移

## 3. 真机点验（2026-09-24 已跑，两条路径）

- [x] `NEXT_PUBLIC_USE_MOCK=false` 起 `next dev` → `GET /settings` **HTTP 200**（29,322 B）：HTML 逐字核对 `演示环境 / 功能预留 / 系统设置 / docs/annualreport / LocalAuthProvider / RATE_LIMITED / 多轮会话` **全部 True**
- [x] `USE_MOCK=true`（默认）下同样 **200**，两条文案均可见——本页是 SSR 静态页、零接口调用，与 Mock 开关无关
- [x] 侧栏「系统设置」入口仍存在：`href="/settings"` 在 HTML 中 **True**（**未隐藏路由**，A16 判据）
- [x] 花费：**¥0**（纯前端静态页，不触 LLM / 不触解析）；点验后 dev 进程已停、抓取的 HTML 与日志已删

## 4. 文档（已补）

- [x] 补 `changes/Sprint8.3/integration-log.md`（门禁输出 + 真机点验结论 + 未擅自处置声明）
- [x] `docs/dev-doc-status.md` 补批次 D 登记行（顶部最新一条）

## 5. 收尾（待执行）

- [ ] 提交（用户过目后）→ push → 盯 PR #3 的 CI（push 失败直接重试：本机 GitHub 网络时好时坏，非 DNS）
- [ ] **不** bump `app_version`（仍 1.3.0，Sprint 8 收尾统一 bump 1.4.0 + tag）

## 6. 待用户裁决（本轮未做）

1. **种子数据集固化**（plan §7.1 批次 D 第 1 项）
2. **演示彩排脚本**（第 2 项；`changes/archive/2026-09-24-Sprint8.1/demo_walkthrough.py` 已有走查脚本，是否视为已覆盖需确认）
3. **观察项**：受控问题集 11 问与现语料不同源（A15：如实登记为已知限制）；`graph/overview` 的 `entity_count=0` 排查
