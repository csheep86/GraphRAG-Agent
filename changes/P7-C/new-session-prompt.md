# 下一批开工提示词：P7-L（P6-T 判分落库的后坐力收口）

> 本文件是 **P7-C 批次目录下、写给下一批（P7-L）** 的开场提示词（2026-10-13 立）。
> 落地原因：对话上下文会丢，仓库不会。开工前**先读本文件**，再读 `changes/P7-L/proposal.md`。

---

## 1. 确认起点：从 `P7-L` 开始

**执行模式**：AI 主体（改测试断言 + 跑命令 + 回登），**不需要**第二自然人。

**为什么是它——三条机械理由**：

1. **它是当前唯一让 CI 后端 job 变红的东西**：commit `ef62188` 的 CI = 后端 `3 failed / 1298 passed / 7 skipped`，
   前端 ✅ / 契约 ✅。**不修它，后面每一批都无法宣称「CI 绿」**。
2. **它是 P6-T 的直接后果，不是新缺陷**：`git stash -u` 后在 HEAD `40a23c8` 上复跑 ⇒ 同样 3 failed
   （已机械证明，见 `changes/P7-C/integration-log.md` §3）。修的是「断言前提被新事实推翻」。
3. **用户已裁决单开本批**（2026-10-13）：不放进 P7-C（跨批次扩范围）、不放进 P7-K（与可复现性混在一起说不清）。

---

## 2. 开工自检（**动手前先跑，结论只能来自脚本**）

```bash
cd backend && uv run python scripts/check_startup_readiness.py   # 必须 🟢 16 条 / 🟠 0 / 🟡 0
git fetch -q && git log --oneline origin/HEAD..HEAD               # 必须空（无未推送提交）
git status --short                                                # 必须干净
gh run list --limit 2 --json displayTitle,conclusion,headSha      # 见 §7 基线
```

✅ **推送状态已确认（2026-10-13 用户已推）**：`origin/HEAD = 94f2e42`，未推送提交 = 0，工作区干净。
⇒ **第一件事**不是推代码，而是确认 CI：**`94f2e42` 的 run `38378258473`** 跑完没有
（预期：后端 job ❌ 3 failed = F-P7C-5，前端 / 契约 ✅）。若后端 job 出现**第 4 条**失败 ⇒
那是新情况，**先定位再动手**，不许默认「反正有 3 条红的」。

---

## 3. 边界纪律（**Non-goals 5 条**，见 `changes/P7-L/proposal.md` §2）

1. 不改产品代码；2. 不放宽任何判分红线（`correct` 禁令、非匿名判分）；
3. 不重判任何题；4. 不动 P6-T 的数据；5. 不顺手清其它 eval 过期断言。

---

## 4. 已查证坐标表（**不要再查第二遍**）

| # | 坐标 | 事实 |
|---|---|---|
| L1 | `backend/tests/test_eval_baseline_a1.py:512` | `assert result.value is None` ⇒ 实测 `0.8333333333333334 is None`（多跳已判分 ⇒ 正常出数） |
| L2 | `backend/tests/test_evaluation_dataset.py:138` | `assert all(item.correct is None)` ⇒ `assert False`（gold 已写 `correct`） |
| L3 | `backend/tests/test_export_judging_sheets.py:108` | `assert "judged_by" not in keys` ⇒ 该键随 `MANIFEST.json` 的 `rubric.supplements[*].judged_by` 被判分表内联导出 |
| 参考实现 | `backend/tests/test_eval_baseline_a1.py:520-544` | `test_multihop_number_carries_answer_texts` 已有 monkeypatch `load_multihop_set` 的现成写法 ⇒ L1 照抄它的形态 |
| 守卫原文 | `backend/tests/test_export_judging_sheets.py:104-108` | `_all_keys(sheet)` 递归扫全树 ⇒ L3 只需收窄到题行 |

---

## 5. 决策表（已裁决，不要重新讨论）

| 决策 | 结论 |
|---|---|
| 三条红怎么修 | **只改断言，不改产品代码**（用户 2026-10-13 裁决） |
| L1 | monkeypatch 造 `correct=None` 副本，保住「缺判分须吐原文」（D3）这条覆盖 |
| L2 | 「要么全 `None`，要么全 bool **且** 带 `_judging.judged_by`」——**加强**非匿名判分 |
| L3 | `_all_keys` 收窄到题行；`correct` 禁令不动 |
| P7-K 版本修法 | 用户已裁决 **③ 独立评测环境**（`changes/P7-K/proposal.md` §8），本批不碰 |

---

## 6. 已完成项（不要重做）

- **P6-T**：86/86 判分（`40a23c8`），`C1=0.142857` / 多跳 `0.833333`，F1/F2 未触发。
- **P7-C**：dev 兜底收口 + 护栏 **G-27**（`ef62188`），G 计数 15 → 16。
- 遗留已登记：F-P7C-1（交付栈仍 `development`）/ F-P7C-2（兜底未删除）/ F-P7C-3（三处过期文案 → P7-D）/ F-P7C-4（`login_flow` 实测 5 条，proposal 写 7 条）。

---

## 7. 基线（**只能往好不能往坏**）

| 项 | 读数 |
|---|---|
| 本地 `uv run pytest -q` | `3 failed / 1259 passed / 46 skipped` |
| CI 后端 job | `3 failed / 1298 passed / 7 skipped`（带图环境）；run **`38367482383`**（commit `ef62188`）❌，前端 / 契约 ✅ |
| `check_startup_readiness.py` | 🟢 **16 条**（G-27 5 项）｜🟠 0｜🟡 0 |
| `ruff check` / `ruff format --check` | All checks passed / 298 files formatted |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 12 |
| `export_openapi.py --check` | 零 diff |
| HEAD | **`94f2e42`**（✅ 已推送，`origin/HEAD` 同步；工作区干净）｜`1a8e09d`（CI 读数回填）→ `94f2e42`（裁决登记 + P7-L 骨架 + 本提示词） |

---

## 8. 验收判据（**每条都要能贴机器输出**）

1. 本地 `pytest -q` **0 failed**，且 `passed` 不降（≥1259）。
2. 三条用例**原意图仍在**：L1 仍覆盖缺判分吐原文；L2 仍要求非匿名；L3 仍禁题行 `correct`。
3. 三件套干净 + CI **四 job 全绿**。

---

## 9. 提交推送纪律

- 一个批次一个 `proposal.md` + 一个 `integration-log.md`；**不得跨批次扩范围**。
- 提交前本地三件套 + `pytest`；**推送后以 CI 为最终裁决**（R-10）。
- 本批收尾：更新 `docs/release-readiness-audit-2026-10-13.md` §7 的 P7-L 行状态。

---

## 10. 升级用户的四种情况

1. 某条修法发现**必须**改产品代码 ⇒ 停下报告。
2. 发现更多 eval 断言依赖「未判分」前提 ⇒ 登记，逐条判定，不批量改。
3. `MANIFEST.json` 的 `supplements[].judged_by` 若被判定不该出现在 rubric 元数据里 ⇒ **数据侧裁决，先问**。
4. CI 红且复核两遍仍红 ⇒ 带 job 名 + 失败行 + 归因。

---

## 11. 不许外推

- 三条转绿 **≠** 评测体系达标；它只说明断言与新事实相容。
- 本批**不产生**任何新的判据数字；C1 / 多跳读数仍是 P6-T 的冻结值。
- 修完不得宣称「P6-T 已闭环」——F-P7C-5 只是 P6-T 的后坐力之一。

---

## 12. 下一批指针

**P7-L 完成后**：按审计 §7 队列，剩 `P7-D`（B2+B3 前端 Mock / 契约文案）、`P7-E`（B4+B6）、
`P7-F`（A3 阈值裁决后回填）、`P7-G`（A7 三条遗留）、`P7-H`（A5 升级+回滚演练，**需 bump 1.7.0 与第二见证者**）、
`P7-I`（A4 L2 端到端）、`P7-J`（B5 私钥处置，**纯人工**）、`P7-K`（A8，修法 ③ 已裁决）、`P8-Release`（A6 终审）。
⚠️ 开工前**重跑** §2 的自检——文档会过期，脚本不会。
