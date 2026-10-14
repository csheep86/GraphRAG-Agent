# P7-K · 集成日志（评测可复现性 · 第 1 段：两道闸门 + 坐标落盘）

> **日期**：2026-10-14 ｜ **状态**：第 1 段已交付（¥0 / 零 LLM），第 2 段（真环境连跑）未开工
> **为什么它是第 1 段**：出口判据 1 / 4 需要**独立评测环境**才跑得出来（§8 约束 4 要求先在那个环境上验
> 「连跑两次答案逐字一致」）。而闸门属于**代码层**，今天就能落、且必须用今天这套判断去验 ⟹ 先做。

---

## 1. 本批做了什么（三件事，都指向"数字不许被偷换"）

| # | 落点 | 做了什么 |
|---|---|---|
| ① | `backend/app/evaluation/runner.py` | 新增 `JudgementBasis`（判分当时那一趟的坐标锚）+ `_reproducibility_gate`（**门 ①环境自检**）+ `_answer_gate`（**门 ②答案比对**）+ `_live_env_coords` / `_blocked_result` / `_apply_judgements` |
| ② | 同上 | 多跳 `eval_multihop_accuracy` 与 C1 `eval_graph_gain`（图侧 + 基线侧）**各接上两道门**，出数前先过闸 |
| ③ | `backend/app/evaluation/criteria.py` | `Provenance` 新增 `pool_fingerprint` / `generation_model` / `top_k` ⇒ 环境坐标进**归因**（不是只进 detail）；CLI `eval_acceptance.py` 按判分表 `_source_sheets` 自动加载 basis |

### 1.1 为什么锚点是「判分表的 `_source_sheets`」

恢复 D5 的关键是**拿出当时人判的那批答案原文**。实测发现它早就存在：
`data/eval/judging/c1-judge-graph-*.json` 的元信息里写着 `_source_sheets`，指向同一目录那份答卷
`c1-sheets-*.json`（内含每题 `answer` 原文 + `_git_hash` + `_graph_spec.{pool.fingerprint,top_k,generation_model}`）。

⇒ 于是**不需要新增命令行参数**：判分表本来就自证来源（与 `eval_acceptance.py::_load_judgements`
「判分文件必须能自解释」同一条约定）。新增参数是可以**忘传**的，而这里忘传 ⇒ 直接退化为「未核」并如实登记。

### 1.2 两道门的判定口径（三条必须记住的）

| 情形 | 结果 |
|---|---|
| 池 / git / top_k / 模型任一项不符 | **BLOCKED**：`value=None` + `INDETERMINATE`，detail 同时给 `expected` 与 `actual` |
| 本次答案为**拒答** | 计为「不一致」（拒答检测**不依赖** basis，是最后一道防线） |
| 答案原文与判分所见**逐字不等** | 计为「不一致」，逐题列 `index` + 首尾 80 字 |
| 没有 basis（判分表没写 `_source_sheets`） | **如实登记 `unchecked`**，不写成"已核实"；但拒答检测照常生效 |
| basis 属于别的数据集 | 同 `unchecked`（不适用），不许跨数据集套用 |

> 刻意**没有**把"取不到坐标"判成不一致：那会造出一种**无法被反驳的假红**，而假红会反过来把真红淹没。

---

## 2. Non-goals 逐条核销（照 `changes/P7-K/proposal.md` §3，共 6 条）

| # | Non-goal | 是否守住 | 依据 |
|---|---|---|---|
| 1 | 不重判已判过的 86 题 | ✅ | 本批零判分动作；`c1-*` / `gold-multihop-*` 数据文件**一个字节未改**（`git status` 可核） |
| 2 | 不动 C1 / 多跳阈值 | ✅ | 多跳 `threshold=0.80 / calibrated`、C1 `C1_GAIN_THRESHOLD=0.10 / provisional` **原值未动** |
| 3 | 不修 B1 dev 身份头 | ✅ | 未碰 `core/auth.py` / `X-Org-Id` 相关链路 |
| 4 | 不新建全量重建语料入口、不重灌演示语料 | ✅ | 未新增任何 ingest / rebuild 入口，未跑重建 |
| 5 | 不改 rubric-v2、不新增补充口径 | ✅ | `MANIFEST.json` 未改（只读调用） |
| 6 | 不为"让数字好看"而重跑 | ✅ | **一次评测都没跑**（这正是本批的形态：先把"能不能复用"机器化，再谈重跑） |

> 顺带守住：多跳 **保留了** gold 里已存 `correct` 的兜底（`_apply_judgements`），
> 但它的**前置条件**变成"两道门都通过"——缺了门，兜底就退化成 P6-T 那条 canary。

---

## 3. 实测读数（全部为本机命令输出）

| 项 | 读数 |
|---|---|
| 新增用例 | **20 passed** |
| 全量 pytest | **1298 passed / 46 skipped / 0 failed** |
| ↳ 核销 | 本地基线 `1278 / 46` + 本批 **+20** = 1298，**skipped 数量一致** ✅ |
| ↳ ⚠️ 口径提醒 | **CI 的 1317 passed / 7 skipped 与本地不同基**（CI 有真 Neo4j/PG ⇒ 少 39 条 skip）。两个数**不许混写** |
| ruff check / format | `All checks passed!` / `302 files already formatted`（301 + 新增测试文件） |
| 接缝纪律 | `[OK]` 通过（ERROR 0 / WARN 0 / OK 12） |
| 契约零漂移 | `[OK] openapi.yaml 与后端模型一致` |
| 会话漂移检查 | `✅ 本次回切未发现漂移`（3 文件 / +498 行，未触阈值） |

---

## 4. 反向验证（**证明闸门在拦，而不是测试在绿**）

断开 ⇒ 重跑 ⇒ 接回，两次：

| 断开的部分 | 变红的用例 | 结论 |
|---|---|---|
| 门 ② `_answer_gate` 强行返回空 | `test_drifted_answer_is_caught` / `test_refusal_is_caught_even_without_basis` / `test_refusal_is_caught_with_basis_too` / **`test_all_refused_no_longer_reports_pass`** | 4 failed ⇒ canary 那条**真的由这道门把着** |
| 门 ① `_reproducibility_gate` 的 blocked 分支 | `test_pool_drift_blocks` / `test_git_and_model_and_topk_each_block` / **`test_pool_drift_blocks_instead_of_reusing_scores`** | 3 failed ⇒ 环境漂移**真的会被拦** |

> **`test_all_refused_no_longer_reports_pass` 是 P6-T canary 的直接复演**：
> 打桩让链路 6/6（此处 2/2）全拒答 + gold 里写死 `correct=True`
> ⇒ 旧实现会报 `PASS`；现在必须 `value=None / UNKNOWN / INDETERMINATE`。**它红了才说明门在工作。**

---

## 5. 一处自我纠偏（记下来，免得日后踩回去）

首版 `_apply_judgements` 写成 `judged_by=judged_by`（无条件）。读回旧实现才发现原口径是
「`judged_by` 仅在 `correct is not None` 时落名」——**未判分的题不该写着某个人的名字**，
否则事后分不清这题到底判没判。已按原口径改正（用例随之更新）。

---

## 6. 本批**没有**做的事（下一段的工，别在这儿宣称完成）

| 出口判据 | 状态 | 缺什么 |
|---|---|---|
| **1** 同命令连跑两次答案逐字一致 | ❌ 未跑 | 需要**独立评测环境**（§8 约束 1~3：单独栈 / 单独图库，且 active 版本唯一） |
| **4** 新环境下 C1 / 多跳出数并与冻结读数登记关系 | ❌ 未跑 | 同上 + **会产生 LLM 费用** |
| **2** 池指纹不符 ⇒ BLOCKED | ✅ **已落**（单测覆盖，真机未跑） | — |
| **3** 答案不匹配 ⇒ 不再静默出数 | ✅ **已落**（含 canary 复演） | — |
| **5** pytest 不降 / 三件套干净 / CI 绿 | ✅ 本地满足（CI 待回填） | — |

### 6.1 下一段的成本为什么比文档估计的低（¥0 实查结论）

文档 §8 / 审计 §7 序 9 担心「修法 ③ 要建 org / 图库 ⇒ 可能产生 LLM 费用」。实查后：

- `backup.py --neo4j-container A` 出整库 `neo4j.dump`，`restore.py --neo4j-container B --apply`
  起一次性容器 `--volumes-from` 执行 `neo4j-admin database load --overwrite-destination=true`
  ⇒ **支持 A 实例 → B 实例整库搬运**；
- 沿用同一个 `DEFAULT_ORG_ID`，图上 Chunk / Entity / KgVersion 的 `org_id` **原样保留**，无需改写
  （工具的 org 改写能力只到「把 NULL 补成某值」，也不该去改）；
- ⇒ **不需要重新抽取语料**，而那才是烧钱的一段（逐 chunk 调 LLM）。

**剩余开销只有"跑评测本身"（生成答案调模型）**，与走哪条路无关。
⚠️ 两个已知卡点：① 目标容器必须**已停**才能 load；② 整库恢复会把 `attendance-demo-v1` 与
`20261012T064951Z-inc-*` **两个 ready 版本一起搬进去** ⇒ 恢复后必须在新 PG 上把 inc 版本置非 ready
（纯 PG 写、**没有现成脚本**，命中 proposal §5 情况 2 ⇒ 动手前先报告）。

---

---

## 7. 第 2 段探路（2026-10-14 实机）｜**真机跑不了，且原因改变了本段的形态**

### 7.1 环境实况（`docker ps`）

| 容器 | 状态 | 端口（宿主机） |
|---|---|---|
| `graphrag-drill-backend-1` | Up 30h healthy | **8000** |
| `graphrag-drill-postgres-1` / `-neo4j-1` | Up 30h healthy | — / 7475、7688 |
| `graphrag-pg` / `graphrag-neo` | Up 2d / 30h | 5432 / 7687 |
| `graphrag-pg16` / `graphrag-neo4j` / `kg-poc-neo4j` | Exited | — |

### 7.2 三个 ¥0 发现

1. **`EVAL_BASE_URL` 默认 `http://127.0.0.1:8002`，而活着的服务在 `8000`**
   （`app/evaluation/runner.py:112`）⇒ 不显式给 `--base-url` 必然连不上，且 first error 会
   误导成"后端未起"。**（已绕：`--base-url http://127.0.0.1:8000`）**
2. **多跳探针结果：`链路不可用：6/6 题请求失败（首错：HTTP 401）`**
   （报告 `backend/reports/eval/p7k-multihop-probe1.json`）
3. **401 的根因**：契约要求 `bearerAuth`；而 `dev.<org>.<actor>` 兜底只在
   `ALLOW_DEV_ORG_HEADER=true` **且非生产**时装配（`app/core/auth.py:9-14`，护栏 **G-27**）。
   评测脚本 `runner.py:159` **只发 `X-Org-Id`、不发 `Authorization`** ⇒ 在关了 dev 兜底的
   栈上**必然 401**。drill 栈正是这种形态。

### 7.3 由此得出的结论（**不许绕过**）

> **不许为了跑评测去把 drill 栈的 `ALLOW_DEV_ORG_HEADER` 打开** —— 那等于把 B1 的护栏
> （P7-C 刚钉死的「非开发形态不可达」）为一次评测而拆掉一层。P7-K Non-goal 3 也写明
> 「不修 B1 dev 身份头」。

⇒ 这反过来**机械地证明 proposal §1 裁决的「独立评测环境」是必需、而非可选**：
评测必须跑在**为评测而配**的栈上（`APP_ENV=development` + `ALLOW_DEV_ORG_HEADER=true`），
而不是跑在任何一套"顺便存在"的容器里。

### 7.4 下一步（第 2 段本体，另外开一轮做）

1. 用 `deploy/docker-compose.yml` 起一套**独立评测栈**（`project-name` 与 drill 隔离），
   显式注入 `ALLOW_DEV_ORG_HEADER=true` / `APP_ENV=development`；
2. 图库按已查证的 **`neo4j-admin dump/load` 整库搬运**（`backup.py:193-232` / `restore.py:294-303`），
   沿用同一 `DEFAULT_ORG_ID` ⇒ **不需要重新抽取语料**（那才是烧钱的一段）；
3. 恢复后在新 PG 上把那个多出来的 inc 版本置**非 ready**（这是 D4 的直接成因；
   **无现成脚本** ⇒ 命中 proposal §5 情况 2：动手前先报告）；
4. 用官方 `--compare A B` 做出口判据 1（连跑两次逐字一致），再出 C1 / 多跳读数登记（判据 4）。

> ⚠️ 成本提醒：在这一步**之前**的全部工作已让 `--live` 的失败成本从"出赝数"降到
> "连不上就 BLOCKED"——第 1 段的两道门在核验出 401 时给出了 `value=null + INDETERMINATE`，
> **没有出任何数字**（这正是它们该做的事）。

---

---

## 8. 第 3 段：多跳判分材料化 + 裁决乙（2026-10-14）

### 8.1 为什么多跳那个 0.8333 是赝的（源于一个**形状差异**）

| | C1 | 多跳 |
|---|---|---|
| 判分材料自证来源 | ✅ 判分表有 `_source_sheets` ⇒ 能加载 basis | ❌ 判分写在 `gold-multihop-v1.json` 的 `correct` 字段里，**没有"当时那批答案"** |
| 门①环境自检 | 生效 | `unchecked`（按设计不拦、如实登记） |
| 门②答案比对 | 生效 | 只查拒答；6 题均非拒答 ⇒ **放行** |

⇒ 结论写在 §9.3：**P6-T canary 的两种形状，我此前只堵了一半**。拒答型已堵；
**「答案悄悄变了但仍给老分」这条没堵** —— 而这才是日常形态（不报错、不拒答）。

### 8.2 材料化怎么做的（**坐标只写真有的，缺的一律留空**）

新增 `backend/data/eval/judging/multihop-sheets-20261009T083547Z.json`，
答案原文取自 P6-T 那一趟 live 报告 `reports/eval/eval-live-20261009T083547Z.json`
（含 `_source_report` 反指），judged_by / rubric 取自 gold 的 `_judging`：

| 坐标 | 值 | 出处 |
|---|---|---|
| `_git_hash` | `17351c69` | P6-T 报告的 `git_hash` |
| `_kg_version` | `attendance-demo-v1` | gold 顶层 |
| `_judged_by` / `_judged_at` | `wIlliam` / 2026-10-13 | gold 的 `_judging` |
| `top_k` / `generation_model` / `pool.fingerprint` | **留空** | ⚠️ 判分当时**没记录** ⇒ 不许编造一个去"凑"比对 |

并在 `gold-multihop-v1.json` 顶层**只加一行** `_source_sheets`（diff = 1 行；
先试过整体 `json.dumps` 重写，会把 `expected_points` 全部重排 ⇒ 已还原改最小 diff）。
多跳的 basis **刻意不新增命令行参数**——参数能被忘传，而忘了传 ⇒ basis=None ⇒ 又回到无人把守。

顺带修了一个真缺口：`JudgementBasis._locate_sheets` 原本只找**同目录**，
而多跳的 gold 在 `data/eval/`、材料在 `judging/` ⇒ 永远拿不到 basis；
现在先同目录、再 `judging/`（注释里写清了原因）。

### 8.3 裁决乙：代码版本**只登记**，答案比对才是硬拦截

用户 2026-10-14 授权按建议执行。理由（完整版见 §9.4 的死锁）：

> 版本是「答案可能变了」的**代理指标**；`stale_answers()` 的逐字比对是**直接证据**。
> 让代理压过事实，会逼着人去改判分材料里的 `git_hash` 来"凑"放行
> ——那等于把"换个版本号"变成洗白赝数的手段。

| 坐标 | 变了会不会拦 |
|---|---|
| 池指纹 / top_k / 生成模型 | ✅ 照旧拦（它们**直接决定检索到哪些证据**） |
| 代码版本 | ❌ 不拦 ⇒ `reproducibility=verified_with_code_drift` + `detail.code_drift` 留痕 |
| **代码版本 + 材料无答案原文** | ✅ **仍拦**（`reason=code_drift_without_answer_basis`） |

最后一行是**不可让的前提**：没有答案原文时，版本差异是「这批答案可能不是人判过的那批」
的**唯一**线索，一并降级就等于撤掉全部防线。

### 8.4 死锁是怎么解的（为什么必须选乙）

- 要出数 ⇒ 环境 git 必须 == 判分时的 git（多跳 `17351c69` / C1 `101773e7`）；
- 但那是**旧代码，里面没有 P7-K 的闸门** ⇒ 在那儿跑出的数没有任何保护；
- 在当前代码跑 ⇒ 版本不符 ⇒ 门①必拦 ⇒ **永远出不了数**（甲方案还会导致
  "每改一行代码，所有判分材料作废"）。

### 8.5 反向验证（**不是测试绿了就算数**）

| 临时断开 | 结果 |
|---|---|
| 拆掉「无答案原文仍须拦」的前提 | **1 条红** |
| 退回「版本参与拦截」（裁决乙之前） | **2 条红** |
| 接回 | **22 全绿**（本地全量 **1300 passed / 46 skipped** = 1298 + 2） |

### 8.6 真机：同一条命令，昨天 PASS、今天 BLOCKED

```
昨天 probe2: [measured_provisional] multihop_accuracy  value=0.8333   verdict=PASS
今天 probe3: [unknown]              multihop_accuracy  value=null
             blocked_by=判分已过期：6/6 题的本次答案与判分材料不一致
                       （拒答或答案原文漂移）⇒ 旧判分不得套用（P6-T canary 的形状）
```

且 `detail.stale_answers` 逐题给出了 `judged_answer_head` vs `current_answer_head`
⇒ 不只是"不给数"，还**指出差在哪**。这是第 1 段 + 第 3 段合起来第一次在真机上生效。

### 8.7 一处**注释与代码不符**（登记，不在本批修）

`runner.py` 多跳处的注释写「放在**出数之前**……环境不对时再去跑 6 道题只是白烧一次 LLM」，
但 `ask_safe` 在更前面已经把 6 题跑完了才调门① ⇒ **注释的省钱的意图没兑现**。
跨出了 P7-K 的边界 ⇒ 只登记，不修。

---

## 9. 评测栈搭好 + 第一次出数 —— 但**这个数不许被引用**

### 9.1 评测环境怎么搭的（**没有搬图库、没有新建容器、没动任何既有服务**）

| 动作 | 具体做法 |
|---|---|
| 数据库 | 在 `graphrag-pg` 容器内 `CREATE DATABASE graphrag_eval`，再 `pg_dump graphrag \| psql graphrag_eval` |
| 版本状态 | 评测库里把该 org 下除 `attendance-demo-v1` 外的 3 个 ready 行改为 `status='pending'` **且 `ready_at=NULL`**（双重失效） |
| **原库校验** | 改完后 `graphrag` 库 `status='ready'` **仍是 5 行** ⇒ 一字未动 |
| 应用进程 | 用**进程级环境变量**覆盖（`env_file` 硬编码 `backend/.env`，不支持切换 ⇒ **不碰你的 `.env`**）：`APP_ENV=development` + `ALLOW_DEV_ORG_HEADER=true` + `DATABASE_URL=…/graphrag_eval` + Neo4j 走现有 `graphrag-neo`，独占端口 **8100** |
| 判据 URL | `--base-url http://127.0.0.1:8100`（默认 8002 的坑已绕） |

> ⚠️ 诚实登记：**本机起的服务用的是 PG 超级用户 ⇒ RLS 未被触及**（不是"已验证隔离"的形态）。
> 评测关心的是可复现性，不是隔离；但这一条不许被读成"RLS 已验证"。

### 9.2 结果：多跳出数 `value=0.8333`（与 P6-T 冻结读数一致）

### 9.3 ⚠️ **但这个数是赝的 —— 逐字比对推翻了它**

拿本次 `answer_texts` 与 P6-T 当时那份（`eval-live-20261009T083547Z.json`）逐题比对：

| 题 | 本次 citations | 当时 citations | 答案原文 |
|---|---|---|---|
| 1 | 6 | 8 | ❌ 不同 |
| 2 | 3 | 4 | ❌ 不同 |
| 3 | 5 | 7 | ❌ 不同 |
| 4 | 3 | 2 | ❌ 不同 |
| 5 | 5 | 6 | ❌ 不同 |
| 6 | 4 | 4 | ❌ 不同 |

**6/6 没有一题逐字一致**；而 `value=0.8333` 照出，
`detail.reproducibility` / `detail.stale_answers` **全空** ⇒ **两道门这次一道都没把住**。

### 9.4 为什么没把住（**这是缺口，不是 bug**）

| 门 | 状态 | 原因 |
|---|---|---|
| 门①环境自检 | `unchecked` | 多跳**没有**自己的判分材料 ⇒ `judgement_basis=None` ⇒ 按设计不拦、如实登记 |
| 门②答案比对 | **空** | `basis=None` 时只查**拒答**；本次 6 题 `refused=false` ⇒ 放行 |

⇒ **多跳这条路径的判分没有「自证来源」的材料**（判分写在 `gold-multihop-v1.json` 的 `correct`
字段里，不像 C1 的判分表那样带 `_source_sheets`）⇒ 后面两道门**对它天然失效**。
**这就是 D5 还没被真正堵住的地方**：答案已经全变了，判分照样被套上去。

> 换个说法：P6-T canary 的两种形状，**拒答**那条已堵（单测 `test_all_refused_no_longer_reports_pass`
> 复演过），**「答案微调但仍然给老分」**这条**没堵**，而后者才是日常形态——因为它不报错、
> 不拒答，只是悄悄变了一点点。

### 9.5 修它的路已经看见了

答卷里本来就有 **`_source_report`** 字段（指向产出这份答卷的那份 report JSON，里面就有
`answer_texts`）⇒ **多跳也能有自己的 basis**，缺的只是「多跳判分材料化」这一步：
把判分当时的 report 登记为多跳的 `_source_report`，出数前按它验答案。

⇒ **P7-K 第 3 段**（未开工）：多跳判分材料化 + basis 加载，然后重跑本节探针 ⇒
预期会变成 **BLOCKED**（答案不符）而不是 `0.8333 PASS`；只有在**答案逐字一致**时才允许出数。

---

## 10. C1 真机 + 连跑两次：**出口判据 1 被系统行为否决**（不是实现问题）

### 10.1 C1 也被门②拦住了

```
status=unknown  value=null
blocked_by = 判分已过期：图侧 33/40 题的本次答案与判分材料不一致（拒答或答案原文漂移）
             ⇒ 旧判分不得套用
```

与多跳（6/6）同向 ⇒ **旧的判分材料在当前环境下已整体不适用**。差异并非"答案答错了"，
而是**同一批证据上的措辞变了**（例：第 1 题只是尾巴多了一句「该上限规定自 2026 年
1 月 1 日起施行…」）⇒ 这正是 §8.1 说的"漂移型"，日常形态。

### 10.2 `--compare` 连跑两次：**EXITCODE=1**，119 处差异

把差异定位到字段级（**不是**排序噪声）：

| 差异字段 | 条数 | 说明 |
|---|---|---|
| `awaiting_graph[].answer` | **13** | ⚠️ **答案原文本身在两次之间不同** |
| `awaiting_graph[].citations` | 4 | 引用条数也变了 |
| `stale_answers[]` 的 index / reason / head | 其余 | 派生的：答案变了 ⇒ 漂移集合随之改变 |

⇒ **同一环境、同一份代码、同一 git（`61eebf6`），连跑两次，图侧 40 题中约 13 题答案不同。**

### 10.3 这句话必须写清楚，因为它推翻了后面的路

> **出口判据 1「同一条 live 命令连跑两次，答案逐字一致」在当前系统上不成立。**

而且它连带否掉了"重判"这条路：若答案每次跑都不一样，那么
**重判差异题也无法让 P7-K 收口** —— 判完这批，下次跑又是另一批答案，仍然 BLOCKED，
且 BLOCKED 的题集合还每次不同。

⚠️ **怎么读这个结论**：这不是 P7-K 失败。**P7-K 的任务就是把这件事逼出来。**
在装上门之前，同一套输出会以一个稳定的 `0.8333` 出现在屏幕上，没人知道它既不对
口径、也不对自己的上一次。现在它以 `value=null` + 逐题差异的形式出现，且差异本身
还能被量化（13/40）——这才是有站的住的证据的形态。

### 10.4 因此剩下的，是一条**产品侧**的债（不属于本批）

要让 C1 真正出数，前置条件是**答案可复现**。可能的方向（未经查证，仅登记方向）：

1. 生成侧：确认采样确已钉 0（`ChatOpenAI(temperature=0)` 已是），再查供应商侧
   （deepseek 在同一 prompt 下是否承诺逐字稳定）；
2. 检索侧：`top_k=32` 的候选集及其顺序是否稳定（排序 tie-break / 并发）；
3. 口径侧：若稳定做不到 ⇒ 判分维度应从"逐字一致"改为"要点覆盖"，那属于
   **rubric 层面的变更**，P7-K 的边界第 5 条明写不改 rubric-v2。

⇒ 以上任一条都是**新的一批工作**，不混在本批里做。

---

## 11. CI

| 项 | 读数 |
|---|---|
| **最新 CI run** | **`38548539100`**（push `61eebf6`）四 job **全绿**（后端 1m29s） |
| 后端 job pytest | **1339 passed / 7 skipped / 0 failed** |
| 核销 | P7-J 基线 `1317` + 第 1 段 **20** + 第 3 段 **2**（git 语义 1 条拆成 3 条）= **1339** ✅<br>（若 CI 没真把新用例收进去，这里会停在 1317） |
| 本地 vs CI 口径 | 本地 `1300 / 46 skipped`、CI `1339 / 7 skipped` —— 相差仍是**固定的 39 条 skip**（CI 有真 Neo4j/PG）⇒ 两个数都真，**但不可互换** |
| 更早的 run | `38526586392`（第 1 段，1337）／`38529683194`（P7-F，1337 持平）／`38536948877`（文档批） |
