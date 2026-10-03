# F4 · M6 出口判据评测体系 · 任务清单

> 与 [`proposal.md`](./proposal.md) 配套。**批次边界以 proposal §2 Non-goals 为准**。
> 每子任务收尾跑「收尾三件套」（见文末）；**只删 xfail、测试没真通过 —— 不算转正**。
> 事后实测证据与遗留记 [`integration-log.md`](./integration-log.md)（本文件是事前计划，两者不可互相替代）。

**状态（2026-10-03）**：**E1 / E2 / E3 均已完成**（证据见 `integration-log.md` §E1 / §E2 / §E3，pytest 733 → 777 → 814 → **818**）。
⚠️ **E2 实测（第一次）**：重建数据前判据**一个数字都没拿到**（14/14 = 501，PG 演示数据丢失）⇒ 全部 `UNKNOWN` / `BLOCKED`，**未用 fixture 冒充**；
**（第二次，用户拍板重建 + 核对 gold id 空间后）**：**C2-c = 1.00 / C2-a 召回 = 1.00 / C2-b 误报 = 0.00** 拿到真值（详见日志 §E2.7）。
⚠️ **跑 `check_session_drift.py` 前必须 `git add -N <新文件>`**——脚本只读 `git diff`，
**未跟踪文件不在 diff 里** ⇒ 否则它会回「没有改动」，S5 等于没跑（详见日志 §E1.5）。

**开工前必读（红线）**：
- **禁止**改写 `specs/m6-ontology-incremental.md` §3.4（C1–C3 判据原文）——口径缺陷一律登记为 **A1–A7**（proposal §6）；
- **禁止**新增无消费者的 `settings.*` 配置（幽灵配置，上批刚犯）；
- **禁止**把 `BLOCKED` 写成数字（`0.0` 会被读成"召回为 0" ⇒ 误触发反证 F2）；
- **禁止**改动既有 `scripts/eval_controlled_qset.py` 与其 3 条守卫测试。

---

## E1 — 指标口径 + 四态状态机 + 边界单测

> 目标：**先把"怎么算"钉死并测住**，再谈跑出数字（RK-E6：宁可慢，不许省边界）。

- [x] **E1.1** 建 `backend/app/evaluation/` 包：`__init__.py` / `metrics.py` / `criteria.py`
      - [x] `metrics.py`：五个指标的**纯函数**
        - [x] `citation_coverage(answers, *, include_refused, require_span, chunk_prefix)` —— **A6 两档显式参数化**，默认档与现脚本一致（分母排除拒答）
        - [x] `recall(gold, detected, *, match_rule)` / `false_positive_rate(detected, gold, *, match_rule)` —— **A2 匹配口径参数化**（默认 `(head_id, relation_type, tail_id)` 三元组 + 方向敏感 + 保序去重）
        - [x] `graph_gain(graph_score, baseline_score)` —— **A7 零除**：`baseline_score <= 0` 或任一侧缺失 ⇒ 返回 `None` + `reason`，**严禁**返回 `0` / `inf`
        - [x] `single_doc_cost(records, *, rule)` + `dedupe_document_costs` —— **A4 单位** `token/doc`、**A5 去重口径参数化**
        - [x] **并列 / 去重**：`_dedupe` 保序（同键保留首次）+ `_split` 结果按匹配键字典序 ⇒ 确定性
      - [x] `criteria.py`：**四态状态机**
        - [x] `CriterionStatus = MEASURED / MEASURED_PROVISIONAL / BLOCKED / UNKNOWN`（`StrEnum`，`UP042`）
        - [x] `CriterionResult`：`BLOCKED` **不得**携带数字、**必须**带 `blocked_by`（`__post_init__` 结构级禁止，不靠自觉）
        - [x] `provenance` 为**必填字段**（数据集版本 / 语料 `kg_version` / `offline|live` / git hash）
        - [x] `PlaceholderEvaluator(blocked_by=...)` + `CRITERIA` 注册表（重复登记报错）
- [x] **E1.2** 边界单测 `tests/test_evaluation_metrics.py`（**25 条**，每条都是可执行判据）
      - [x] 空集（gold 为空 / detected 为空 / answers 为空）
      - [x] 零除（基线 ≤ 0、无成功记录、分母为 0、未判分）
      - [x] 全召回（recall = 1.0）/ 误报为 0（fpr = 0.0）/ 全覆盖（coverage = 1.0）
      - [x] 并列与去重的确定性（重复项只算一次、方向敏感）
      - [x] 拒答是否入分母两档都测（A6）+ `require_span` 两档
      - [x] 匹配口径三档（triple / entity_pair / canonical_name）结果不同（A2）
      - [x] 去重口径三档（last_success / first_success / sum_all）+ 失败/作废默认不计（A5）
- [x] **E1.3** `tests/test_evaluation_criteria.py`（**19 条**）
      - [x] `BLOCKED` 带数字 / 缺 `blocked_by` / `UNKNOWN` 带数字 / `MEASURED` 无值 ⇒ **构造即失败**
      - [x] `resolve_status` 三条自证线四种组合（缺链路→`BLOCKED`，缺数据集/口径→`UNKNOWN`，语料非终局→`PROVISIONAL`，全绿→`MEASURED`）
      - [x] `judge` 五档：`PASS` / `FAIL` / **`PASS(provisional)`** / `INDETERMINATE` ×2 / `higher_is_better=False`
- [x] **E1.4** 收尾三件套 ✅（详见 `integration-log.md` §E1.3）
      - [x] **S5 实测 ✅ 无孤儿模块**（`tests/` 引用已满足）；⚠️ 本步结论**前提**是先 `git add -N`（见文首警示）；
            E2 建 `scripts/eval_acceptance.py` 后**仍须复跑**确认（RK-E4）

---

## E2 — 受控问题集（版本化）+ gold + 执行器 + 报告

- [x] **E2.1** `backend/data/eval/` 数据集（**版本化，来源写清**）✅ 5 个文件全部落盘
      - [x] `MANIFEST.json`：版本 / 来源语料 / `kg_version` / 标注人 / 日期 / **rubric（A3）** / 脏数据处理口径 / **224 vs 230 漂移登记**
      - [x] `controlled-qset-v3.json`：受控问题集 14 题（12 库内 + 2 库外），与既存脚本**逐字一致**
      - [x] `gold-multihop-v1.json`：6 题，跳数 **2–4**，含 `hop_path`；**全部 `correct=null`**（待人工判分）
      - [x] `gold-affiliation-v1.json`：**9 组** gold（1+1+1+3+3，与 `demo/affiliation/README.md` §3.1 一致），逐条带 `evidence`；**`verified_against_live_output=false`**
      - [x] `baselines/fixture-baseline-v1.json`：**⚠️ 显式 `provided=false`（不含任何基线测量值）**，只给 `self_test` 构造值
- [x] **E2.2** `dataset.py`：加载 + 结构校验（缺字段 / 重复题 / `hops<2` / 空成员 ⇒ `DatasetError`，**不静默**）
- [x] **E2.3** `runner.py`：双模式 + 判据注册表
      - [x] **`--offline`（默认）**：不依赖 LLM / 网络 / Neo4j ⇒ CI 可跑、断网可跑；**不产出判据数字**
      - [x] `--live`：走真实 HTTP（`EVAL_BASE_URL`）；单题失败**收集**而非抛栈（见 E2.7 教训）
      - [x] 7 个判据全部登记：`C_CITATION` / `C_MULTIHOP` 真 evaluator；其余 5 个 `PlaceholderEvaluator`（带 `blocked_by`）
- [x] **E2.4** `report.py`：JSON 报告
      - [x] 必带：`schema` / `git_hash` / `generated_at` / `mode` / 数据集版本 / 每判据 `provenance` / `threshold_source`
      - [x] `--compare`：两次报告 diff（忽略 `generated_at`）
      - [x] **幂等**：同一输入两次运行 ⇒ 报告（除时间戳）**逐字一致**（由测试钉住）
      - [x] **`self_test` 区块单独标 `synthetic: true`**（与判据分区，防演练值被读成测量结果）
- [x] **E2.5** `scripts/eval_acceptance.py`（CLI 入口）
      - [x] `--offline` / `--live` / `--criteria` / `--out` / `--compare` / `--calibrate` / `--judgements` / `--judged-by`
      - [x] **`--calibrate` 只输出建议值（P50/P90/建议 ceiling），绝不改 config / .env**（RK-E7，单测钉住）
      - [x] 报告顶部 + 终端输出「**升为 MEASURED 还缺什么**」清单
- [x] **E2.6** `tests/test_eval_qset_parity.py`：**新 JSON 数据集 == `eval_controlled_qset.QUESTIONS`**（防第二真源，D5）✅ 3 条（题面 / 拒答标注 / `kg_version`）
- [x] **E2.7** 真跑（用户拍板后 **重建演示数据 + 核对 gold id 空间**）⇒ **三条判据拿到真值**
      - [x] **C2-c 引用覆盖率 = 1.00**（11 作答全有引用；请求失败 0）⇒ PASS
      - [x] **C2-a 召回 = 1.00**（gold 9 / 检出 9 / 命中 9）、**C2-b 误报 = 0.00** ⇒ 均 PASS(**provisional**，A8 语料规模不足)
      - [x] 中途照实登记过 `UNKNOWN + 原因`（14/14 501，PG 无 ready 版本），**没有**用 fixture 冒充
      - [x] gold id 空间**初版是错的**（`supplier_id` 只是节点属性）⇒ 改为真机空间 `node_ids` + 共享节点不算成员 + `verified=true`
      - [x] ⚠️ 登记 1 条**拒答误伤**（Q8 期望回答、实际拒答）——属"拒答 0 误伤"判据缺口，不在本批修
- [x] **E2.8** 收尾三件套 ✅（详见 `integration-log.md` §E2.3）：pytest **814**、ruff 全过、`check_seams` ERROR 0、契约零 diff、S5 ✅ 无孤儿

---

## E3 — TBD-7 落 config + 判据接线 + 文档回填

- [x] **E3.1** `backend/app/core/config.py` 新增 **`eval_single_doc_token_ceiling: int = Field(default=32_000, gt=0)`**
      - [x] 注释写死：**单位 = token/文档**（不是元）；**来源**（演示语料推算，provisional）；**非达标线**；校准命令；**+「chunk 数一律读 MANIFEST，脚本里的 230 是历史值、不可当分母」**
      - [x] **消费者明确**（3 处，非幽灵配置）：`runner.resolve_cost_ceiling()`（阈值 + 来源）/ `runner.eval_single_doc_cost()`（判据带出阈值）/ `scripts/eval_acceptance.py::_calibrate()`（打印并**当场判一次**）
      - [x] 阈值来源**分两档**：env 显式设置 ⇒ `env-override`（可真判 PASS / FAIL）；默认 ⇒ `provisional`（只给 `PASS(provisional)`）——实测两档都验过
- [x] **E3.2** `backend/.env.example` 同步（**缺它即 `check_session_drift.py` S3 命中**）
- [x] **E3.3** **D3 复核**：C3-b 阈值**不落** config（无消费者 ⇒ 幽灵配置）；常量 `metrics.COST_RATIO_SIGNIFICANT = 1.00` 写在 `metrics.py` 并注明来源（矩阵「显著 < 1.00」），由 `eval_incremental_cost_ratio` 读取 ⇒ 常量非孤儿
- [x] **E3.4** 判据接线（不做孤儿脚本）
      - [x] `docs/acceptance-traceability-matrix.md` §5.1：新增「**可执行命令**」列（指到 `eval_acceptance.py`）；状态列按本批实测刷新
      - [x] `docs/delivery-requirements-and-guardrails.md` **DR-D10** 行：回填脚本路径与当前状态
      - [x] `docs/dev-doc-status.md`：新增 **§10** 登记 **A1–A9**（**新章节，只追加不重排**，守 **R5**）+ 本批证据路径
      - [x] `integration-log.md` §E3.5 写明怎么接进收尾三件套与 `check_session_drift.py`（S3 / S5 + **必须 `git add -N`**）+ CI 接线建议（登记未做）
- [x] **E3.5** **红线复核**：`git diff --stat 820e6f57 HEAD -- specs/ contracts/` ⇒ **空**（spec §3.4 与契约一字未改）
- [x] **E3.6** 收尾三件套（全量）：pytest **818** / ruff 全过 / `check_seams` ERROR 0 / `export_openapi` 零 diff / 前端零 diff

---

## 出口判据（一句话）

`changes/P0-m6-eval/` 三件套齐备；`uv run python scripts/eval_acceptance.py --offline` 在**断网 / 无 LLM / 无 Neo4j** 下可跑且**两次运行 JSON 报告逐字一致**（除时间戳），报告中 **C2-c = `MEASURED`**、**C3-a / C3-b = `BLOCKED(blocked_by="P5-M6")`**；`EVAL_SINGLE_DOC_TOKEN_CEILING` 已落 `config.py` + `.env.example` 且**有消费者**（`check_seams.py` ERROR 0）；pytest **只增不减**、`ruff check` + `format --check` 全过、`export_openapi.py --check` **零 diff**、前端 `gen:api` + `typecheck` + `lint` **零 diff**。

---

## 收尾三件套（**每个子任务收尾必跑**）

```bash
# backend/
uv run pytest -q                              # 只增不减（基线 733 passed / 3 skipped / 7 xfailed — 开工实测复核后以实测为准）
uv run ruff check . && uv run ruff format --check .   # 不用 Black
uv run python scripts/check_seams.py           # ERROR 必须为 0
uv run python scripts/export_openapi.py --check # 契约零漂移
uv run python scripts/check_session_drift.py   # 报告，退出码恒 0；S1 有 Non-goals / S2 改动量 / S3 配置同步 / S5 孤儿模块

# frontend/（E3 收尾）
npm run gen:api && npm run typecheck && npm run lint
```

## Non-goals 提醒

不实现 M6（7 端点仍 501）／**不改 spec §3.4（只登记 A1–A7）**／不动 ADR 原文／不改契约（零 diff）／
不建 `cost_metrics` 表／不实现产品级 RAG 基线（只出协议 + fixture）／
**不改** `scripts/eval_controlled_qset.py` 与其 3 条守卫测试／不做前端业务改动／不做 P2·P2.5·P3·P4·P6。
