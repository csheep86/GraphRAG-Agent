# P7-L · 集成日志（P6-T 判分落库的后坐力收口：3 条既有断言过期）

> **日期**：2026-10-13 ｜ **来源**：`changes/P7-C/integration-log.md` §5（F-P7C-5）＋ 用户裁决（2026-10-13）
> **一句话**：三条把「尚未判分」当前提的断言改成与「已判分」相容的表述，**判分红线一条没放宽**；
> 只动 `backend/tests/` 三个文件，产品代码与 P6-T 数据一行未改。

---

## 0. 结论（先给事实，全部有机器读数）

| 项 | 改前（基线） | 改后（本批） |
|---|---|---|
| 本地 `uv run pytest -q` | `3 failed / 1259 passed / 46 skipped` | **`0 failed / 1262 passed / 46 skipped`** |
| 改动范围 | — | **3 文件 / +42 −3**（全部在 `backend/tests/`） |
| 产品代码 / 判分数据 | — | **零改动**（`git diff --stat` 可核） |

三条各自的结论：断言**原意图全部保留**（见 §3），且**新增一条**机器判据——
L2 从「判分须存在」升级为「判分若存在则**必须署名**」——红线是收紧不是放松。

---

## 1. 开工自检（动手前跑的，结论只来自脚本）

| 项 | 命令 | 读数 |
|---|---|---|
| 护栏真实状态 | `python scripts/check_startup_readiness.py` | 🟢 **16 条** ｜🟠 **0** ｜🟡 **0**（🔵 条件跳过 2 条，与本批无关） |
| 未推送提交 | `git fetch -q && git log --oneline origin/HEAD..HEAD` | **空** |
| 工作区 | `git status --short` | **干净** |
| CI（**开工前提**） | `gh run view 38378258473` | 后端（ruff + pytest）❌，挂在 **Pytest** step：`3 failed, 1298 passed, 7 skipped` —— **恰好 3 条**，无第 4 条 ⇒ 与 F-P7C-5 完全吻合，照 §2 正常动手 |
| 本地复三条 | `pytest -q tests/test_eval_baseline_a1.py tests/test_evaluation_dataset.py tests/test_export_judging_sheets.py` | 同三条同名红，逐条命中 §4 坐标表 |

**两处与 `changes/P7-C/new-session-prompt.md` §7 的偏差（如实登记，未影响判据）**：

1. **HEAD 不是 `94f2e42` 而是 `3047f9c`**（docs-only：「P7-C 提示词刷新在飞状态」），
   `origin/HEAD` 已同步、工作区干净。该 commit 自带新 run **`38378525326`**，
   后端 job 同为 **`3 failed, 1298 passed, 7 skipped`** ⇒ 并无新变量，只是基线行过期。
2. `check_session_drift.py` 的 **S1 报的是 `P7-C` 的 5 条边界，不是本批 P7-L**（见 §5 F-P7L-1）。

---

## 2. 三条改了什么（坐标为**改前**行号）

| # | 坐标（改前） | 失败断言 | 改法 |
|---|---|---|---|
| **L1** | `backend/tests/test_eval_baseline_a1.py:512` | `assert result.value is None`（实测 `0.8333333333333334 is None`） | 先把 `app.evaluation.runner.load_multihop_set` monkeypatch 成 **真 gold 的 `correct=None / judged_by=None` 副本**（`dataclasses.replace`），再跑 ⇒ 人为回到「未判分」形态，**保住**「缺判分必须吐答案原文（D3）」这条覆盖。替身手法照抄同文件既有用例 `test_multihop_number_carries_answer_texts` |
| **L2** | `backend/tests/test_evaluation_dataset.py:138` | `assert all(item.correct is None)` ⇒ `assert False` | 改成「**要么全 `None`**（未判分，不入分母）／**要么全 bool 且带 `_judging.judged_by`**」；另加「半本判分」拦截：全有或全无，不许只判一部分 |
| **L3** | `backend/tests/test_export_judging_sheets.py:108` | `assert "judged_by" not in keys`（该键来自 rubric 元数据的判分人署名） | 把 `_all_keys` 的扫描范围**收窄到题行**（`sheet["graph"]` / `sheet["baseline"]` 的逐题记录），不再扫 rubric 元数据层；`correct` 与 `judged_by` 在**题行**里仍双双被禁 |

**为什么 L3 收窄不等于放宽**：`join_questions()`（`scripts/export_judging_sheets.py:72`）
是**白名单重建**题行字段的，题行里要出现 `correct` / `judged_by`，只可能是有人去动那个白名单——
收窄后的扫描**照样会红**（§3 已机械验证）。被排除的只是导出的 rubric 元数据里的判分人署名，
而**判分必须留署名**这件事恰恰是 L2 新增机器判据所要求的：两边同向不矛盾。

---

## 3. 反向验证（**证明新断言仍能被打红**，否则等于恒绿）

一次性脚本 `backend/_p7l_revcheck.py`（**已删除**，`git status` 可核：只剩三个测试文件），
不碰仓库判分数据（L2 用 **tmp 副本** + 重定向 `DATA_DIR`）。8 条全部符合预期：

```
[OK ] L3 干净题行 ⇒ 绿
[OK ] L3 题行带 judged_by（仍禁） ⇒ 红
[OK ] L3 题行带 correct（红线原样） ⇒ 红
[OK ] L3 题行嵌套带 correct ⇒ 红
[OK ] L2 现状（已判分 + 有署名） ⇒ 绿
[OK ] L2 半本判分 ⇒ 红：判分必须**全有或全无**：半本判分 ⇒ 分母只算判过的题，答对率虚高
[OK ] L2 匿名判分（缺 _judging.judged_by） ⇒ 红：...缺失或为空 ⇒ 匿名判分（A3：判分须可追溯到具体的人）
[OK ] L2 署名空串 ⇒ 红（同上）
[OK ] L2 全未判分（形态 1） ⇒ 绿
```

L1 的反向证据是**改前它就红**（缺着 monkeypatch 时读到已判分 gold ⇒ 出数）；
改后它绿、且 `answer_texts` 三条断言（`len == 6` / 题号 `[1..6]` / 每题有原文）原样在跑。

---

## 4. 出口判据逐条核销（proposal §3）

| # | 判据 | 机器读数 |
|---|---|---|
| 1 | 本地 `pytest -q` **0 failed**，总数不降（基线 1259 passed） | **`1262 passed / 46 skipped / 0 failed`**（1259+3=1308 ⇒ 1308，一条没少） |
| 2 | 三条用例原意图仍在 | L1 仍覆盖缺判分吐原文（含 `len==6` / 逐题原文断言）；L2 仍要求非匿名且**新增半本判分**拦截；L3 仍禁题行 `correct` / `judged_by`（§3 四条红灯） |
| 3 | ruff / format / seams / openapi | `ruff check` **All checks passed**；`ruff format --check` **298 files already formatted**；`check_seams.py` **ERROR 0 / WARN 0 / OK 12**；`export_openapi.py --check` **零 diff** |
| 4 | push 后 CI 四 job 全绿 | 待 push 后由 CI 裁决（**R-10**）——这是本批存在的唯一理由 |

Non-goals 5 条逐条自答：

1. **不改产品代码** ⇒ `git diff --stat` 只有 `backend/tests/*` 三个文件；
2. **不放宽红线** ⇒ 题行 `correct` / `judged_by` 禁令原文保留，L2 反而加严；
3. **不重判** ⇒ 未碰判分表与 gold 的 `correct` 值；
4. **不动 P6-T 数据** ⇒ `data/eval/**` 零改动（反向验证走 tmp 副本）；
5. **不顺手清别的过期断言** ⇒ 未在 eval 子系统内扩散任何第四处改动。

---

## 5. 遗留登记（**不在本批处置**）

- **F-P7L-1（新登记）**：`check_session_drift.py` 的 S1 **按目录 mtime 猜当前批次**
  （`_latest_proposal()` 取 `changes/P\*` 里 `_batch_recency` 最大者）⇒ 本批开工时它报的是
  **`P7-C` 的 5 条边界**（因为 P7-C 的 md 在 `3047f9c` 被刷新过，比本批 `proposal.md` 新）。
  脚本自己承认过同类的上一次误判（`check_session_drift.py:73-74`），这次是同一病因的第二次发作。
  **本批的应对**：不等它报，改完自己对着 `changes/P7-L/proposal.md` §2 的 5 条逐条答一遍（§4）。
  **不在本批改**——改它需要「显式指定批次」的接口决策，属工具/流程批次，先登记。

- 继承性遗留（非本批）：F-P7C-1（交付栈仍 `development`）／F-P7C-2（兜底未删除）／
  F-P7C-3（三处过期文案 → P7-D）／F-P7C-4（`login_flow` 实测 5 条，proposal 写 7 条）。
  **F-P7C-5 本身由本批收口**（待 CI 确认）。

---

## 6. 不许外推

- 三条转绿 **≠** 评测体系达标；它只说明**断言与新事实（86/86 已判分）相容**。
- 本批**不产生任何新的判据数字**：C1 = `0.142857`、多跳 = `0.833333` 仍是 **P6-T 的冻结值**。
- 不得宣称「P6-T 已闭环」：F-P7C-5 只是 P6-T 的后坐力**之一**。
- L2 新增的「半本判分」拦截目前是**新装的**，它还没被真实违规触发过——能红是反向脚本证明的，
  不代表历史上有人这么干过。
