# P6-W 开工提示词（写给下一批，2026-10-10 由 P6-V3 落成）

> 队列活版口径：[`docs/delivery-plan.md` §9.2 序 6](../../docs/delivery-plan.md)；
> 上一批收口：[`integration-log.md`](./integration-log.md)

---

## 1. 执行模式（**开工前先做一道闸门判断**）

⚠️ **本批不是拿到就开工的批次**，有两道闸门：

1. **先看 §6 的 W1 取舍**：十项里第 **8 / 9** 项依赖 DR-E2 的备份 / 恢复脚本，
   而它**目前全仓不存在**（已机械查实，见 §5 表）。
   - 未裁决 ⇒ **不许动代码**，先把那张表交给用户裁决（或另行指定），就此收口；
   - 已裁决 ⇒ 按裁决执行。
2. **若下一批实际换成 P6-X（演练留证）**：那是**双人**批次，
   `delivery-plan.md` §9.2 序 7 明写「执行者 ≠ 见证者」「**AI 不能单独收口**」
   ⇒ **必须把本节改写为"人做主体"**，并写死 AI 只能做搬运 / 校验 / 跑命令 / 回登，
   不得代收口。**不要用本节原文去跑 P6-X。**

其纪律照旧：无人值守（默认采纳本文件的建议项，只有 §11 四类情况升级）；
`backend/` 归后端、`specs/` + `contracts/` 归架构师、`frontend/` 本批一行不动。

## 2. 为什么起点是 P6-W（三条**机械**理由）

1. **队列口径**：`delivery-plan.md` §9.2 序 **6** = **DR-E4 安装验收十项脚本化**，
   前置 = P6-V3；P6-V3 已收口（三个提交：`6054f21` / `6d564f8` / `c4f0dc0`，
   见本目录 `integration-log.md` §1）。
2. **它是队列里排在 C3 之后的最近一项**：序 1~5d（P6-R … P6-V3）
   均已落地，`DR-E4` 在 `delivery-requirements-and-guardrails.md:132` 仍标 **⏳ 未做**。
3. **工量不是文档写的那个数**（见 §5）：十项里**至少 5 项已有 CI 机械落点**
   （健康 / License / 租户隔离 / 私有化开关 / 部分端点）⇒ 真正缺的不是"写十个脚本"，
   而是 **DR-E2 的备份 / 恢复能力**（它**零基础**）。⇒ 先判断要不要把它前置。

## 3. 开工自检（先跑，别凭文档下结论）

```bash
cd backend && uv run python scripts/check_startup_readiness.py   # 期望 17/0/0
cd backend && uv run python scripts/check_seams.py               # 期望 ERROR 0 / WARN 0 / OK 12
cd backend && uv run python scripts/export_openapi.py --check     # 期望零 diff
cd backend && uv run python scripts/extract_seam_signatures.py --check  # 期望与快照一致
```

四项都对上才开始。**结论只能来自脚本输出**，不能来自本篇或集成日志的表格。

⚠️ **本地环境的坑（沿用前两批）**：
- 本机测试库是**持久库**，`create_all` 不加列、`alembic upgrade head` 会撞表
  ⇒ 别指望它们补 Schema；
- CI 每次起新 PG 容器 ⇒ CI 才是门禁（**R-10**），本地红不一定等于 CI 红，反之亦然；
- 有图口径要设 `GRAPH_REAL_NEO4J_{URI,USER,PASSWORD}` **三个**变量，
  少设会让一批真图用例**静默 skip**（不是失败）。

## 4. 边界纪律（Non-goals **≥ 8 条**，落 `changes/P6-W/proposal.md`）

1. **AI 不得代填任何 `correct` 值**（A3）——永久红线。
2. **不许为了"十项全绿"改验收判据本身**：要脚本化的是 `deployment-spec.md` §10
   的表，**不是反过来**把表里不合理的地方顺手改掉（要改判据 ⇒ 停下来升级用户）。
3. **不改 rubric / 题集 / 判分**（P6-T 仍 `UNKNOWN`，人是瓶颈）。
4. **不改 `frontend/`**；**不改契约** —— `export_openapi.py --check` 零 diff 为判据
   （含描述文本 ⇒ X-5 仍不在本批）。
5. **不夹带** X-5 契约描述文本、`cost/dashboard` 的 stage 切片、P5H-6 跨版本边
   —— 各自有批次。
6. **不动 P6-V3 的成果**：两侧写入方唯一性、`_graph_elements` 单一换算口、
   `stage` 两档取值；**不许虚构演练 / 备份结果**（没跑就是没跑，不得写"已验证"）。
7. **不许把"在某台机器上跑通过了"当成机器可跑的判据**：本批要的是**可复跑的脚本**，
   后者属 P6-X，双人见证。
8. **不因为 C3-b 两侧现在能出数就宣称达标**：**TBD-7 阈值仍未拍板**。

> ⚠️ 若实现中必须触碰某条 Non-goal ⇒ **先缩范围再报告**
> （哪份文档哪一行 / 改什么 / 为什么绕不过 / 试过的替代方案）。

## 5. 已查证坐标（**2026-10-10 由 P6-V3 机械查实 —— 请先自己复核一遍，本篇会过期**）

### 5.1 ¥0 工量比对（**别照抄"做十项"的乐观口径**）

| 查实项 | 结果 | 出处 |
|---|---|---|
| `backup-manifest.json` 是否存在 | ❌ **全仓 0 命中**（含 .md / .py / .yml / .json / .toml） | 全仓搜索 |
| 备份 / 恢复脚本是否存在 | ❌ **没有**：`backend/scripts/` 38 个脚本里无任何 backup / restore | 实读目录 |
| `PRIVATE_DEPLOY_ENABLED` | ✅ 已存在且有测试：`app/core/config.py` / `core/egress.py` / `tests/test_private_deploy_egress.py`；`deploy/docker-compose.yml` 在用 | 实读 |
| DR-E2（备份 / 恢复 + 恢复演练） | ⏳ **未做** | `delivery-requirements-and-guardrails.md:130` |
| DR-E3（升级演练，含回滚） | ⏳ **未做** | 同上 `:131` |
| DR-E4（安装验收十项脚本化） | ⏳ **未做** | 同上 `:132` |
| `deploy/` 现有物 | 只有 `docker-compose.yml` / `variants/` / `license/` / `README.md` ——**无验收脚本、无备份脚本** | 实读 |

### 5.2 十项逐条的"已有基础"预判（**下一批开工第一件事是逐条复核，不是照抄**）

| # | 项 | 是否已有机械落点 | 备注 |
|---|---|---|---|
| 1 | 容器健康 | 🟡 有 compose，无脚本化判据 | 需应在 CI / 目标环境如何"机器可跑"，属决策 W2 |
| 2 | License 生效 | ✅ G-23 已有 3 条 + `license_cli.py` | 判据可能已具备，重点在**移植到验收脚本** |
| 3 | License 拒绝可达 | ✅ G-23 同上 | 同上 |
| 4 | 上传 → 解析 → 建图 | 🟡 pipeline 有测试 | ⚠️ 取决于抽取引擎档位 / 是否要 live LLM（**W3**） |
| 5 | 问答可溯源 | 🟡 同上 | ⚠️ 同上，且可能受 P6-R 的采样口径影响 |
| 6 | 审计留痕 | 🟡 需查 `audit_log` 现有写法 | 与 `app/services/audit.py` 的 action 注册方式耦合 |
| 7 | 租户隔离 | ✅ **G-9（10 条）+ G-26（15 条）已在 CI** | 大概率是"复用"而非"新写" |
| 8 | 备份成功（`backup-manifest.json` + SHA-256） | ❌ **零基础**（依赖 DR-E2） | **本批最大未知项** |
| 9 | 恢复演练（独立环境跑通 1~6） | ❌ 依赖 DR-E2，且属**人工**（≟ P6-X） | 与序 7 P6-X 职责重叠 |
| 10 | 生产配置（无密钥进日志） | 🟡 `PRIVATE_DEPLOY_ENABLED` 有测试 | "无密钥进日志"是否已有反向守卫待查 |

## 6. 决策表（默认采纳； **(A) 情形直接把 §5.1 + §6 交给用户**）

| # | 决策 | 建议 |
|---|---|---|
| **W1** 🆕 | 第 8 / 9 项怎么办（**DR-E2 零基础**） | **建议：先把 DR-E2 的备份 / 恢复脚本补出来，再谈第 8 / 9 的脚本化**；若用户坚持本批只做 DR-E4，则**明确登记第 8 / 9 顺延到 P6-X**，不许写"已完成" |
| **W2** | "机器可跑"的定义 | 建议：**能进 CI 的进 CI**；依赖目标环境 / 真 LLM / 独立环境的，**脚本 + 明确的 Skip 档位**（并登记到 F-3 灰区，不要让它在 CI 里静默 skip —— 那是 P7-B 要清的账） |
| **W3** | 第 4 / 5 项要不要 live LLM | 建议：**默认走 mock 档**（前几批的口径），真 LLM 那条沿用 D6 **不进 CI** |
| **W4** | 十项脚本落哪 | 建议新建 `backend/scripts/install_acceptance.py`，**逐项输出 PASS / SKIP / FAIL + 原因**（可机读优先于好看） |
| **W5** | 判据重复怎么办（第 2 / 3 / 7 项已有 G） | 建议**复用既有测试**，验收脚本断言"这些槡件跑过且绿"，而不是再抄一份断言（**重复实现迟早漂移**） |

> **必须让用户选的其实是 W1**（其余可按建议项默认执行）。

## 7. 已完成项（不许重做）

- **P6-V3**：`cost_ratio` 两侧写入方（图元素个数同量纲）+ 9 条判据 + 1 条顺序耦合修正
  （`integration-log.md` §1 三个提交）。
- P6-V2：M2 抽取侧 token 落点 + `stage` 列 + 唯一约束 + 跨行 doc 去重。
- P6-V / P6-V1：读路径 7/7 继承读、`cost_metrics` 建表 + RLS + 端点真实现；两侧排序口径登记。
- ⚠️ **C3-a / C3-b 仍 BLOCKED**：TBD-7 阈值未拍板；**两侧现在能出数 ≠ 达标**。
- ⚠️ **P6-T 判分仍未做**（86 题，已判 2 题，产物刻意不入库）。

## 8. 基线（动工前自己重跑一次现行值，本篇数字会过期）

- pytest **有图口径**：**1191 passed / 5 skipped**（= P6-V2 基线 1182 + 本批 9 条新判据；
  env 见 `integration-log.md` §4 —— **三个变量都要设**，少设会静默 skip）
- pytest 无图口径：**1154 passed / 42 skipped**
- 五项门禁：`check_startup_readiness` 17/0/0、`check_seams` 12 OK/0 ERROR、
  `export_openapi --check` 零 diff、`extract_seam_signatures --check` 一致、ruff 双通过
- 本地容器：`graphrag-pg` / `graphrag-neo` 双 Up
  （实际容器名是 `graphrag-pg`，不是某些文档里写的 `graphrag-postgres`）

## 9. 验收判据（每条都要能贴机器输出）

**(A) 情形**（W1 未裁决）：

1. 把 §5.1 表 + W1~W3 原样交给用户，并写明"这么选的依据是什么"；
2. 用户选择**回登**到 `docs/deployment-spec.md` §11 或 `changes/P6-W/proposal.md`；
3. 收口时明确记"本批未开工，等待裁决"，**不得**夹带任何半成品实现。

**(B) 情形**（W1 已裁决）：

1. 十项**逐条**要么 PASS 有机器输出、要么 SKIP 有**明确登记的原因**
   （含它在哪个环境才能跑）——不许出现"看不出来是过了还是根本没跑"的项；
2. 第 2 / 3 / 7 项**复用**既有 G-9 / G-26 / G-23，不得重抄一份断言；
3. 依赖 DR-E2 的第 8 / 9 项：要么本批补出脚本（按裁决），要么**显式登记顺延**，
   两条路都不许写成"已完成"；
4. 脚本的输出**可机读**（每条一行 PASS / SKIP / FAIL + 原因），不许只打印给人看；
5. `pytest` **不降**（≥ 1191 passed / 5 skipped）；五项门禁读数不变；
6. 回登：`changes/P6-W/integration-log.md` + `delivery-requirements-and-guardrails.md`
   DR-E4（必要时连 DR-E2）状态行 + `docs/acceptance-traceability-matrix.md`。

## 10. 提交 / 推送纪律

- 每步一个 Conventional Commit；**代码 / 测试 / 文档分列**，不混提交；`main` 直推。
- 推送后以 **CI 四 job 全绿**为收口；红了的第一种反应是**看是不是批次摊太大**，
  不是先改测试让它绿（R-10：CI 才是门禁）。
- 收口时把实测证据固化进 `changes/P6-W/integration-log.md`，再写
  `changes/P6-W/new-session-prompt.md`（**提示词一律落成 MD 文件，不在聊天里贴全文**）。
- ⚠️ **不要提交** `.specstory/`、`.vscode/`、`backend/data/eval/judging/judge-progress.json`
  （P6-T 本地进度，刻意不入库）。

## 11. 升级用户的四类情况

1. **判据本身有争议**（例："第 6 项要求 ≥ 7 条审计留痕"在 mock 链路下到底该怎么凑）
   ⇒ 停下来问。
2. **必须改契约 / 必须改 `deployment-spec.md` §10 的表本身**才能落 ⇒ 停下来。
3. **边界冲突**：发现更有价值但落在 Non-goals 之外的东西 ⇒ **先缩范围登记下来、再报告**。
4. **AI 无法自行判断的取舍** —— **本批最大的一类**：**W1**（要不要先把 DR-E2 补出来），
   以及 W2 里"哪些项允许 SKIP 而不算没做"。这两条属用户 + 架构师裁决。

## 12. 不许外推

- "两侧写入方都有了" ≠ "C3-b 达标"：**TBD-7 阈值仍未拍板**。
- "第 2 / 3 / 7 项已有 G-9 / G-26 / G-23 在 CI 绿" ≠ "安装验收这三项已过"
  ——两者是**不同场景**（后者还要覆盖"目标环境 + 交付形态"）。
- "`deploy/docker-compose.yml` 里有 `PRIVATE_DEPLOY_ENABLED`" ≠ "第 10 项已通过"
  ——第 10 项还要求**无密钥进日志**，那条反向守卫是否存在**待下一批复核**。
- 别把验收写成"截图 / 人工确认"打勾：本批判据必须能被机器复跑复现。

## 13. 下一批指针（收口时按**实际结果**改，别照抄）

1. **P6-T 判分 86 题**：**必须传承到每一批**，直到完成（P8-Release 零缺口对账前判完）
   （当前进度：`backend/data/eval/judging/judge-progress.json` 已判 **2 题**，
   该产物属 P6-T 本地进度，**刻意不入库**）。
2. **P6-X（演练留证）**：**独立环境 + 双人，AI 不得单独收口**
   ——写它的提示词时**务必**先把 §1 执行模式改成"人做主体"。
3. **`cost/dashboard` 按 stage 切片**：属契约变更（跨角色：`openapi.yaml` + 前端
   `npm run gen:api`），已登记在 spec §10.1.1 第 14 项；X-5 的契约描述文本同批次一同处理。
4. **`delivery-plan.md` §9.2 序 5d 的过期前提**已于**本批**更正（那条写着"全新构建分支
   已有真实 LLM 调用可量"的旧文已改写）⇒ **这条指针不要再往下传**。
5. 队列后续：**P6-Y**（L2 端到端）→ **P7-B**（readiness 脚本补 skip 档位 + 自测，结清 F-3 灰区）
   → **P8-Release**（tag `v2.0.0`）。
