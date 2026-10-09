# P6-V1 开工提示词（写给下一批，2026-10-09 由 P6-V 落成）

> 队列活版口径：[`docs/delivery-plan.md` §9.2 序 5b](../../docs/delivery-plan.md)；
> 上一批收口：[`integration-log.md`](./integration-log.md)

---

## 1. 执行模式

**无人值守**，默认采纳本文档的建议项；只有 §10 那四类情况停下来升级用户。
跨角色严格隔离：`backend/` 归后端、`specs/` 与 `contracts/` 归架构师、`frontend/`
**本批一行不动**（除非 X-5 由用户点名要改）。

## 2. 为什么起点是 P6-V1（三条**机械**理由，不是"顺序到了"）

1. **队列口径**：`delivery-plan.md` §9.2 序 5b 写明 **P6-V1 = as-of 排序口径对齐**，
   前置 = P6-V；P6-V 已收口并提交（`git log` 五个提交，详见本目录 `integration-log.md` §1）。
2. **同域小修**：它落在 M4 / 检索域，与刚改过的 `graphs.py` / `reasoning.py` 同文件群，
   上下文还热；**不占 P6-W 的位置**（P6-W 是 DR-E4 安装验收十项，需要目标环境）。
3. **风险已被推到眼前**：`changes/P6-U/13-as-of-evidence-rank.md` 记着 DB 侧
   `ORDER BY (prio, size(rels), ids[-1]) LIMIT 400` 与 Python 侧 7 维口径不一致；
   当前候选只有 165 行、够不着 400 ⇒ **没触发是运气**，语料一涨真胜者会在 DB 侧被截掉。

## 3. 开工自检（先跑，别凭文档下结论）

```bash
cd backend && uv run python scripts/check_startup_readiness.py   # 期望仍是 17/0/0
cd backend && uv run python scripts/check_seams.py               # 期望 ERROR 0 / WARN 0 / OK 12
cd backend && uv run python scripts/export_openapi.py --check     # 期望零 diff
```

三个都对上才开始。**结论只能来自脚本输出**，不能来自本篇或集成日志的表格。

## 4. 边界纪律（Non-goals **≥ 8 条**，落 `changes/P6-V1/proposal.md`）

（下面这几条至少都要覆盖；不许删根，只准加）

1. **AI 不得代填任何 `correct` 值**（A3）——永久红线。
2. **不动 P6-V 的成果**：七条读路径的继承读，不得为了排序而改视野逻辑（读口径与排序口径是两件事）。
3. **不改 rubric / 题集 / 判分**（P6-T 仍 `UNKNOWN`，人是瓶颈）。
4. **不改 frontend/**（除非用户点名要一并修 X-5，那时才允许）。
5. **不改契约** —— `export_openapi.py --check` 零 diff 为判据；**包括描述文本**
   （`export_openapi` 的输出就是 `contracts/openapi.yaml`，前端 TS 生成物会跟着动）。
6. **不夹带**：不许把 `fetch_evidence_chunks` 的继承读、M2 token 落点、跨版本边（P5H-6）
   并进来 —— 它们各自有批次，已在上一批登记（见 `integration-log.md` §9）。
7. **不许"改一边就完了"**：一旦动了 DB 侧排序键，必须同时把两侧口径写成文档，
   否则下一次有人只改一边，又回到同款 bug。
8. **不改 `docs/sprint-calendar.md` 的方针**（它是方针，不是排期）。

## 5. 已查证坐标（**先自己复核一遍** —— 本篇会过期）

| 坐标 | 位置 | 备注 |
|---|---|---|
| DB 侧排序 | `backend/app/services/reasoning.py::_cypher_paths()` — `ORDER BY (prio, size(rels), ids[-1]) LIMIT 400` | 先看它还在不在原位（P6-V 改过该文件附近） |
| Python 侧精排 | 同文件里的 7 维比较函数 | 与上一条**逐维**比对 |
| 遗留登记 | `changes/P6-U/13-as-of-evidence-rank.md` §遗留 | **证据源头** |
| 队列定义 | `docs/delivery-plan.md` §9.2 序 5b | 编号 / 前置 / 判据 3 条 |

## 6. 决策表（默认采纳；要改请在 `proposal.md` 登记）

| # | 决策 | 建议 |
|---|---|---|
| **W1** | DB 侧要不要把 7 维全搬进 Cypher | **不建议**：先写清"哪些维在 DB 侧做、为什么"，把 `LIMIT 400` 的语义降为**保底候选**，再由 Python 侧精排；除非能证明精排救不回来 |
| **W2** | 是否动 `LIMIT 400` | 只在**有用例证明截断会丢真胜者**时改；改必有该用例 |
| **W3** | X-5（契约描述文本） | **本批不动**（跨角色 ⇒ §10 第 3 类，先问用户） |
| **W4** | 判据进不进 CI | 进（纯函数 + 内存用例，不需要 live LLM） |

## 7. 已完成项（不许重做）

- ADR-0008 §7 **7/7 读路径已切**版本继承读，`agents.py` 检索已接线（P6-V，含真图用例）。
- `cost_metrics` 表 + RLS 迁移 + 端点真实现 —— **但要记住：M2 落点与增量重算仍缺**。
- C3-a / C3-b **仍 BLOCKED**，理由已换成真实缺口；**不许因为有表就宣称出数**。

## 8. 基线（动工前自己重跑一次现行值，本篇数字会过期）

- pytest（有图口径）：**1167 passed / 5 skipped**（跑法见 `integration-log.md` §3 的 env）
- CI 起跑点：P6-V 收口 run —— **以 CI 页面最新绿 run 为准，别照抄本篇**
- 本地容器：`graphrag-postgres` / `graphrag-neo` 双 Up

## 9. 验收判据（每条都要能贴机器输出）

1. **两侧排序键逐维比对**的输出（哪一维一致、哪一维不一致、为什么）；
2. **一条候选 > 400** 的用例，证明真胜者不被 DB 侧截断（这是 W2 的存在理由）；
3. `pytest` **不降**（≥ 1167 passed）；
4. `ruff` / `check_seams` / `export_openapi --check` 三项读数不变；
5. 回登：`changes/P6-V1/integration-log.md`，并把本 §5 提到的遗留登记同步更新。

## 10. 升级用户的四类情况

1. **判据本身有争议**（例："什么是真胜者"spec 没定义）⇒ 停下来问。
2. **必须改契约**才能对齐 ⇒ 停下来（含 X-5 的描述文本）。
3. **边界冲突**：发现更有价值但落在 Non-goals 之外的东西（例如顺手发现
   `fetch_evidence_chunks` 也该切继承读）⇒ **先缩范围登记下来、再报告**，不许硬做完再说。
4. **AI 无法自行判断的取舍**（例如要不要牺牲延迟换排序质量）⇒ 问。

## 11. 不许外推

- "两侧差不离" ≠ "已对齐"；没有逐维比对的输出就不许写"对齐"。
- 别把验收写成"截图 / 人工确认"——本批判据必须能 `pytest` 复跑复现。

## 12. 下一批指针（收口时按**实际结果**改，别照抄）

1. **P6-T 判分 86 题**：**必须传承到每一批**，直到完成（P8-Release 零缺口对账前判完）。
2. **已排定的后续**（**2026-10-09 用户裁决**，已写入 `docs/delivery-plan.md` §9.2 序 5c / 5d
   与 `specs/m6-ontology-incremental.md` §10.1.1 第 12 行 —— **收口时以那两处为准**，本篇会过期）：
   - **P6-V2（直接后继）**：M2 抽取侧 token 落点 + `stage` 列（偏离 **X-6**）。
     已查证：写库**只有 1 处**（`app/tasks/registry.py:487` `_do_extract`，那边 db / org_id /
     doc_id 齐全）；真正的工量在**把 usage 从日志层提到结构化返回值**
     （`app/services/extraction/langextract.py:296` 类型契约 / `:373` invoke / `:403` 取值），
     外加 3 个测试替身签名。判据见队列序 5c。
   - **P6-V3**：C3-b 取证 —— `full_rebuild_cost` 取**首次全量构建**（偏离 **X-7**，方案 B2），
     **不许**新建全量重建入口（会撞 `incremental.py:17-18`「失败绝不回落全量」护栏）。
     ⚠️ **卡在同一个未决前提**：增量重算零 LLM ⇒ token 口径下分子恒 ≈ 0 ⇒ `cost_ratio`
     会假性"显著 < 1.00"。**在"耗时 / 图写操作数 / 受影响节点数"定案前不得开工、不得宣称达标**。
4. **P6-W**（DR-E4 安装验收十项脚本化，需目标环境）→ **P6-X**（演练留证，
   **独立环境 + 双人**，AI 不得单独收口）→ **P6-Y**（L2 端到端）→ **P7-B** →
   **P8-Release**（tag `v2.0.0`）。
5. **X-5** 契约描述文本更新（`cost/dashboard` 还写着"占位骨架 / 恒 501"）：
   跨角色任务，需 `export_openapi.py` + 前端 `npm run gen:api` 一起提。

> 原先这里挂着「M2 抽取侧 token 落点 / 增量重算**未排归属批次**」——**2026-10-09 已裁决**
> （序 5c P6-V2 / 序 5d P6-V3），故本条**已移入上面的第 2 项**。此处留白只为守 R-5：
> 不删原文，只加导航说明。**收口时请把这段话删掉**，别让它无限传下去。
