# P6-V3 开工提示词（写给下一批，2026-10-09 由 P6-V2 落成）

> 队列活版口径：[`docs/delivery-plan.md` §9.2 序 5d](../../docs/delivery-plan.md)；
> 上一批收口：[`integration-log.md`](./integration-log.md)

---

## 1. 执行模式（**开工前先做一道闸门判断**）

⚠️ **本批不是拿到就开工的批次**：队列 ¶ 判据 ② 明确写着「须由**用户 + 架构师裁决**后再开工」。

开工第一步是二选一：

- **(A) 未裁决** ⇒ **不许动代码**，只做一件事：把 §6 的两张 ¥0 查实表交给用户，
  让他在候选口径里选一种（或另行指定），并把裁决回登
  `specs/m6-ontology-incremental.md` §10.1.1（新增一行，编号不重排）。然后就此收口。
- **(B) 已裁决** ⇒ 按裁决落地 `incremental_cost` / `full_rebuild_cost` 的写入方。

其纪律照旧：无人值守（默认采纳本文件的建议项，只有 §11 四类情况升级）；
`backend/` 归后端、`specs/` + `contracts/` 归架构师、`frontend/` **本批一行不动**。

## 2. 为什么起点是 P6-V3（三条**机械**理由）

1. **队列口径**：`delivery-plan.md` §9.2 序 **5d** = C3-b 取证（分母按**首次全量构建**，
   偏离 **X-7**，方案 B2），前置 = P6-V2；P6-V2 已收口（五个提交，见本目录
   `integration-log.md` §1）。
2. **它是 `cost_ratio` 唯一还空着的两侧**：`cost_metrics` 表现在有两个写入方
   （M3 问答 + **M2 抽取**，P6-V2 已实读验证），但 `incremental_cost` /
   `full_rebuild_cost` **仍无任何写入方** ⇒ `cost_ratio` 恒 0.0（探针实测）。
3. **关键缺口变了**：上一轮担心「增量侧零 LLM ⇒ 分子恒 0」。本批 ¥0 查实后，
   问题比文档写的更具体 —— 连**分母侧（全量构建）也是零 LLM**（见 §5 表），
   ⇒ 「首次全量构建」这个分母**必须靠 P6-V2 落下来的抽取侧 token 来定义**，
   否则两头都空，`cost_ratio` 永远是 `0/0`。

## 3. 开工自检（先跑，别凭文档下结论）

```bash
cd backend && uv run python scripts/check_startup_readiness.py   # 期望 17/0/0
cd backend && uv run python scripts/check_seams.py               # 期望 ERROR 0 / WARN 0 / OK 12
cd backend && uv run python scripts/export_openapi.py --check     # 期望零 diff
cd backend && uv run python scripts/extract_seam_signatures.py --check  # 期望与快照一致
```

四项都对上才开始。**结论只能来自脚本输出**，不能来自本篇或集成日志的表格。

⚠️ **本地环境的坑（P6-V2 已踩）**：CI 每次起新 PG 容器 ⇒ `create_all` 天然带新列；
本地 `graphrag_test` 是**持久库**，`create_all` 不加列、`alembic upgrade head` 会从 base
重跑撞表 ⇒ 本地要补 Schema 就照抄
[`sync_local_test_db_stage.py`](./sync_local_test_db_stage.py) 的路子，别指望 `alembic`。

## 4. 边界纪律（Non-goals **≥ 8 条**，落 `changes/P6-V3/proposal.md`）

1. **AI 不得代填任何 `correct` 值**（A3）——永久红线。
2. **不许新建全量重建入口**（结论：必须正面撞 `incremental.py:16-18` 的
   「失败显式失败、**绝不**静默回落全量」护栏）——这条是硬边界，不是权衡。
3. **不改写 C3-a / C3-b 的阈值**（TBD-7 未拍板；只展示、不校准）。
4. **不改 rubric / 题集 / 判分**（P6-T 仍 `UNKNOWN`，人是瓶颈）。
5. **不改 `frontend/`**；**不改契约** —— `export_openapi.py --check` 零 diff 为判据（含描述文本）。
6. **不夹带**：不许顺手动 `dashboard` 的 stage 切片（契约变更）、X-5 描述文本、
   P5H-6 跨版本边 —— 各自有批次。
7. **不为"出数"而虚构口径**：分子在无 LLM 的事实下接近 0 是**事实**，
   不许用占位值 / 回放数把它垫出"显著 < 1.00"的样子。
8. **不动 P6-V2 的成果**：`stage` 列 / 唯一约束 / 抽取侧落点 / 跨行 doc 去重
   ——本批只能在**既有两档**之上工作。
9. **不改 `docs/sprint-calendar.md` 的方针**；不改 specs §4.3 表结构原文。

## 5. 已查证坐标（**2026-10-09 由 P6-V2 实读 —— 请先自己复核一遍，本篇会过期**）

### 5.1 两条被实读改写的前提（**本批最重要的部分**）

| 查实项 | 结论 | 出处 |
|---|---|---|
| 全量构建（分母侧）有没有 LLM | ❌ **零 LLM**：`kg/` 全目录搜 `build_chat_model` / `TokenUsage` / `invoke(` ⇒ **0 命中**；`entity_resolution.py:12` 明写「零 LLM」、`temporal.py:5` 明写「不调 LLM」 | 实读 `services/kg/` 全目录 |
| ⇒ X-7 分母从哪来 | 唯一能落数的"首次全量构建成本"= **这批语料的 M2 抽取侧 token**，而它**已经在库里**（`cost_metrics[stage='extraction']`，P6-V2 产出）⇒ 分母应定义为「相关文档首次抽取之和」，**不是**新建一次重建 | `changes/P6-V2/integration-log.md` §2 |
| 增量侧候选口径要不要新埋点 | **基本不用**：`IncrementalRebuildResult` 已经带着 `entity_count` / `relation_count` / `batch_count`，且已打进日志 `ontology_incremental_rebuild_done` ⇒ 「受影响节点数」「图写操作数」两类候选只需**落库**，不必新插埋点 | 实读 `services/kg/incremental.py:129-143`、`:321-324`、`:388-443` |

### 5.2 坐标表

| 坐标 | 位置 | 备注 |
|---|---|---|
| 全新构建分支 | `backend/app/tasks/registry.py:630` `kg_build_executor`（`:656-667` 判新/复用 kg_version） | 文档写 `634-644`，实读行号已漂移；**自身零 LLM** |
| 增量重算护栏 | `backend/app/services/kg/incremental.py:16-18`（纪律 3：绝不回落全量） | 文档写 `:17-18`，实读是 16-18 |
| 校正侧同款护栏 | `backend/app/services/kg/correction.py:421-424`「校正未生效（没有回落全量重建）」 | 文档写 `:420-424` |
| 增量结果结构 | `incremental.py:129-143` `IncrementalRebuildResult` | 现成的三个计数 |
| 版本真源字段 | `backend/app/db/models.py:259` `KgVersion`（`entity_count` / `relation_count` / `created_at` / `ready_at`） | ⚠️ **没有**耗时 / 写操作数 ⇒ 若选"耗时"口径要新列 + 迁移 |
| 成本行写入 | `backend/app/services/cost_metrics.py` `record_answer_usage` / `record_extraction_usage` → `_record_usage(stage=…)` | 新口径**建议**走同一个 `_record_usage`，不要再开第三条记账路径 |
| 队列定义 | `docs/delivery-plan.md` §9.2 序 5d | 编号 / 前置 / 判据 3 条 |
| 偏离登记 | `specs/m6-ontology-incremental.md` §10.1.1 第 12 项（X-7 行）+ 第 14 项 | 收口时以该文件为准 |

## 6. 决策表（默认采纳； **(A) 情形直接把这两张表交给用户**）

| # | 决策 | 建议 |
|---|---|---|
| **Z1** | `full_rebuild_cost` 分母 | **建议取「该批语料首次抽取的 token 之和」**（读 `cost_metrics[stage='extraction']`），不新建重建入口 ⇒ 正面满足 X-7"B2"又不撞护栏 |
| **Z2** | `incremental_cost` 分子（三组候选） | ① **受影响节点数**（`entity_count + relation_count`，零新埋点，最快）；② **图写操作数**（`batch_count` / 写边数，亦是现成的）；③ **耗时**（`KgVersion` 无此列 ⇒ 需加列 + 迁移，代价最大） |
| **Z3** | 单位不一致怎么办 | 三种口径的**量纲不同**（token vs 节点数 vs 毫秒）⇒ 分子分母必须**同量纲**，否则 `cost_ratio` 无意义。**建议口径：`full_rebuild_cost` 与 `incremental_cost` 都取同一量纲**（要节点数就两边都节点数，要 token 就两边都 token） |
| **Z4** | 落哪一行 | 落在**当天对应 stage 的行**上（沿用 `_record_usage`）；写入方必须是**唯一一处**，不许三处散写 |
| **Z5** | 判据进不进 CI | 进（纯逻辑 + PG；真 LLM / 真 Neo4j 重图那条沿用 D6 不进 CI） |

> **必须让用户选的其实是 Z2+Z3 的组合**：`(Z1 分母按 Z3 同量纲)` + `Z2 分子口径`。

## 7. 已完成项（不许重做）

- **P6-V2**：M2 抽取侧 token 落点 + `stage` 列 + 唯一约束 + 跨行 doc 去重（`pytest` 1173 → **1182**）。
- P6-V1：两侧排序口径登记 + 真图 401 候选对照。
- P6-V：ADR-0008 §7 **7/7 读路径**继承读；`cost_metrics` 建表 + RLS + 端点真实现。
- ⚠️ **C3-a / C3-b 仍 BLOCKED**：阈值 **TBD-7 未拍板**；即便本批出数也不许宣称达标。

## 8. 基线（动工前自己重跑一次现行值，本篇数字会过期）

- pytest（有图口径）：**1182 passed / 5 skipped**
  （env 见 `integration-log.md` §2 —— 三个变量都要设，少设会让两条图用例静默 skip）
- 五项门禁：`check_startup_readiness` 17/0/0、`check_seams` 12 OK/0 ERROR、
  `export_openapi --check` 零 diff、`extract_seam_signatures --check` 一致、ruff 双通过
- 本地容器：`graphrag-pg` / `graphrag-neo` 双 Up（注意：实际容器名是 `graphrag-pg`，
  不是某些文档里写的 `graphrag-postgres`）

## 9. 验收判据（每条都要能贴机器输出）

**(A) 情形**（未裁决）：

1. 把 §5.1 两张表 + Z1–Z3 组合原样交给用户，并写明「这么选的依据是什么」；
2. 用户的选择**回登**到 spec §10.1.1（新行，编号不重排，守 R-5）；
3. 收口时明确记"本批未开工，等待裁决"，**不得**夹带任何半成品实现。

**(B) 情形**（已裁决）：

1. `full_rebuild_cost` / `incremental_cost` **各有且仅有一个写入方**，且有实际读数；
2. 同量纲校验的用例（Z3）：分子分母单位一致，否则断言失败（不许给出无量纲比值）；
3. 「增量失败不回落全量」的护栏用例（撞键即红 —— 这条防的是有人为了出数去开新入口）；
4. `cost_ratio` 在无增量数据时仍是 `0.0` 而不是 NaN（沿用既有 `0.0` 语义）；
5. `pytest` **不降**（≥ 1182 passed）；五项门禁读数不变；
6. 回登：`changes/P6-V3/integration-log.md` + spec §10.1.1（新行，**编号不重排**）。

## 10. 提交 / 推送纪律

- 每步一个 Conventional Commit；**代码 / 测试 / 文档分列**，不混提交；`main` 直推。
- 推送后以 **CI 四 job 全绿**为收口；红了的第一种反应是**看是不是批次摊太大**，
  不是先改测试让它绿（R-10：CI 才是门禁）。
- 收口时把实测证据固化进 `changes/P6-V3/integration-log.md`，再写
  `changes/P6-V3/new-session-prompt.md`（**提示词一律落成 MD 文件，不在聊天里贴全文**）。

## 11. 升级用户的四类情况

1. **判据本身有争议**（例："rewrite 子图的 batch_count 算不算图写操作数"）⇒ 停下来问。
2. **必须改契约**才能落 ⇒ 停下来（含 X-5 描述文本）。
3. **边界冲突**：发现更有价值但落在 Non-goals 之外的东西 ⇒ **先缩范围登记下来、再报告**，
   不许硬做完再说。
4. **AI 无法自行判断的取舍** —— **本批最大的一类**：Z1 / Z2 / Z3 的组合，
   以及"Confirmed 之后 `cost_ratio` 拿到 0/0 怎么报"，都属于用户 + 架构师的裁决项。

## 12. 不许外推

- "两边都有写入方了" ≠ "C3-b 达标"：**TBD-7 阈值仍未拍板**。
- "全量构建分支有真实 LLM 调用可量"（plan 原文）⇒ **已被实读推翻**：那是一条零 LLM 路径。
- "测试里跑出了cost_ratio < 1" ≠ "真相比值"：先确认分母分子有没有同量纲、是不是同批语料。
- 别把验收写成"截图 / 人工确认"——本批判据必须能 `pytest` 复跑复现。

## 13. 下一批指针（收口时按**实际结果**改，别照抄）

1. **P6-T 判分 86 题**：**必须传承到每一批**，直到完成（P8-Release 零缺口对账前判完）
   （当前进度：`backend/data/eval/judging/judge-progress.json` 已判 **2 题**，该产物属 P6-T 本地进度，**刻意不入库**）。
2. **顺手续正 `docs/delivery-plan.md` §9.2 序 5d 的过期前提**：那行写着
   「`registry.py:634-644` 全新构建分支**已有真实 LLM 调用可量**」——已被实读推翻（该分支零 LLM）。
   建议在**同一条 X-7 裁决里一并更正**，别留着误导下一个人。
3. **`cost/dashboard` 按 stage 切片**：属契约变更（跨角色：`openapi.yaml` + 前端 `npm run gen:api`），
   已登记在 spec §10.1.1 第 14 项；有了 stage 行之后这事才真正具备前提。
4. **P6-W**（DR-E4 安装验收十项脚本化，需目标环境）→ **P6-X**（演练留证，**独立环境 + 双人**，
   AI 不得单独收口）→ **P6-Y**（L2 端到端）→ **P7-B** → **P8-Release**（tag `v2.0.0`）。
5. **X-5** 契约描述文本更新（`cost/dashboard` 还写着"占位骨架 / 恒 501"）：跨角色任务。
