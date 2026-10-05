# P6-I · 集成日志（rubric-v1 → rubric-v2：要点分级 core / secondary）

> **日期**：2026-10-05 ｜ **边界文档**：`changes/P6-I/proposal.md`（Non-goals 9 条已冻结）
> **拍板**：用户采纳建议 —— D1 **改** / D2 选**方案 C（要点分级）** / D3 **先做前置验证**
> **一句话**：40 题上 C1 由 **2.94% → 8.82%**（3 遍一致），**但仍未达 10%**；
> 本批更重要的产出是：**再放宽 1 道图侧题就越过阈值** —— 悬崖已被量化，因此**停在 v2 不再松动**。

---

## 1. 前置验证结果（V1–V3）：推算完全成立

| | proposal §4 推算 | 实测 | 偏差 |
|---|---|---|---|
| 现状（rubric-v1） | 2.94% | **2.94%** | **0.00pp** |
| rubric-v2（core-only） | 8.82% | **8.82%** | **0.00pp** |

验收线是 < 1.5pp ⇒ **通过**。验证没花一次 LLM 调用：`p6h-dryrun.json` 里那 40×2 条答案是现成的。

### V2 重判明细（11 条 false，逐条读过答案原文）

| 侧 | 题 | core 是否命中 | rubric-v2 结果 |
|---|---|---|---|
| 图 | Q5 | ✅ 答出「不得超过 36 小时」（漏的是 secondary「依据劳动法第四十一条」） | **翻 true** |
| 图 | Q7 | ✅ 答出「不定时工作制」（漏的是 secondary「已履行审批」） | **翻 true** |
| 图 | Q20 | ❌ 拒答 | false |
| 图 | Q22 | ❌ 只答了「销售经理属已履行审批」——那是 Q7 的事实，不是本题问的审批程序 | false |
| 图 | Q26 | ❌ 自陈未检索到处置时限 | false |
| 基 | Q12/Q35/Q36/Q37/Q38 | ❌ 整题拒答 | false |
| 基 | Q34 | ❌ 答非所问（自陈未见 E004 加班记录，而 OT0001 就是该记录） | false |

⇒ **只有 Q5 / Q7 翻转，基线侧一条都没动** —— 与 proposal §4 预判的机制完全吻合。

### ⚠️ 一条必须说出口的自证局限

0.00pp 的偏差**不足以证明推算可靠**，因为推算与判罚出自同一个人（我）。
单人项目里做不了真正的独立复核。**能站住的只有数学部分**（下一条）；
除此之外，这个偏差只说明「我的判罚前后一致」。

### 🎁 本批最有用的发现：不必重判 80 条，只需 11 条

``core ⊆ expected_points`` ⇒ 一道**现行判为 true** 的题必然覆盖了 core
⇒ 在更宽的规则下**必然仍为 true**。这是**单调性**给出的数学保证，不是推测
⇒ 69 条 true **不需要人工再看一遍**。

> 原本估算「全量要点级重判 ≈ 重做一次 P6-H 判分」，实际降到 **11 条**。
> 这条已写进 `MANIFEST.json` 的 `rubric.monotonicity_note`，供下次换 rubric 复用。

## 2. 落地了什么（4 个文件）

| 文件 | 改动 |
|---|---|
| `data/eval/controlled-qset-v4.json` | 每题新增 `secondary_points`（**16 题带标注，24 题全 core**）；`expected_points` 语义**不变** |
| `data/eval/MANIFEST.json` | `rubric` 升为 **rubric-v2**，并把 v1 的规则连同「它名下的数字 0.0294」登记进 `supersedes` |
| `app/evaluation/dataset.py` | `QuestionItem.secondary_points`（默认空 ⇒ 旧数据集全部按 core，零破坏） |
| `tests/test_evaluation_dataset.py` | 新增 `test_secondary_points_are_a_proper_subset_of_expected` |

**数据设计为什么向后兼容**：`expected_points` 保持「全部要点」的原义，另加 `secondary_points`
（`core = expected_points − secondary_points`）⇒ loader、既有测试、判分流程一行都不用改。

**新测试挡两类静默事故**：
1. `secondary ⊆ expected` ⇒ 防止把不存在的要点写进去（判分人对着假清单判）；
2. `secondary ≠ expected` ⇒ 防止某题全标 secondary ⇒ **没有 core ⇒ 任何答案都判对**，等于偷偷删题。

## 3. live 实测（真图 + 真 LLM + 真 PG + 真 embedding，3 遍）

| 遍次 | value | graph | baseline | corpus_layer | provenance.rubric | verdict |
|---|---|---|---|---|---|---|
| r1 | **0.08823529** | 0.925（37/40） | 0.850（34/40） | L2 | `rubric-v2` | FAIL |
| r2 | **0.08823529** | 0.925 | 0.850 | L2 | `rubric-v2` | FAIL |
| r3 | **0.08823529** | 0.925 | 0.850 | L2 | `rubric-v2` | FAIL |

## 4. ⚠️ 改 rubric 没能让 C1 达标，而悬崖已经量化

```
距 10% 阈值：rubric-v1 还差 7.06pp ⇒ rubric-v2 还差 1.18pp（仍未达标）
再翻 1 道图侧题 ⇒ graph 38/40 = 0.95，C1 = 11.76%  ← 越过阈值
```

⇒ **从这里往前每多放宽一道题，就越接近「为达标而调刻度」**。本批**停在 rubric-v2**，
剩下的差距应当靠**提升图侧能力**去补，而不是靠判分。

### 剩下的 3 道 false 恰恰是「该拿来修产品」的那类

图侧剩下的三条形态一致，都是**长条款里的某个特定 span 没被召回**：

- Q20「月标准工时 174 小时」——明文在 `worktime-system-rules` 第二章第二节第六条；
- Q22「须经劳动行政部门审批」——明文在 `worktime-system-rules` 第二章第三节第十条；
- Q26「高等级预警 5 个工作日内处置」——明文在 `overtime-and-comp-off` 第四章第十二条。

⇒ 三条图侧都自陈「没检索到」，而 **dense 侧恰恰全都答对了**。其中最讽刺的是 Q22：
图侧拿 Q7 的事实「销售经理已履行审批」去答 Q22 的程序问题（答非所问），dense 侧直接给出制度条文。
**这是召回问题，不是计分问题** —— 改 rubric 对它无能为力。

## 5. Non-goals 核销

| # | Non-goal | 是否守住 |
|---|---|---|
| 1 | 不校准阈值 | ✅ 阈值仍 10% provisional，属 ⑤ |
| 2 | 不改增益公式 | ✅ 仍是 `(图 − 基) / 基` |
| 3 | 不动题面 / 题组成 | ✅ 40 题、题面、`should_refuse` 一字未动 |
| 4 | 不动 C2 等其它判据 | ✅ |
| 5 | 只改 rubric 第 ② 条 | ✅ 第 ①③ 条原样保留 |
| 6 | **不为达标而放宽** | ✅ 见 §4，停在 v2 不再松动 |
| 7 | 不顺手修 H6 403 / 入图器自检 / P7-B / G-12 / MANIFEST 语料统计 | ✅ 一个没碰 |
| 8 | 不改检索 / prompt / 拒答判定 | ✅ 三条 span 缺陷**只登记**（见 §4） |
| 9 | 不许「既改计分又选题」 | ✅ 题集零改动（只加了分级字段） |

## 6. 门禁

```
pytest（真 Neo4j / 真 PG + app_rls）   969 passed / 3 skipped / 3 xfailed   ← 968 ⇒ +1，0 回归
ruff check .                           All checks passed!
ruff format --check .                  232 files already formatted
check_seams.py                         ERROR 0 / WARN 0 / OK 10
export_openapi.py --check              [OK] 契约零 diff
check_session_drift.py                 S1 读到 changes/P6-I/proposal.md 的 9 条边界
```

## 7. 收尾三问（自答）

1. **有没有"顺便做的"？** 有一处**超出最小改动**但必须说：给 loader 加了 `secondary_points` 字段。
   没有它，那条新测试读不到数据就成了摆设（典型的假绿）。题面、阈值、判据公式**都没动**。
2. **有没有为躲坑而绕路的实现？** 没有。唯一一次"看起来能偷懒"的机会是跳过 69 条 true 的重判，
   但那不是偷懒——是**单调性**给出的保证，且我把理由写进了 MANIFEST，下次换 rubric 可复核。
3. **验收是真跑还是读代码？** 全部实测：3 遍 live C1（真图 + 真 LLM + 真 PG + 真 embedding），
   11 条 false 逐条对着答案原文重判。

## 8. 遗留（已登记，本批不碰）

| # | 事项 | 归属 |
|---|---|---|
| 1 | 图侧在「长条款特定 span」召回弱于 dense（Q20 / Q22 / Q26）⇒ **这是当前 C1 距阈值 1.18pp 的真实来源** | 被测链路，须另开批次 |
| 2 | `expected_points` 粒度不均（n = 1~4）⇒ 二元计分下题权重不等 | §3.1 已提出，建议独立于 rubric 处理 |
| 3 | MANIFEST 语料统计过期（224 / 15 vs 实测 1329 / 25） | ③ 入图善后 |
| 4 | H6 引用回溯 403 / 制度入图器自检恒 FAIL / P7-B / G-12 | P6-D/E 遗留 |
| 5 | 判分跨 run（D3） | 本次 3 遍一致，非保证 |
