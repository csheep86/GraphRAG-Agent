# P7-L · P6-T 判分落库的后坐力收口（3 条既有断言过期）

> **日期**：2026-10-13 ｜ **来源**：`changes/P7-C/integration-log.md` §5（**F-P7C-5**）＋ 用户裁决（2026-10-13）
> **一句话**：86 题判分落库之后，三条把「**尚未判分**」当成前提的断言失效了；把它们改成与「已判分」相容的表述，**红线一条都不放宽**。

## 0. 为什么单开一批

这三条红**不是产品缺陷**，是**新事实推翻了断言前提**，且修它们等于改**判分红线的机器表述**
（A3：脚本不得代判）。放在 P7-C 里顺手改 = 跨批次扩范围；放在 P7-K 里 = 与「可复现性」混在一起说不清。
⇒ 单开 P7-L，一份集成日志说清三条各自的前因后果。

**当前状态**：CI 后端 job `3 failed / 1298 passed / 7 skipped`（commit `ef62188`），前端 / 契约两个 job 绿。
**机械证明与本批之外无关**：`git stash -u` 后在 HEAD `40a23c8` 上复跑 ⇒ 同样 3 failed。

## 1. 三条待修（坐标 + 推荐修法，均已由用户选定）

| # | 坐标 | 失败断言 | 成因 | 修法（**改断言，不改产品代码**） |
|---|---|---|---|---|
| **L1** | `backend/tests/test_eval_baseline_a1.py:512` | `assert result.value is None`（实测 `0.8333333333333334 is None`） | 多跳 gold 已判完 ⇒ `multihop_accuracy` **正常出数**，不再 `blocked_by=A3` | 用 monkeypatch 把 `load_multihop_set` 换成 `correct=None` 的副本 ⇒ **保住「缺判分时必须吐答案原文」（D3）这条覆盖**，而不是删掉它 |
| **L2** | `backend/tests/test_evaluation_dataset.py:138` | `assert all(item.correct is None for item in items)` | 同上：判分后 `correct` 不再是 `None` | 改为「要么全 `None`（未判分），要么全为 bool **且** gold 集带 `_judging.judged_by`」⇒ 反而**加强**了「判分必须非匿名」的要求 |
| **L3** | `backend/tests/test_export_judging_sheets.py:108` | `assert "judged_by" not in keys` | P6-T 给 `MANIFEST.json` 的 `rubric.supplements[*]` 写了 `judged_by: wIlliam`，判分表把 rubric 元数据一起导出 ⇒ 该键出现在产物里 | 守卫只扫**题行**层级、不扫 rubric 元数据（`_all_keys` 收窄）；`correct` 的禁令**不动** |

## 2. Non-goals（**改一条都要先回来登记理由**）

1. **不改产品代码**——三条全在测试侧，L1 的替身也走 monkeypatch。
2. **不放宽任何判分红线**——「产物不得含 `correct`」「判分必须非匿名」两条**原样保留**；
   L3 只允许把扫描范围收窄到题行，**不许**改成"允许 `judged_by` 出现在题行里"。
3. **不重判任何题**——86 题判分已是事实，本批不触碰判分表与 gold 的 `correct` 值。
4. **不动 P6-T 的数据**（MANIFEST / gold / 两张判分表）——L3 走测试侧收窄，不改数据。
5. **不顺手清理 eval 子系统里的其它过期断言**——发现即登记，另立批次。

## 3. 出口判据

1. `uv run pytest -q` **本地 0 failed**（三条转绿，且总数不降：基线 `1259 passed / 46 skipped`）。
2. 三条用例的**原意图**仍在：L1 仍覆盖「缺判分 ⇒ 吐答案原文」；L2 仍要求「判分非匿名」；
   L3 仍禁止题行出现 `correct` / `judged_by`。
3. `ruff check` / `ruff format --check` / `check_seams.py` ERROR 0 / `export_openapi.py --check` 零 diff。
4. push 后 **CI 四 job 全绿**（这是本批存在的唯一理由：把后端 job 救回来）。

## 4. 升级用户的四种情况

1. 某条修法发现**必须**改产品代码才能保住原意图 ⇒ 停下报告。
2. 修完发现还有别的 eval 断言依赖「未判分」前提 ⇒ 登记进本批清单，逐条判定，**不批量改**。
3. `MANIFEST.json` 的 `supplements[].judged_by` 若被判定为**不该出现在 rubric 元数据里** ⇒
   那是数据侧裁决（改字段名 / 移到 `_judging` 下），须先问，不得顺手改数据。
4. CI 红且复核两遍仍红 ⇒ 带 job 名 + 失败行 + 归因。
