# P6-A 集成日志 —— **A8：语料扩标 200/500/100/20 + 统计口径（判定用置信界）**

| 项 | 内容 |
|---|---|
| **批次** | P6-A（P6 开工第一步；与 A1 并列，先做 A8——它**不依赖裁决**且直接解锁 G-25 的达标判定） |
| **日期** | 2026-10-04 |
| **依据** | `delivery-plan.md` §6 第 6 行 L10-A8；`changes/P0-m6-eval/integration-log.md` L10-A8 / L11(b)1 |
| **出口判据** | `proposal.md` §2：① passed 不减；② 新断言反向验证判红；③ 真图实测出真值；④ 全部门禁 |

---

## 1. 门禁实测（**跑出来的**）

| 门禁 | 起跑（P3-E 收束后） | 收束（本批） |
|---|---|---|
| `uv run pytest -q` | **903 passed** | **921 passed / 3 skipped / 3 xfailed**（+18 = `test_eval_corpus_a8.py`） |
| `ruff check` / `ruff format --check` | 双绿 | 双绿（223 files） |
| `check_seams.py` | 接缝 OK 10 | 接缝 OK 10 / ERROR 0 |
| `export_openapi.py --check` | 零漂移 | 零漂移 |
| `check_startup_readiness.py` | — | 无回退（G-25 / G-26 条目不变） |
| `ci.yml` 解析 | — | backend job 的种子步骤改导入 **v2**，门禁步骤加 `--gold v2` |

## 2. 真图实测（本地 Neo4j 5.26，**非打桩**）

| 步骤 | 实测 |
|---|---|
| 生成语料（seed 20261004） | contracts **200** / invoices **500** / vouchers **100** / suppliers 120 / 持股边 68 / 植入 **20 组**（五类 × 4） |
| 导入（`--corpus-dir …/generated --kg-version affiliation-demo-v2`） | **实体 1268 / 关系 1428**，未对齐 0 行（全对齐，见 proposal §4.2） |
| `--live --gold v2` | 召回 **1.0000**（**20/20**），95% 单侧下界 **0.8609 ≥ 0.80** ✓；误报 **0.0000**（**0/20**），上界 **0.1391 ≤ 0.15** ✓ |
| `--live`（默认 v1，9 组） | 召回 1.0000 但下界 **0.7169 < 0.80** ⇒ **UNDERPOWERED**；误报上界 **0.2831 > 0.15** ⇒ **UNDERPOWERED**（**不再**被误标 PASS(provisional)，修掉 L11(b)1 的「报告打架」） |
| `--gate`（v2 基线重设后） | 通过（只判不退化） |

> C2-a / C2-b 走 `AffiliationService().detect()`：**只读 Neo4j、零 LLM、零 HTTP**
> ⇒ 语料与检测都**确定性** ⇒ 可安心断言 20/20 与 0 误报（不是"碰巧一次"）。

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `backend/scripts/gen_affiliation_corpus.py`（新增） | 受控生成器（固定 seed ⇒ 可复现）：200/500/100 + 20 组植入（五类 × 4）；三张单据表加**正文列**；`--check` 自检（规模 / 噪声唯一性 / 三方金额 / 文本证据） |
| `demo/affiliation/generated/*.csv`（新增，入库） | 生成器产出；CSV 行逗号拼接即 `:Chunk.text` ⇒ **正文自动进证据链**（无需改 ingest 的证据逻辑） |
| `backend/data/eval/gold-affiliation-v2.json`（新增） | 20 组，`node_ids` 走图节点 id 空间；`kg_version=affiliation-demo-v2`；`corpus_layer=L1`；每组带 `text_evidence`；**实测核对后**置 `verified_against_live_output=true` |
| `backend/app/evaluation/stats.py`（新增） | Clopper-Pearson **精确**单侧界（纯 Python 二分 + `math.comb`，不引 scipy） |
| `app/evaluation/criteria.py` | 新增 `Verdict.UNDERPOWERED`；`judge(..., ci_bound=)` ⇒ 点估计达标但**界**不达标 ⇒ UNDERPOWERED（**不是** PASS） |
| `app/evaluation/metrics.py` | `findings_recall` / `findings_false_positive_rate` 的 `options` 增 `hit` / `spurious` / `n`（算界要计数，光有比例算不出） |
| `app/evaluation/runner.py` | `RunnerContext.gold_version`（默认 **v1**，换语料必须显式）；detail 增 `n` / `ci_lower` / `ci_upper` / `corpus_layer`；**判定用界**；v2 ⇒ `corpus_is_final=True`（状态升 `measured`） |
| `app/evaluation/dataset.py` | gold 版本化（`v1` / `v2`），未知版本**报错**（不许靠默认值悄悄换语料） |
| `app/evaluation/report.py` | 人读摘要增 `n=[…]` 与 `corpus_layer`（只打 1.0000 不打"9 组下界 0.717" ⇒ 满分会被读成达标） |
| `scripts/eval_acceptance.py` | 新增 `--gold {v1,v2}` |
| `app/evaluation/gate.py` | 基线文件换版 `ci-c2-v2.json`（v1 那份作废删除，留着会被误用） |
| `ci.yml` | 种子步骤改导入 **v2**；门禁步骤加 `--gold v2`；失败摘要同步 |
| 文档 | 需求基线 DR-D10 / G-25 行、`delivery-plan.md` P6 行、`specs/m4-affiliation-detection.md` §4.7.3（**S13：L1 已偿还 / L2 未做**）、`demo/affiliation/README.md` §5 |

## 4. ⚠️ 本批最硬的一个发现：**L10-A8 裁决表里的界值是近似值，偏乐观**

| 观测 | 裁决表（2026-10-03，近似） | **精确 Clopper-Pearson（本批实算）** |
|---|---|---|
| 19/20 下界 | ≈0.82 ✓ | **0.7839 ✗** |
| 18/20 下界 | ≈0.75 | 0.7174 |
| 16/20 下界 | ≈0.62 | 0.5990 |
| 1/20 误报上界 | ≈0.18 | **0.2161** |
| 0/20 误报上界 | ≈0.139 ✓ | 0.1391 ✓（这项一致） |

⇒ **真实门槛比裁决表更严**：20 组必须 **20/20 全中**（下界 0.8609）才支持「召回 ≥ 0.80」，
19/20 **不够**。裁决的**方向完全正确**（判定用界、误报须 0 条），只是数值偏乐观。
已在 `changes/P0-m6-eval/integration-log.md` L10-A8 前**追加订正块**（不改原文条款），
并把精确值钉进单测（`tests/test_eval_corpus_a8.py`）。
**本批实测恰好 20/20 + 0 误报 ⇒ 达标结论不受影响。**

## 5. 反向验证（**逐条判红**）

| 破坏 | 判红 |
|---|---|
| runner 漏传 `ci_bound`（召回） | ✅ |
| runner 漏传 `ci_bound`（误报） | ✅ |
| 去掉 `UNDERPOWERED` 分支（界不达标仍给 PASS） | ✅ |
| 下界算错（恒 `alpha^(1/n)` ⇒ 假绿） | ✅ |
| 上界算错（恒 0 ⇒ 误报永远达标） | ✅ |
| 生成器去掉 `text_evidence` | ✅ |
| 植入组数缩水（20 → 15） | ✅ |
| 噪声唯一性坏掉（地址撞车 ⇒ 误报） | ✅ |

## 6. 未决事项

| # | 事项 | 级别 | 处置 |
|---|---|---|---|
| 1 | **L2 端到端**（真机文档走 M2 抽取）未做 ⇒ 不得对外宣称端到端达标 | 高 | 另批（需真机 + 抽取链路）；报告的 `corpus_layer=L1` 已把它标出来 |
| 2 | **A1**（向量基线实现 + 双侧判分 + 反向守卫）未做 ⇒ C1 图谱增益 ≥10% **仍判不出** | 高 | P6 开工第一步的另一半，另批 |
| 3 | **A6+L8**：`runner` 两处 `include_refused=False`（含拒答档从未输出）+ 拒答误伤 1 条（Q8）未修 | 高 | 另批（C2-c 达标判定相关） |
| 4 | 阈值 0.80 / 0.15 仍是 **provisional**（TBD-7 未校准）⇒ 报告给 `PASS(provisional)` 而非裸 PASS | 中 | 与 TBD-7 收敛口径同批 |
| 5 | 导入 v2 时 `entity_merge_candidates` 写了 **81 行**（名称/地址相似候选） | 低 | 不影响 C2-a / C2-b；登记备查 |

## 7. 复现命令

```bash
cd backend
export NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=ci-graph-pw-2026

uv run python scripts/gen_affiliation_corpus.py --check     # 只自检
uv run python scripts/ingest_affiliation_sources.py --purge \
  --corpus-dir demo/affiliation/generated --kg-version affiliation-demo-v2
uv run python scripts/eval_acceptance.py --live --gold v2 \
  --criteria c2_a_hidden_relation_recall,c2_b_false_positive_rate
uv run pytest -q tests/test_eval_corpus_a8.py                # 19 条
```
