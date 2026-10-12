# 下一批开场提示词（v1 · 2026-10-12）—— **P6-W：DR-E2 备份成功（AI 段）+ 恢复演练（人工段 P6-X）**

> 上一份提示词在 [`changes/P6-V6/new-session-prompt.md`](../../P6-V6/new-session-prompt.md)（已执行完）；
> 本批提示词按「落在**当前批次目录**下、写给下一批」的约定写在 `changes/P6-V5/`。

---

## 0. 一句话定位

**本批要做的是把 DR-E2 的「AI 能做的那一半」从 SKIP 推成 PASS，并显式写明「另一半不许 AI 做」。**
它的判据本体（`install_acceptance.py` 第 8 / 9 项）**已经存在且会报错** —— 不是在造新东西。

---

## 1. 起点确认 + 为什么是它（**三条机械理由，不是喜好**）

**起点 = 本 MD 所在的那一笔提交**（刻意**不钉**具体 hash —— 上一份提示词把 HEAD 写死后，
自身落成 / 去重那两笔就触发了它的停机条件；这里换成自指写法）。
开学第一件事就是复核：

```bash
git log -1 --format="%H %s"            # 应含 changes/P6-V5/new-session-prompt.md
gh run list --limit 1 --json databaseId,conclusion,headSha
gh run view <id> --json jobs --jq '.jobs[] | [.name,.conclusion] | @tsv'   # 4 项 success
```

### 为什么下一批是 P6-W（三条）

1. **C3 已经出真值了，但停在 D2**（= TBD-7 阈值由人裁决，AI 不得代填）——不能再做。
   2026-10-12 P6-V5 真机实测：**C3-a = 7574.0000 token/doc（`PASS(provisional)`）／
   C3-b = 0.2727（`PASS`）**；`--calibrate` 建议 9100，**不采纳**（n=1 且文档仅 1019 字）。
2. **DR-E2 是当前唯一的「脚本已有、证据没有」的交付阻塞**：`docs/delivery-requirements-and-guardrails.md`
   给它的定性是「未演练 ⇒ 不得承诺可私有化交付；**有脚本 ≠ 具备可恢复能力**」。
3. **它的收敛路径今天是机械可查的**（见 §4 坐标表），且 **AI 段是 ¥0、CI 段零依赖** ——
   是当下唯一「既不花 LLM 钱、又能真的推进一格」的批次。

---

## 2. 开工自检（**动手前必做，结论只能来自脚本**）

```bash
cd backend && uv run python scripts/check_startup_readiness.py
```

按最后一列行事：`[OK]` = 真在拦；`[~~]` = 管一半，**另一半所管需求不得宣称完成**；
`[--]` = 挂起，**对应 DR 一律不得宣称完成**。**犯了却已改的是你所依赖的那一条。**

再跑一次 https 是 CI 门禁，不在本地。

---

## 3. 边界纪律（**Non-goals 6 条，不许越过**）

| # | 边界 | 判据 / 说明 |
|---|---|---|
| 1 | **不许 AI 代做恢复演练** | `install_acceptance.py:673-696` 第 9 项写明：即便 D-1b 满足，本项**仍为人工双人**（执行者 ≠ 见证者），AI **不得单独收口** ⇒ 顺延 **P6-X** |
| 2 | **不许为了十项全绿去改 §10 的表 / 改脚本断言** | `install_acceptance.py:19-26` 纪律第 2 条 |
| 3 | **不许把「有脚本」写成「具备能力」** | DR-E2 原文：**有脚本 ≠ 具备可恢复能力** |
| 4 | **不许起任何真 LLM 调用**（可持续到 D1 另行批准为止） | 本批全部动作必须 ¥0 |
| 5 | **不做交付动作** —— release notes / tag / P6-X 演练本体一律不碰 | 纪律 R-10 |
| 6 | **不许降低既有判据换绿**（包括把 SKIP 说成 PASS、把 `--backup-dir` 缺参改掉） | 纪律 **R-10** |

> 回切点（每个子任务收尾）：`cd backend && uv run python scripts/check_session_drift.py`
> **S1 报「没有 Non-goals」⇒ 先停下来补边界**，不许边写边定边界。

---

## 4. 已查证坐标表（**2026-10-12 实读，开工必须先复核行号**）

| 事项 | 坐标 / 命令 | 今日机械结论 |
|---|---|---|
| 第 8 项「备份成功」 | `backend/scripts/install_acceptance.py::check_8` | **SKIP**：`缺 --backup-dir ⇒ 无真实备份产物可验（先跑 backup.py --out-dir <目录>）` |
| 第 9 项「恢复演练」 | `install_acceptance.py:673-696` | **SKIP**：`D-1b 前置已满足 ⇒ 可做，但本项仍为人工双人 ⇒ 顺延 P6-X` |
| 备份脚本 | `backend/scripts/backup.py` | 已存在；**本机尚未跑过一次** |
| 恢复脚本 | `backend/scripts/restore.py` | 已存在（一致性校验：错位 ⇒ 退出码 2） |
| D-1b 机械查 | `install_acceptance.py::inspect_d1b`（只扫 `.github` / `deploy` / `backend/scripts`） | **前置已满足**（← DR-E2 文档里「因 D-1b 未落地不可执行」那句**已过期**，今日已订正） |
| 键值表依据 | `docs/delivery-requirements-and-guardrails.md`（DR-E2 行） | 同上订正已在同一天提交 |
| ⚠️ 过期文案（**候选，不许顺手改**） | `backend/scripts/eval_acceptance.py` 的「升为 MEASURED 还缺什么」仍写「还没跑过一次真机」 | 真机**已跑**（P6-V5 §8）；修正属**另一批次**（要连带 ruff / CI） |

---

## 5. 决策表（**须由用户在下面两项上勾选后才开工**）

| 编号 | 决策 | 选项 | 默认值 |
|---|---|---|---|
| **W1** | 是否授权跑一次**真实备份**（写入本机磁盘，**不联网、¥0**） | 批准 / 不批 | **不批即停** ⇒ 本批 AI 段无可产出的证据，直接转 §10 升级用户 |
| **W2** | 恢复演练（P6-X，**人工双人**）是否已排入近期日程 | 是 / 否 | 否 ⇒ 本批只登记「AI 段结论 + 人工段前因」，**不收口** |

> **两个都没勾** ⇒ 本批不做任何事，把 §1 的三条理由重申一次就停下（不许变成"随手先写点什么")。

---

## 6. 已完成项（**上一批留下，别重做**）

- `changes/P6-V5`：V0 隔离清场（4 处 writers，含 `--calibrate` 前的成因）、会话级守卫
  `tests/conftest.py::cost_metrics_residue_guard`（已**反向验证**：播种脏行会红、清掉后 1251/43 不变）、
  C3 真机真值、守卫首战在 CI 上拦下三处额外污染。
- docs：DR-E2 过期描述已订正；矩阵 C3-a / C3-b 已登记真值（+为什么不采纳 9100）。
- **`backend/data/eval/judging/judge-progress.json`：保留**（= 人工判分续判状态，删它 = 销毁进度）。

---

## 7. 基线（**同侧比，不许跨口径**）

| 口径 | 数字 | 备注 |
|---|---|---|
| CI（4 项 job） | 最近一次绿：`run 38211562200` @ `dc60bf9` | 契约校验 / 前端 / 后端 / 汇总 全 success |
| 本机 pytest 默认口径 | **1251 passed / 43 skipped** | 真图用例**默认 skip** |
| 本机 pytest **真图口径** | **1289 passed / 5 skipped** | 必须显式开 `GRAPH_REAL_NEO4J_*`（凭据取本机 `.env`）；⚠️ **本机默认绿 ≠ CI 绿** |
| `install_acceptance.py`（无参数） | **PASS 1 / SKIP 9 / FAIL 0** | 第 8 项即本批要推的那一格 |

---

## 8. 验收判据（**必须实际跑出，不许读代码得出**）

| # | 判据 | 命令 | 通过标准 |
|---|---|---|---|
| **W-K1** | 跑一次**真实备份** | `uv run python scripts/backup.py --out-dir <目录>` | 退出码 0；产出含 `backup-manifest.json`（SHA-256 / 大小 / 时刻 / active `kg_version`） |
| **W-K2** | 第 8 项 **SKIP → PASS** | `uv run python scripts/install_acceptance.py --backup-dir <同上>` | 该项 `[PASS] manifest 校验`；且第 9 项**仍为 SKIP**（人间双人未做 ⇒ 不许被"顺便"抹成 PASS） |
| **W-K3** | 静态检查不倒退 | `uv run ruff check .` + `ruff format --check .` | All checks passed / 294 files formatted |
| **W-K4** | 接缝门禁 | `uv run python scripts/check_seams.py` | ERROR 0 / WARN 0 / OK 12 |
| **W-K5** | 测试不倒退 | `uv run pytest tests -q`（默认口径）**+ 真图口径各一次** | 1251/43 与 1289/5 **都不降**（动到写入铲子时必须两套都跑） |
| **W-K6** | CDN 漂移 | `check_session_drift.py` | S1 读到本批 Non-goals；S2 不超阈值；S3~S5 未触发 |

---

## 9. 提交 / 推送纪律

1. **一笔提交只做一种角色**：后端（code/test）/ 架构师（docs + 契约）/ changes（本批三件套）**分开**。
2. Conventional Commits：`fix` / `feat` / `docs` / `test` / `chore`；commit body 必须带**实测输出**。
3. **推送后以 CI 为最终裁决**：确认 4 项 job success 才算完；`pre-commit` 未启用，`CI` 才是门禁（**R-10**）。
4. **本批不许提交** `backend/storage/**` / 备份产物 / `reports/eval/**`（生成物，勿混入证据）。

---

## 10. 升级用户的 4 类情况（**AI 不许自行处置**）

1. **发现是他处缺陷**（如备份脚本本身有 bug、manifest 校验逻辑错）⇒ 停下报告，不自行改判据。
2. **需要改契约 / 改 §10 的表才能前进** ⇒ 停下报告（Non-goal 2）。
3. **CI 红了且复核两遍仍红** ⇒ **不许先改测试让它绿**，先按本提示词 §7 同侧比看是不是本次改动引入的。
4. **出现任何需要钱的环节**（联网恢复验证 / LLM / MinerU 等）⇒ 停下，回到决策表补批准。

---

## 11. 不许外推（**写到 != 做到**）

- 「备份成功 PASS」**只代表第 8 项**，**不得**据此宣称 DR-E2 达标 —— 第 9 项（演练）仍 SKIP。
- 「本地肉机有过一次成功备份」**不得**外推到「目标 / 离线环境也没问题」—— 那是 P6-X 人工段的活。
- D-1b 前置满足 **≠** 交付已经私有化可行；只是第 9 项的**前置**成立。
- **实测读数**：上一批得出的数字（C3 的 7574 / 0.2727）是 **n=1 的样例**，
  **不得**当作分布或上限引用。

---

## 12. 下一批指针

人工段（恢复演练，**P6-X**）由用户执行并留证 `docs/drills/restore-drill-*.md`
（执行者 ≠ 见证者，AI **不得**单独收口）；留证出现后 `install_acceptance.py` 第 9 项会**自动转 PASS**
（`check_9` 只认真实存在的文件，**不认 AI 的口头声明**）。
下一份提示词仍按惯例落成 MD：`changes/<当前批次>/new-session-prompt.md`，**不贴全文进聊天**。
