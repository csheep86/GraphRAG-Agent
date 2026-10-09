# P6-U · 集成日志（**D4 / Sprint10.5 编号改指 + P5 出口判据对账 + 过期口径更正**）

> 队列定位：`docs/delivery-plan.md` §9.2 第 4 项。
> 边界（Non-goals 10 条）见 [`./proposal.md`](./proposal.md) §6.3（drift **S1** 已读到）。

## 1. 本批做了什么（四件，全部可复跑）

1. **U1 编号改指**：`git mv changes/Sprint10.5 changes/P6-U`（**只改名，不重排内容**——R-5）
   + 全仓 **26 文件 / 44 行**路径引用同步（§3）。
2. **U2 在途改动归因**：实测 `backend/` **已无**未提交代码 ⇒ 本批**零业务代码**（§4）。
3. **U3 P5 四条出口判据逐条对账**（§5）。
4. **U4 过期口径更正**：`DR&G` **DR-D7 行**（§6.1）+ **DR-D4 行 / §6.4.1 / `dev-doc-status` / `delivery-plan:80`（判据④）**（§6.2）。

## 2. 开工自检（结论只来自脚本，不来自文档表格）

| 项 | 读数 | 与 §7 基线的关系 |
|---|---|---|
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** | ✅ 逐位一致 |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12** | ✅ 一致 |
| `export_openapi.py --check` | **零 diff** | ✅ 一致 |
| `ruff check` / `ruff format --check` | **All checks passed** / **274 files already formatted** | ✅ |
| 最近一次绿 CI | run **37912090743**（`4887c32`） | ✅ 起点绿 |
| `pytest`（**有图口径**） | **1157 passed / 3 skipped / 0 failed**（78.03s） | ✅ 与 P6-T 基线**逐位一致**，不降 |

> 有图口径 = 真图三开关 `GRAPH_REAL_NEO4J_URI=bolt://localhost:7687` / `_USER=neo4j` / `_PASSWORD=ci-graph-pw-2026`；
> 本机 `graphrag-neo` / `graphrag-pg` 均 **Up**。

## 3. U1 · 编号改指（判据 1）

```powershell
git mv changes/Sprint10.5 changes/P6-U      # 26 个文件，全部 R（rename）
```

| 项 | 结果 |
|---|---|
| 新目录 | ✅ `changes/P6-U/` 存在，26 文件齐（含 `00-recon.md` / `10-gate-report.md` / `11` / `12` / `13` / 15 个 probe 脚本 / `proposal.md`） |
| 目录内编号引用 | ✅ 已同步；并在 `proposal.md` **追加** §6（编号改指 / 实测更正 / Non-goals 10 条 / 决策表 / P5 判据对账） |
| 全仓路径引用 | ✅ **26 文件 / 44 行** `changes/Sprint10.5/…` → `changes/P6-U/…`（`git diff --numstat` 合计 **44 insertions / 44 deletions**） |
| 残留检查 | ✅ `rg 'changes/Sprint10\.5'` 剩 **10 处**，逐处核实**全是「改名动作」的叙述**（如 `git mv changes/Sprint10.5 changes/P6-U`、DR-D4 行的更正说明），**无一处是断链路径** |

**为什么只改路径、不改叙述**：叙述性旧编号（如「旧编号 `Sprint10.5` 已废」「Sprint 10.4 收尾」）是**史实**，
改成 `P6-U` 会让 2026-10-01 的裁决记录失真 ⇒ 保留，并在 §6.4.1 显式写明「上一句已过期，勿再引用」。

## 4. U2 · 在途未提交改动归因（**提示词口径已过期，按实测记账**）

```powershell
git status --short
# ?? .specstory/  ?? .vscode/  ?? backend/data/eval/judging/judge-progress.json
git status --short backend      # 只剩 judge-progress.json（P6-T 判分产物，非代码）
git ls-files changes/P6-U       # 26 个文件全在版本库内
```

| 开场提示词 §0 的说法 | 2026-10-09 实测 | 证据 |
|---|---|---|
| `backend/` 有在途未提交改动 | ❌ **已无** | `git status --short backend` 仅 1 个未跟踪项（判分产物） |
| `changes/Sprint10.5/` 未归档 | ❌ **已 git 跟踪** | `git ls-files` 26 文件 |
| D4 未收口 | ❌ **已于 2026-10-07 由 P5-B 收口** | `changes/P5-B/integration-log.md` §5「T5 · D4 收口」（J3 前端虚线 + 演示图谱恢复 + G3 回归；CI run `37594891877` 四 job 全绿） |

⇒ **U2 无改动可接**。本批**不新写 L2 ②③ 的业务代码**（`proposal.md` Non-goal 8：已交付，再写即无消费者的重复实现）。
这处「前置已超前完成」**不是** §10 第 1 类的阻塞性前置不成立（自检与 §7 基线逐位相符、U1/U3/U4 均可执行）⇒ 继续执行并在本文如实登记。

## 5. U3 · P5 四条出口判据对账（`delivery-plan.md` P5 行）

| # | 判据 | 达成 | 证据（**可复跑 / 指得出行**） |
|---|---|---|---|
| ① | m6 spec **v1.0 定稿** | ✅ | `specs/m6-ontology-incremental.md` 头部：**v1.0，2026-10-02 定稿**，§10 checklist 八项全勾 |
| ② | schema-suggestion PoC **跑通** | ✅ | `DR&G` DR-D3 行：已达成（2026-10-02）；deepseek-chat 定向调用产出 **12 实体 + 12 关系类型** |
| ③ | **D7（R22：`question` 参与检索）** | 🟡 **部分** | `backend/app/services/graphs.py:693` `select_evidence_chunks(..., question: str \| None = None, snippets=...)` —— `question` **已入参并参与候选内字面量重排**（P6-J，2026-10-05，``RETRIEVER_GRAPH`` 由 `graph_mentions` → `graph_mentions+lexical_rerank`）。⚠️ **候选集仍是结构性窗口**（active 全量实体保底 500 → `MENTIONS` 反查 chunk）⇒ `question` **不参与候选集生成**，R22 明确「不关闭」 ⇒ **不标达成** |
| ④ | **D4：承接在途目录并改指本阶段编号** | ✅ | 代码 **2026-10-07 P5-B 收口** + 编号 **2026-10-09 本批改指**（§3） |

> ⚠️ **不许外推**：④ 达成 ≠ L2 端到端达标（端到端 = **P6-Y**）；③ 部分落地 ≠ D7 达成（参与排序 ≠ 参与召回）。

## 6. U4 · 过期口径更正（**只追加不重排，R-5**）

### 6.1 `DR&G` DR-D7 行（原第 120 行）

**追加前**：

```
| **DR-D7** | **R22：`question` 参与检索** | ⏳ 未做 | 风险 R22 | 检索不再只靠实体 |
```

**追加后**（状态列更正 + 完成判据列写死判据层）：

```
| **DR-D7** | **R22：`question` 参与检索** | 🟡 **部分落地（2026-10-05，P6-J）** — ⚠️ **免责更正**：本行原写「⏳ 未做」为**过期口径**，
2026-10-09 P6-U 核实后更正：`graphs.py:693` `select_evidence_chunks(..., question=..., snippets=...)` **已接 `question` 入参**…
⚠️ **但这不等于「参与检索」**：**候选集仍是结构性窗口**…R22 明确**「不关闭」** ⇒ 本行**不标达成**
| 风险 R22 | 检索不再只靠实体 —— **判据层 = 候选集生成**（不是候选内排序） |
```

### 6.2 `delivery-plan.md` P5 行（第 80 行）判据③ / ④

**⚠️ 判据③ 的「`qa_logs` 建表」过期口径经核实已于 `b6413c0`（交付体系重排）更正完毕**
（现文本自带「⚠️ 原判据③「`qa_logs` 建表」**已于 2026-09-26 达成**（DR-D6 已更正）」）⇒ **本批不重复追加**，
只补记 **D7 的真实达成度**（判据③ 当前无达成标记，会误导）与 **判据④ 的执行登记**：

**追加前**：

```
③ **D7（R22：`question` 参与检索）**——⚠️ 原判据③…不再作为出口判据
④ **D4：承接在途的 `changes/Sprint10.5/`**（知识时效 L2 ②③，未提交）**并改指本阶段编号**（见需求基线 §6.4）
```

**追加后**：

```
③ **D7（R22：`question` 参与检索）** 🟡 **部分落地**：`question` 已入参 `select_evidence_chunks` 并参与**候选内重排**
（P6-J，2026-10-05），但**候选集仍是结构性窗口** ⇒ R22 **不关闭**、本判据**不标达成**——⚠️ 原判据③…不再作为出口判据
④ **D4：承接在途的 `changes/P6-U/`**（知识时效 L2 ②③）**并改指本阶段编号** ✅ **已执行**：代码 **2026-10-07 P5-B 收口**
+ 编号 **2026-10-09 P6-U 改指**（⚠️ 本句原写的「未提交」**已过期，勿再引用**；见需求基线 §6.4.1）
```

### 6.3 顺带更正的同类过期口径（**U6，与 U4 同类，追加不重排**）

| 位置 | 原口径 | 更正为 |
|---|---|---|
| `DR&G` **DR-D4 行**（117） | 「🟡 在途（未提交）」 | 「**代码已收口（2026-10-07，P5-B）+ 编号已改指（2026-10-09，P6-U）**」+ 免责更正；**按判据记账不标达成**（② 前端验证降级 / ③ 前端入口未做 / 端到端 = P6-Y） |
| `DR&G` **§6.4.1**（新增小节） | — | 追加改名已执行登记表 + 「⚠️ 上一句（§6.4 现状段）已过期，勿再引用」 |
| `dev-doc-status.md` 第 68 行 | 「`backend/` 有一批**未提交**改动 + 目录**未归档**」 | 追加更正块（已收口 / 已改指 / 实测无改动） |
| `delivery-plan.md` 第 198 行 | 「m6 spec 升 v1.0（硬闸门）；D4 收口」 | 逐项标达成：① ✅ ② ✅ ③ 🟡 部分 ④ ✅ 已执行 |

## 7. 决策登记

| # | 决策 | 结论 |
|---|---|---|
| **U1** | 目录落点与编号 | ✅ `git mv` 到 `changes/P6-U` + 44 行引用同步（**只改名不重排**） |
| **U2** | 在途改动怎么接 | ⏭️ **无改动可接**（实测已空，§4）⇒ 本批零业务代码 |
| **U3** | P5 四判据 | ✅ 对账完成（① ✅ / ② ✅ / ③ 🟡 / ④ ✅），§5 |
| **U4** | 两处过期口径 | ✅ DR-D7 更正；`delivery-plan:80` 判据③ **经核实已更正**（不重复追加），只补 D7 达成度与判据④ 执行登记 |
| **U5** | 判据进不进 CI | 沿用 D6：**判据不进 CI**（依赖 live LLM）；本批无新增判据 |
| **U6** 🆕 | DR-D4 / §6.4 / `dev-doc-status:68` / `delivery-plan:198` | 与 U4 同类的过期口径，一并更正（§6.3） |
| **U7** 🆕 | `10-gate-report.md` §5 的 **A/B/C 三条出路** | ⚠️ **口径更正**：原记「未裁决」**是错的**（照抄冻结报告未回查）。实测 **B 已于 2026-09-30 裁决采纳并落地登记**（`ADR-0005:153` / `specs/m2:251` / `_bridge_window.py:87`），**A / C 已作废** ⇒ 经用户 2026-10-09 确认，**本批只回填登记**（`10-gate-report.md` §5.1 / §5.2），**不重裁** |

## 8. Non-goals 核销（10 条）

| # | 边界 | 核销 |
|---|---|---|
| 1 | AI 不得代填任何 `correct` 值 | ✅ 本批无判分动作；`judge-progress.json` 未跟踪、未改 |
| 2 | 不改 rubric / 题集 | ✅ 未触碰 |
| 3 | 不动 C2-a / C2-b / C2-c 口径 | ✅ 未触碰 |
| 4 | 不改检索 / 不回滚采样 | ✅ 未触碰（`question` 入参只作**证据引用**，未改其实现） |
| 5 | 不做 C1 / 多跳判分 | ✅ 未做 |
| 6 | 不动前端 | ✅ 未触碰 |
| 7 | 不新增端点 / 错误码 / `settings.*` | ✅ 无 ⇒ **未触发 S3** |
| 8 | 不新写 L2 ②③ 业务代码 | ✅ 本批零业务代码（§4） |
| 9 | 不重裁 §6.4 已裁事项 / 不改 A/B/C 三条出路 | ✅ 只执行改名裁决；A/B/C 已于 2026-09-30 裁为 B（U7）⇒ 本批**只回填登记**（`10-gate-report.md` §5.1），未重新开方案 |
| 10 | 不动 R27 / `alert` 表 / 演练留证 | ✅ 未触碰 |

## 9. 全部门禁（收尾）

| 项 | 读数 |
|---|---|
| `pytest`（有图口径） | **1157 passed / 3 skipped / 0 failed** = 基线**逐位一致**，不降 |
| `ruff check` / `ruff format --check` | **All checks passed** / **274 files already formatted** |
| `export_openapi.py --check` | **零 diff** |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12** |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** |
| CI（**终裁，R-10**） | ✅ run **37914433145**（`4c93974`）**四 job 全绿**，`gh run watch --exit-status` **EXIT=0**（见 §12） |

## 10. `check_session_drift`（实跑输出）

| 判据 | 输出 |
|---|---|
| **S1** | `[OK]` 读到 `changes\P6-U\proposal.md` 的 Non-goals 并逐条列出（§6.3 的 10 条 + §4 原有 5 条） |
| **S2** | ⚠️ **改动 44 个文件 > 阈值 25** —— **回答见下** |
| **S3** | ✅ 无新增 `settings.*` ⇒ 未触发 |
| **S4** | ✅ 未触及契约相关路径 ⇒ 契约不用同步 |
| **S5** | ✅ 无新增 app 模块 |

**S2 超阈值的回答（脚本拦不住、必须自己答）**：

- **实质内容改动只有 4 个文件**：`changes/P6-U/proposal.md`（追加 §6）、`docs/delivery-requirements-and-guardrails.md`（DR-D4 / DR-D7 / §6.4.1）、
  `docs/dev-doc-status.md`（一处更正块）、`docs/delivery-plan.md`（第 80 / 198 行）。
- **其余 40 个是 U1 改名的机械后果**：26 个 `git mv` 重命名（内容**零改动**）+ 14 个单行/双行路径引用同步（合计 44 行，且**不含 backend 业务代码**，
  只涉及 `_bridge_window.py` / `ingest_attendance_{csv,policies}.py` / `test_ingest_temporal.py` 的**注释与 docstring**）。
- ⇒ **不是范围蔓延**，是「改名不断链」的必然后果；无需拆批。

**收尾三问自答**：

1. **有没有顺便做的？** —— 无。§6.3 的 4 处「顺带更正」同属 U4「过期口径更正」一类，且全部是**追加**，未扩大裁决范围。
2. **有没有绕路？** —— 无。改名走 `git mv`（保留历史），未用复制 + 删除。
3. **判据是真跑出来的还是读代码得出的？** —— ③ 的「部分落地」是**读代码**（`graphs.py:693` 签名）得出的，
   **未真跑召回实验**；已在 §5 与 `proposal.md` §6.5 明确标注为 🟡 与「不许外推」，**未当作达标证据**。

## 11. 本批新查实、但**不在本批处置**的口径

1. **开场提示词 §0 的「在途未提交」口径已过期**（§4）—— 已在本文与 `proposal.md` §6.2 更正；**下一批别再照抄这句**。
2. **D4 完成度的三个降级点**（P5-B 自陈）：② 前端虚线的**行为验证是降级的**；③ as-of 前端入口未做；L2 端到端未做。
3. **`judge-progress.json` 仍未跟踪**（P6-T 判分产物）：本批按 Non-goal 1 未动它。
4. **⚠️ 本批自己的一处口径错误（病历，留档防再犯）**：我在本日志 §13 第 2 条与 `new-session-prompt.md`
   先写「§5 的 A/B/C 三条出路仍未裁决」，**这是照抄 2026-09-30 冻结报告、没回查 ADR / spec 得出的**。
   实测 **B 已于同日裁决采纳并落地**（`ADR-0005:153` / `specs/m2:251` / `_bridge_window.py:87`）。
   ⇒ **教训**：`changes/` 下的**冻结态文档**不等于现状——凡文档里出现「未裁决 / 待裁 / 未做」，
   动笔传承前必须回查 **ADR / spec / 代码**三处确认，不能只信一份报告。已于 2026-10-09 回填更正。

## 12. 提交与 CI（R-10 终裁）

| 序 | 提交 | 内容 |
|---|---|---|
| 1 | `chore(changes): rename Sprint10.5 → P6-U` | 26 个重命名 + 全仓 44 行路径引用同步（§3） |
| 2 | `docs(chore): P6-U 收口 —— 编号改指登记 + 三处过期口径更正 + P5 判据对账` | `proposal.md` §6 / `DR&G` / `dev-doc-status` / `delivery-plan` + 本日志 |

| 3 | `docs(chore): P6-U 下一批（P6-V）开场提示词 + 集成日志 §12 CI 终裁读数` | `new-session-prompt.md`（工量已机械查实：读路径 **7 条**、`cost_metrics` 表不存在、成本端点恒 501）+ 本文档 §12 |
| 4 | `docs(chore): 回填 §5 三条出路裁决（=B，A/C 作废）+ 更正本批自己的过期口径 + 排入 P6-V1` | `10-gate-report.md` §5.1 / §5.2、`12` §5 与 `13` §遗留的裁决回填、`proposal.md` §6.2 / Non-goal 9、本文档 §7 U7 / §8-9 / §11-4 / §13-2、`new-session-prompt.md` §11-2/3、`delivery-plan.md` §9.2 序 **5b**（**P6-V1**） |

**CI 终裁读数**（`gh run watch 37914433145 --exit-status` ⇒ **EXIT=0**）：

| job | 结论 |
|---|---|
| 契约校验（前后端漂移门禁） | ✅ success（`export_openapi.py --check` 零 diff） |
| 后端（ruff + pytest） | ✅ success |
| 前端（lint + gen:api） | ✅ success |
| 流水线汇总 | ✅ success |

> ⚠️ 依 P5-B §5.3 的纪律：**此处停止回登 run id** —— 再提交只为"多记一个 run id"会触发
> 「回登 ⇒ 新 commit ⇒ 新 run ⇒ 再回登」的无限递归。下一个 run 应由**下一批的实质改动**触发。

## 13. 下一批指针（按实际结果更新）

1. **⚠️ P6-T 判分遗留（必须传承到每一批，直到完成）**：86 题人工判分**顺延至项目末期**，
   **P8-Release「零缺口」对账前必须判完**。
   - 入口：填 `backend/data/eval/judging/judging-sheet-20261009T084532Z.md`（86 个填写位），
     或跑 `cd backend; uv run python scripts/judge_interactive.py --judged-by <署名>`（一次一题按 y/n，可中断续判）。
   - 已判 **2 题**（`judge-progress.json`：G-01 / G-02）⇒ 续判时不重判。
   - 判完 ⇒ 出数两趟：`--live --criteria c1_graph_gain --judgements <graph表> --baseline-judgements <baseline表>`
     （40 HTTP + 40 基线 LLM）+ `--live --criteria multihop_accuracy`（6 HTTP，**判分已写回 gold ⇒ 不需 `--judgements`**）。
   - 出数后**必须**执行判据 4：报告里的 `answer_texts_*` 与被判的 sheets 原文**逐题**比对，不一致的登记处置。
   - ⚠️ 判分表**必须是两个文件**；值只能真布尔（`null` 会报错，防「未判当答错」）。
   - ⚠️ 基线侧**不许全判 false**：`graph_gain` 分母 = 基线分，≤0 ⇒ 增益无定义（`metrics.py:234`）。
2. **✅ `changes/P6-U/10-gate-report.md` §5 的 A/B/C 已回填（2026-10-09，用户确认）**：出路 **B（作用域继承）已于
   2026-09-30 裁决采纳并落地**（`ADR-0005:153` / `specs/m2:251` / `_bridge_window.py:87`），**A / C 作废**
   ⇒ 见 `10-gate-report.md` §5.1。**别再把它当未决项传承**（本日志与提示词先前写「未裁决」是过期口径，已更正）。
   真正还悬着的三条（§5.2）：① **DB 侧 `ORDER BY …LIMIT 400` 与 Python 侧 7 维口径不一致** ⇒ 已排 **P6-V1**；
   ② **as-of 前端入口**（P5-B Non-goal 3）+ 答案措辞不区分时点 ⇒ 留 **P6-Y**；③ **45 个陈旧 `POLICY_CLAUSE` 实体** ⇒ **不修**（`--purge` 要重跑 MinerU + LLM，只换清洁度）。
3. **P6-V：P5-J（M6 剩余读路径 + `agents.py` 接线 + `cost_metrics`）** ⇒ 解开 C3-a / C3-b 的 `BLOCKED`；
   后续 **P6-W**（DR-E4 安装验收十项脚本化）→ **P6-X**（演练留证，**独立环境 + 双人**）→ **P6-Y**（**L2 端到端**）→ **P7-B** → **P8-Release**（tag `v2.0.0`）。
4. **D7 / R22 的剩余缺口**：`question` 只参与候选内排序，**候选集仍是结构性窗口** ⇒ 方向②实体链接召回 / ③向量召回 + 「扩候选集」仍待排期。
5. **P6-R 遗留**：T=0 下**重新入图**后的 C2-a / C2-b gold 命中**未端到端验证**。
6. **P6-S 遗留（顺延，已连续三批）**：`baseline_spec.embedding_dimension` 恒 `null`；后端 8002 与本地 embedding 8009 的启停**没有脚本化**。
7. **TBD-7（成本阈值）**：与队列并行、**但要用户拍板** —— 它是 C3 能否从"趋势"变"达标"的开关。
8. **R27**（注入层 93%）：保持挂起。**R30**（引用口径残留）：P6-P1 登记。
9. **`alert` 表 + 限流超阈值联动**（P2，**已连续多批**有意不做）。
