# P6-X：第 9 项恢复演练（**纯人工批次**）

> **队列**：[`docs/delivery-plan.md`](../../docs/delivery-plan.md) §9.2 序 **6**（承接 P6-W）
> **性质**：§9.3 明列的**纯人工批次** —— ①判分 ②**演练** ③两条裁决，只能由人做
> **判据源**：[`docs/deployment-spec.md`](../../docs/deployment-spec.md) §6.1 / §6.2 / §10 第 9 项
> **判据本体**：`backend/scripts/install_acceptance.py:673-696` `check_9`（**已存在**，只认 `docs/drills/restore-drill-*.md` 真实存在）
> **上一批交接**：[`changes/P6-W/new-session-prompt.md`](../P6-W/new-session-prompt.md)
> **边界**：本文 §1（Non-goals **7** 条）

---

## 0. 本批做什么 / 谁做

| 环节 | 谁 | 说明 |
|---|---|---|
| **执行** | **wIlliam**（执行者） | 预建 scratch 库 → 跑 `restore.py --apply` → 看机器输出 |
| **见证** | **tianen**（见证者） | 全程在场，事后与执行者共同署名（执行者 ≠ 见证者） |
| 留证正文 | **人写** | `docs/drills/restore-drill-20261012.md`，标「内部演练，非客户现场验收」 |
| 搬运 / 校验 / 跑命令 / 回登 | **AI**（仅此四件） | 整理步骤、跑 `--verify` 与门禁、人授权后代敲命令、把输出写进 `integration-log.md` |

**本批零代码改动是预期结果**：判据已存在，第 9 项转 PASS 靠的是**留证出现**，不是改代码。

---

## 1. Non-goals（**7 条** —— 改任何一条之前先按本文 §5 升级）

1. **AI 不得代做演练 / 代写留证正文 / 代判结论**。`install_acceptance.py:673-696` 写明**人工双人**（执行者 ≠ 见证者）；留证里的"恢复成功""一致性通过"只能由执行者 + 见证者写。
2. **不许改判据换绿**：不许改 §10 的表、不许改 `check_9`、不许放宽 `--backup-dir` 之类前置。
3. **不许把「有脚本 / 有备份」写成「具备可恢复能力」**：DR-E2 原文 —— **有脚本 ≠ 具备可恢复能力**。
4. **不起任何真 LLM 调用**（可持续到 D1 另行批准为止）：本批动作必须 ¥0。
5. **不做交付动作** —— release notes / tag / 对外验收一律不碰（**R-10**）；留证须标「内部演练，非客户现场验收」。
6. **不许碰生产 / 目标环境的真实数据**：演练一律落 **scratch 库**（`--target-db` 须预建，脚本不建库）+ 独立 `--storage-root` + 独立 `--license-file`。
7. **不顺手改 `eval_acceptance.py` 的过期文案**（仍写「还没跑过一次真机」，真机已跑）：属另一批次（要连带 ruff / CI）。

> ⚠️ 若执行中发现必须触碰某条 Non-goal ⇒ **停下报告**，不自行处置。

---

## 2. 决策表（**已由人勾选**）

| # | 决策 | 定案 |
|---|---|---|
| **X1** ✅ | 执行者 / 见证者 | **wIlliam / tianen**（两人不同 ⇒ 满足人工双人） |
| **X2** ✅ | 演练环境 | **scratch**：`--target-db graphrag_restore_drill_20261012`（预建）+ `--storage-root backend/.drill/storage-20261012` + `--license-file backend/.drill/license.lic` ⇒ 不碰开发数据 |
| **X3** ✅ | 图库侧是否一并 load | **否** ⇒ `neo4j` 走 SKIP，**留证须写明"图库侧本次未恢复"**（load 要求停图容器，副作用大于收益） |
| **X4** ✅ | 备份集 | **现成**：`backend/reports/backup/20261012-p6w`（2026-10-12 15:33，六类齐全；开工前 `backup.py --verify` EXIT=0） |

---

## 3. 验收判据（每条都要能贴机器输出）

| # | 判据 | 通过标准 |
|---|---|---|
| **X-K1** | 演练真的执行过一次 | `restore.py --apply` 输出含 §6.2 一致性 PASS；**错位必须报错退出码 2**（反面验证：改清单版本号 ⇒ 必须红） |
| **X-K2** | 留证文件出现（**人写**） | `docs/drills/restore-drill-20261012.md`，文件名匹配 `restore-drill-*.md`、位置是**仓库根** `docs/drills/`；标「内部演练，非客户现场验收」；写清执行者 / 见证者 |
| **X-K3** | 第 9 项 SKIP → PASS（**自动**，不许手改） | `install_acceptance.py --backup-dir <集>` 第 9 项 `[PASS] 演练留证: N 份留证: ...`；第 8 项保持 PASS |
| **X-K4** | 静态 / 接缝不倒退 | `ruff check .` + `ruff format --check .` + `check_seams.py`：All checks passed / 294 files；ERROR 0 / WARN 0 / OK 12 |
| **X-K5** | 测试不倒退 | 默认口径 **1251 passed / 43 skipped**、真图口径 **1289 passed / 5 skipped** 都不降（零代码改动 ⇒ 应完全持平） |
| **X-K6** | 漂移 | `check_session_drift.py`：S1 读到本批 Non-goals；S2 不超阈值；S3~S5 未触发 |
| **X-K7** | 产物不入库 | `git status --porcelain`：备份集 / scratch 存储 / `docs/drills/` 之外的生成物一律不出现 |

### 3.1 基线（同侧比，不许跨口径）

| 口径 | 数字 |
|---|---|
| CI | `run 38220073670` @ `6811fda`，4 项 job success |
| `install_acceptance.py` 无参 | PASS 1 / SKIP 9 / FAIL 0 |
| `install_acceptance.py --backup-dir` | PASS 2 / SKIP 8 / FAIL 0（第 9 项仍 SKIP ⇒ 本批要它转 PASS） |
| ruff / seams | All checks passed / 294 files；ERROR 0 / WARN 0 / OK 12 |

---

## 4. 回登落点

1. `changes/P6-X/integration-log.md` —— 实测输出（§8）。
2. `docs/delivery-requirements-and-guardrails.md` —— **DR-E2** 是否脱离「部分」**由人裁决**（AI 只代笔，不代判）。
3. `docs/acceptance-traceability-matrix.md` —— 第 9 项 SKIP → PASS。

---

## 5. 升级用户的 4 类情况（AI 不许自行处置）

1. 发现**他处缺陷**（`restore.py` 有 bug、§6.2 校验逻辑错）⇒ 停下报告，不改判据。
2. 需要**改契约 / 改 §10 的表**才能前进 ⇒ 停下报告（Non-goal 2）。
3. **CI 红了且复核两遍仍红** ⇒ 不许先改测试让它绿，先按 §3.1 同侧比。
4. 出现**任何需要钱的环节**（联网恢复验证 / LLM / MinerU）⇒ 停下，回决策表补批准。

> **本批专属**：只要出现「AI 要不要替人把留证写了」的念头 ⇒ 答案恒为**不**，直接停下。

---

## 6. 不许外推（写到 != 做到）

- **留证 ≠ 恢复能力本身**：第 9 项 PASS 只说明**这一场**演练做过并留了证，**不得**外推到"目标 / 离线环境也能恢复"。
- **一次本机演练 ≠ 客户现场验收**。
- **图库侧未 load**（X3 = 否）⇒ 留证必须写明"本次未恢复图库"，不得写成"完整恢复演练"。
- 备份集那趟 **n=1**（`postgres 192157 B` / `neo4j 5023346 B` / `storage 114688000 B`）⇒ **不得**当作分布或上限。
