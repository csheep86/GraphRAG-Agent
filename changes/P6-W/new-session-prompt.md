# 下一批开场提示词（v1 · 2026-10-12）—— **P6-X：第 9 项恢复演练（纯人工批次）**

> **本文件曾被上一轮占用**：2026-10-10 版本写给 **P6-D1b**（已执行完，D-1b 现已落地）。
> 本文件现重写为写给 **P6-X**。
> **上一份提示词**：[`../P6-V5/new-session-prompt.md`](../../P6-V5/new-session-prompt.md)（已执行完，
> 证据见 [`integration-log.md` §8](./integration-log.md)）。

---

## 0. 一句话定位

**本批是「人在窗口内真的恢复一次，并留下 `docs/drills/restore-drill-*.md`」——AI 只能跑命令、搬运、回登，不能代做。**
判据本体（`install_acceptance.py` 第 9 项）**已存在且只认真存在的文件**；
留证一出现它**自动**转 PASS，不需要任何人去"勾"。

---

## 1. 起点确认 + 执行模式（**先看这一节，它是本批与以往最大的不同**）

### 1.1 起点

**起点 = 本 MD 所在的那一笔提交**（刻意**不钉** hash —— 上一份提示词把 HEAD 写死后，
自身落成那一笔就触发了它的停机条件；这里换成自指写法）。开学第一件事：

```bash
git log -1 --format="%H %s"            # 应含 changes/P6-W/new-session-prompt.md
gh run list --limit 1 --json databaseId,conclusion,headSha
gh run view <id> --json jobs --jq '.jobs[] | [.name,.conclusion] | @tsv'   # 4 项 success
```

### 1.2 执行模式：**人做主体**（§9.3 明列的纯人工批次）

对照 `docs/delivery-plan.md` §9.3 —— 三条只能由人做的是 ①判分 ②**演练** ③两条裁决。
⇒ **AI 在本批只允许做四件事**：

| 允许 | 说明 |
|---|---|
| **搬运** | 把备份集 / 脚本参数 / 坐标整理成人能照着执行的步骤 |
| **校验** | 跑 `--verify`、跑 `install_acceptance.py`、跑门禁，把机器输出贴回来 |
| **跑命令** | 人授权后代敲命令（含 `createdb`、跑 `restore.py`） |
| **回登** | 把实测输出写进 `changes/P6-X/integration-log.md` |

**明确不许**（红线，不是建议）：

- **不许代写** `docs/drills/restore-drill-*.md` 的正文（一个字都不许替人写）；
- **不许代填 / 代判**任何演练结论（"恢复成功""一致性通过"这类话只能由执行者 + 见证者写）；
- **不许代收口** —— 第 9 项即使转 PASS，DR-E2 的状态回登也须由**人**确认后再由 AI 代笔；
- **不许把 SKIP 说成 PASS**，也不许为了让第 9 项翻绿去改判据（Non-goal 2）。

### 1.3 为什么下一批是 P6-X（三条机械理由）

1. **第 8 项已在 2026-10-12 转 PASS**（本机真实备份，六类齐全，`backup.py --verify` EXIT=0），
   而**第 9 项仍 SKIP**，且 SKIP 的原因**不是**前置缺失 —— 是**留证 0 份**：
   全仓搜 `restore-drill-*` **零命中**（`docs/drills/` 下无文件）。
   ⇒ 十项里**唯一**卡在"人没做"的，就是这一项。
2. **D-1b 前置已满足**（`inspect_d1b` 今日读数）⇒ 不存在"做了也白做"的技术阻塞。
   ⚠️ 老文档里「因 D-1b 未落地不可执行」那句**已过期**，别再拿它当不做演练的理由。
3. **它是 DR-E2 能否脱离「部分」的最后一格**：`docs/delivery-requirements-and-guardrails.md`
   对 DR-E2 的定性是「未演练 ⇒ 不得承诺可私有化交付；**有脚本 ≠ 具备可恢复能力**」。

---

## 2. 开工自检（**动手前必做，结论只能来自脚本**）

```bash
cd backend && uv run python scripts/check_startup_readiness.py
```

按最后一列行事：`[OK]` = 真在拦；`[~~]` = 管一半；`[--]` = 挂起（对应 DR **不得**宣称完成）。
CI 门禁不在这台机器上，推送后看 GitHub Actions。

---

## 3. 边界纪律（**Non-goals 7 条，不许越过**）

| # | 边界 | 判据 / 说明 |
|---|---|---|
| 1 | **AI 不得代做演练 / 代写留证正文 / 代判结论** | §1.2；`install_acceptance.py:673-696` 第 9 项写明**人工双人**（执行者 ≠ 见证者） |
| 2 | **不许改判据换绿** | 不许改 §10 的表、不许改 `check_9`、不许放宽 `--backup-dir` 之类前置 |
| 3 | **不许把「有脚本 / 有备份」写成「具备可恢复能力」** | DR-E2 原文：**有脚本 ≠ 具备可恢复能力** |
| 4 | **不起任何真 LLM 调用**（可持续到 D1 另行批准为止） | 本批动作必须 ¥0 |
| 5 | **不做交付动作** —— release notes / tag / 对外验收一律不碰 | 纪律 R-10；留证须标「内部演练，非客户现场验收」 |
| 6 | **不许碰生产 / 目标环境的真实数据** | 演练一律落到 **scratch 库**（`--target-db` 须预建，脚本不建库） |
| 7 | **不顺手改 `eval_acceptance.py` 的过期文案**（仍写「还没跑过一次真机」，真机已跑） | 属另一批次（要连带 ruff / CI） |

> 回切点（每个子任务收尾）：`cd backend && uv run python scripts/check_session_drift.py`
> **S1 报「没有 Non-goals」⇒ 先停下来补边界**。

---

## 4. 已查证坐标表（**2026-10-12 实读，开工必须先复核行号**）

| 事项 | 坐标 / 命令 | 今日机械结论 |
|---|---|---|
| 第 9 项本体 | `backend/scripts/install_acceptance.py:673-696` `check_9` | 只认 `docs/drills/restore-drill-*.md` **真实存在**；否则 SKIP |
| 留证目录常量 | `install_acceptance.py:77` `DEFAULT_DRILL_DIR = REPO_ROOT / "docs" / "drills"` | **⚠️ 是仓库根的 `docs/drills/`，不是 `backend/docs/`** |
| 留证现状 | 全仓搜 `restore-drill-*` | **0 份** ⇒ 第 9 项机械上不可能 PASS |
| 恢复脚本 | `backend/scripts/restore.py` | 参数（实读）：`--backup-dir`（**必填**）/ `--apply`（默认只校验）/ `--pg-dsn` / `--target-db`（**须已存在，脚本不建库**）/ `--storage-root` / `--license-file` / `--neo4j-container`（**显式给才 load 图库，要求停服**）/ `--pg-container` |
| §6.2 一致性 | `restore.py` + `app/services/backup.py` | 错位 ⇒ **退出码 2**（非静默启动） |
| 备份脚本 | `backend/scripts/backup.py` | 2026-10-12 已跑通一次六类齐全；产物 `backend/reports/backup/20261012-p6w`（**gitignore，未入库** ⇒ 演练前可能需重跑） |
| 图库备份窗口 | F-P6W-2（**复现过**） | 图容器**在线** ⇒ `neo4j-admin dump/load` 必被 `The database is in use` 拒 ⇒ **须停图容器** |
| PG 备份角色 | F-P6W-1 | 必须 **BYPASSRLS**（超级用户 `graphrag`）；`app_rls` / `app_owner` 均 EXIT=1 |
| 本机容器 | `docker ps` | `graphrag-pg`（postgres:16-alpine，5432→5432）/ `graphrag-neo`（neo4j:5.26-community） |
| ⚠️ 本机无 `pg_dump` | `where.exe pg_dump` ⇒ 未找到 | 一律走 `--pg-container graphrag-pg`（容器内 host=`localhost`、端口须是**容器内** 5432） |

---

## 5. 决策表（**须由人勾选后才开工**）

| 编号 | 决策 | 选项 | 默认 |
|---|---|---|---|
| **X1** | **执行者 / 见证者**是谁（**必须两人、不能同一人**） | 填人名 | 空 ⇒ **本批不开工** |
| **X2** | 演练环境：本机（dev 容器）／**独立 scratch** | 本机 / 独立 | **scratch**（`--target-db` 预建库 + 独立 `--storage-root`）⇒ 不碰开发数据 |
| **X3** | 图库侧是否一并 load（**要停图容器**） | 是 / 否 | 否 ⇒ `neo4j` 走 SKIP，**须在留证里写明"图库侧本次未恢复"** |
| **X4** | 备份集用现成的还是重跑一次 | 现成 / 重跑 | 重跑（现成那份在 `reports/` 且**未入库**，本机可能被清） |

> **X1 未填 ⇒ 本批不做任何事**，把 §1.3 的三条理由重申一次就停下。

---

## 6. 已完成项（**别重做**）

- **第 8 项已 PASS**（2026-10-12）：六类齐全 + 8 条子项全绿；`backup.py --verify` EXIT=0。
- 第 9 项**仍 SKIP**，原因已由脚本**机械**给出（留证 0 份），不是漏做。
- DR-E2 文档里「因 D-1b 未落地不可执行」那句**已在上一批订正**（今日复核仍为已订正）。
- **AI 段到此为止**：剩下的事**只能人做**，AI 代做即越界。

---

## 7. 基线（**同侧比，不许跨口径**）

| 口径 | 数字 | 备注 |
|---|---|---|
| CI（4 项 job） | 最近一次绿：`run 38216329081` @ `7478864` | 契约校验 / 前端 / 后端 / 汇总 全 success |
| 本机 pytest 默认口径 | **1251 passed / 43 skipped** | 真图用例**默认 skip** |
| 本机 pytest 真图口径 | **1289 passed / 5 skipped** | 须显式设 `GRAPH_REAL_NEO4J_{URI,USER,PASSWORD}` |
| `install_acceptance.py` **无参** | **PASS 1 / SKIP 9 / FAIL 0** | |
| `install_acceptance.py --backup-dir <集>` | **PASS 2 / SKIP 8 / FAIL 0** | 第 8 项已 PASS；第 9 项**仍 SKIP** |
| ruff / seams | All checks passed / 294 files；**ERROR 0 / WARN 0 / OK 12** | |

> ⚠️ **本机绿 ≠ CI 绿**（上一批的教训：本机默认口径会跳过真图用例）。

---

## 8. 验收判据（**必须实际跑出，不许读代码得出**）

| # | 判据 | 命令 / 动作 | 通过标准 |
|---|---|---|---|
| **X-K1** | 演练**真的执行过一次** | 人：预建 scratch 库 → `restore.py --backup-dir <集> --apply --pg-dsn <BYPASSRLS> --target-db <scratch> --storage-root <独立目录> --pg-container graphrag-pg [--neo4j-container graphrag-neo]` | 机器输出含 §6.2 两条一致性 PASS；**错位必须报错退出码 2**（可顺手做一次反面：改清单版本号 ⇒ 必须红） |
| **X-K2** | **留证文件出现**（人写，AI 不得代笔） | `docs/drills/restore-drill-<日期>.md` | 文件名**必须**匹配 `restore-drill-*.md`，位置**必须**是仓库根 `docs/drills/`；标「内部演练，非客户现场验收」；写清执行者 / 见证者 |
| **X-K3** | 第 9 项 **SKIP → PASS**（**自动**，不许手改） | `uv run python scripts/install_acceptance.py --backup-dir <集>` | 第 9 项 `[PASS] 演练留证: N 份留证: ...`；第 8 项保持 PASS |
| **X-K4** | 静态 / 接缝不倒退 | `uv run ruff check .` + `ruff format --check .` + `check_seams.py` | All checks passed / 294 files；**ERROR 0 / WARN 0 / OK 12** |
| **X-K5** | 测试不倒退 | `uv run pytest tests -q`（默认 + 真图两套） | 1251/43 与 1289/5 **都不降**（本批若零代码改动，两套都应完全持平） |
| **X-K6** | 漂移 | `check_session_drift.py` | S1 读到本批 Non-goals；S2 不超阈值；S3~S5 未触发 |
| **X-K7** | **产物不入库** | `git status --porcelain` | 备份集 / scratch 存储 / `docs/drills/` 之外的生成物**一律不出现** |

---

## 9. 提交 / 推送纪律

1. **一笔提交只做一种角色**：`docs/drills/`（留证，**人写**）/ changes（回登）/ 后端（若动代码）**分开**。
2. Conventional Commits（`docs` / `chore` / `fix` / `test`）；commit body 必须带**实测输出**。
3. **推送后以 CI 为最终裁决**（4 项 job success）；`pre-commit` 未启用（**R-10**）。
4. **本批不许提交**：备份产物（`backend/reports/**`）、scratch 恢复目录、`backend/storage/**`、`reports/eval/**`。
5. 网络：本机到 `github.com:443` 会间歇性 `Recv failure` ⇒ push 失败**先等 60~150 秒重试**，不改 remote、不 force。

---

## 10. 升级用户的 4 类情况（**AI 不许自行处置**）

1. **发现是他处缺陷**（`restore.py` 本身有 bug、§6.2 校验逻辑错）⇒ 停下报告，不自行改判据。
2. **需要改契约 / 改 §10 的表才能前进** ⇒ 停下报告（Non-goal 2）。
3. **CI 红了且复核两遍仍红** ⇒ **不许先改测试让它绿**，先按 §7 同侧比看是不是本次引入。
4. **出现任何需要钱的环节**（联网恢复验证 / LLM / MinerU）⇒ 停下，回决策表补批准。

> **外加一条本批专属**：只要出现「AI 要不要替人把留证写了」的念头 ⇒ **答案恒为不**，直接停下。

---

## 11. 不许外推（**写到 != 做到**）

- **留证 ≠ 恢复能力本身**：第 9 项 PASS 只说明**这一场演练**做过并留了证，
  **不得**外推到"目标 / 离线环境也能恢复"。
- **一次本机演练 ≠ 客户现场验收**：留证必须标「内部演练，非客户现场验收」。
- **图库侧若未 load**（X3 = 否）⇒ 留证必须写明"本次未恢复图库"，**不得**写成"完整恢复演练"。
- **第 9 项转 PASS 后，DR-E2 的状态回登须由人确认** —— AI 只代笔，不代判。
- 备份集那趟 **n=1**：`postgres 192157 B` / `neo4j 5023346 B` / `storage 114688000 B` 都是单次读数，
  **不得**当作分布或上限。

---

## 12. 下一批指针

第 9 项 PASS 之后，DR-E2 才具备「脱离部分状态」的条件（**由人裁决是否回登、回登成什么状态**）。
之后按 `docs/delivery-plan.md` §9.2 队列走，**不由本批指定**。
下一份提示词仍按惯例落成 MD：`changes/<当前批次>/new-session-prompt.md`，**不贴全文进聊天**；
若下一批又是纯人工批次，§1.2 的「人做主体」模式**照抄过去**，不许退化成 AI 主导。
