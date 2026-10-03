# F4 · M6 出口判据评测体系 · 实测日志（integration-log）

> **本文件是事后实测证据**，与 [`tasks.md`](./tasks.md)（事前计划）**不可互相替代**。
> 只写"已完成"不写证据 = 没做完。**未跑的章节一律标注「未开工，待回填」，不许预写结论。**

---

## §0 开工前实测（2026-10-03，**只读探测，未改任何代码**）

| 探测量 | 实测方式 | 结果 |
|---|---|---|
| 基线 commit | `git log -1 --format='%h %ad %s'` | **`820e6f57`**（2026-10-02，归档完 `P0-m6-finalization`）；`git status --porcelain` **空** ⇒ 工作区干净 |
| M6 端点实现度 | 读 `app/api/v1/routes/ontology.py` / `cost.py` | **7 个端点恒 501**（`_placeholder`，`detail.blocked_by`） |
| `cost_metrics` 表 | 扫 `app/db/models.py` 全部 `__tablename__` | **不存在** |
| token 是否落库 | 读 `QaLog`（`app/db/models.py:651`）+ `_record_qa_log`（`agents.py:661`） | **`qa_logs` 无 token 列**；token 只进 loguru（`langextract.py::_extract_token_usage`、`agents.py::_extract_token_usage`） |
| RAG 基线 | 全仓 grep `baseline` / `rag_only` / `纯 RAG` / `RAG 基线` | **无任何基线检索实现**（仅命中 `migrations/versions/*baseline*`、`dev.db` 等无关项） |
| 既有评测资产 | 读 `scripts/eval_controlled_qset.py` + `tests/test_eval_qset.py` | **已存在且是真实现**：14 问（12 库内 + 2 库外）、`QSET_VERSION="v3-2026-09-30"`、`QSET_KG_VERSION="attendance-demo-v1"`；**3 条结构守卫测试** |
| M4 疑点链路 | 读 `app/api/v1/routes/affiliation.py` | `POST /affiliation/detect` 等 **4 个端点已可用** |
| 多跳遍历 | S10.1 落地 `:RELATION*1..3` | 已实现（3 跳） |
| 抽取 token 量级（**阈值推算依据**） | 矩阵 §3.4 M2-7 真机实测：`prompt 1733 / completion 66 / total 1799`；`attendance-demo-v1` = 230 chunks（`eval_controlled_qset.py` docstring）；CSV 派生 chunk 约占 77%（`graphs.py` 注释） | 4 份 docx ≈ 53 chunks ≈ **13 chunk/文档** ⇒ ≈ **23.4k token/文档** × 1.35 ⇒ **32 000** |

> ⚠️ **阈值推算的已知不确定性（照实登记）**：若抽取实际是「每文档一次 LLM 调用」而非「每 chunk 一次」，
> 真实量级会掉到 ~2k/文档。⇒ **必须**经 `--calibrate` 实测校准，在那之前任何 C3-a 的 PASS 只算 `PASS(provisional)`。

**基线测试数**：上批归档登记 **733 passed / 3 skipped / 7 xfailed**；本批 E1 收尾**实测 777 passed / 3 skipped / 7 xfailed**
（**+44 = 本批新增**；`777 − 44 = 733` 与上批登记基线**对得上**，且 skipped / xfailed 数量**未变** ⇒ 无减少、无回归）。

**环境事实（照实登记）**：开工时 PG 容器**已不存在**（上批是 `--rm` 起的，上次会话后消失）⇒ 本次重建
`docker run --rm -d --name graphrag-pg ... postgres:16-alpine`（容器 ID `6c0a71781a29…`）。
**没有 PG 就跑不了 pytest**（`tests/conftest.py:72` → `ensure_database("graphrag_test")`，DR-B2）。

---

## §E1 — 指标口径 + 四态状态机 + 边界单测

**结论：完成（2026-10-03）。** 五个指标的**可执行定义** + 四态状态机 + **44 条**边界用例，全部在断网纯函数层跑通。

### E1.1 落了什么

| 文件 | 内容 |
|---|---|
| `app/evaluation/__init__.py` | 包说明 + 分层约定（为何纯函数要独立成模块） |
| `app/evaluation/metrics.py` | 五个纯函数指标：`recall` / `false_positive_rate` / `graph_gain` / `citation_coverage` / `single_doc_cost` + `accuracy`；口径常量 `UNIT_TOKEN_PER_DOC` / `MatchRule` / `DedupRule` |
| `app/evaluation/criteria.py` | 四态 `CriterionStatus(StrEnum)` + `Verdict` + `Provenance` + **`CriterionResult`（构造即校验）** + `resolve_status`（三条自证线）+ `judge`（含 provisional 降级）+ `PlaceholderEvaluator` + `CRITERIA` 注册表 |
| `tests/test_evaluation_metrics.py` | **25 条**边界用例 |
| `tests/test_evaluation_criteria.py` | **19 条**状态机守卫 |

**A2 / A4 / A5 / A6 / A7 的落点**（逐条对应 proposal §6）：

| 登记项 | 落点 |
|---|---|
| **A2** 匹配口径 | `Relation.match_key(rule)`：`triple`（默认，方向敏感）/ `entity_pair` / `canonical_name`；`recall` / `false_positive_rate` 均带 `match_rule` 回传 |
| **A4** 单位 | `UNIT_TOKEN_PER_DOC = "token/doc"`，`single_doc_cost` 返回值**必带** `unit` |
| **A5** 去重口径 | `dedupe_document_costs(rule=)`：`last_success`（默认）/ `first_success` / `sum_all`；失败与作废**默认不计** |
| **A6** 拒答分母 | `citation_coverage(include_refused=)` 两档**都实现、都测**；默认档与现脚本一致；另加 `require_span`（矩阵原文是"含可回溯 span"，现脚本只用 `chunk-` 前缀代理） |
| **A7** 零除/空集 | 五个函数**全部**返回 `None` + `reason`，**无一处**返回 0 或 `inf` |

### E1.2 边界用例清单（**逐条对得上**）

| 边界 | 测试函数 |
|---|---|
| 空集（gold 空） | `test_recall_empty_gold_is_none_not_zero` |
| 零除（detected 空 / 基线 ≤ 0 / 无成功记录 / 分母为 0 / 未判分） | `test_fpr_empty_detected_is_none_not_zero`、`test_gain_zero_baseline_is_none_not_inf`、`test_single_doc_cost_no_success_is_none`、`test_coverage_empty_denominator_is_none`、`test_accuracy_none_when_nothing_judged` |
| 全召回 / 误报 0 / 全覆盖 | `test_recall_full_hit_is_one`、`test_fpr_zero_when_all_detected_are_in_gold`、`test_coverage_full_when_all_answers_cited` |
| 并列与去重（确定性） | `test_recall_dedupe_is_deterministic`、`test_recall_is_direction_sensitive` |
| 拒答两档（A6） | `test_coverage_refused_excluded_by_default_matches_legacy_script`、`test_coverage_refused_included_lowers_result` |
| 匹配口径三档（A2） | `test_recall_match_rule_changes_result` |
| 去重口径三档（A5） | `test_single_doc_cost_dedup_rules_differ`、`test_single_doc_cost_ignores_failed_and_superseded` |
| `BLOCKED` 不得带数字（结构级） | `test_blocked_with_value_is_rejected`、`test_blocked_without_blocked_by_is_rejected`、`test_unknown_with_value_is_rejected` |
| 阈值 provisional 降级（防假绿） | `test_judge_provisional_threshold_downgrades_pass` |

### E1.3 收尾三件套（**数字**）

| 项 | 结果 |
|---|---|
| `uv run pytest -q` | **777 passed / 3 skipped / 7 xfailed**（上批登记基线 733 ⇒ **+44**，skipped / xfailed **未变**，无失败） |
| `ruff check` + `ruff format --check` | 全过（`format` 曾报 4 文件待格式化，已修；`UP042` 两处 `str, Enum` → `StrEnum`，已改） |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 10** |
| `export_openapi.py --check` | **[OK] 与后端模型一致**（本批未动端点 / schema ⇒ 契约零 diff） |
| `check_session_drift.py` | S1 ✅ **8 条** Non-goals / S2 ⚠️ **新增 1060 行 > 600** / S3 ✅ / S4 ✅ / S5 ✅ 无孤儿模块 |

### E1.4 两条必须自答的（脚本拦不住）

1. **有没有顺便做的？** 无。`metrics.py` / `criteria.py` 的每个函数都对应 proposal §4 / §6 的一条需求（A2–A7 或四态）。
   `accuracy` 看起来像多做的，但它是 **C1 分子**与**多跳答对率**共用的判据载体（矩阵 §5.1 两行都要它）⇒ 不是顺手。
2. **有没有绕路实现？** 两处需说明，均**不是**绕路而是硬约束：
   ① `CriterionStatus` / `Verdict` 用 `StrEnum` 而非 `str, Enum` —— `ruff` 的 `UP042` 要求（格式门禁），不是简化；
   ② `judge` 的 `PASS(provisional)` 用**枚举值里带括号的字符串**——刻意为之，让它无法被读成"已达标"。
3. **判据是真跑出来的吗？** 是：上表每个数字都有命令输出；`--check [OK]` / ERROR 0 / 777 passed 均为实测。

### E1.5 ⚠️ 发现：**`check_session_drift.py` 对未跟踪文件是盲的**（已绕过，登记）

- **现象**：跑 `check_session_drift.py` ⇒ 「✅ 与 HEAD 之间没有改动 —— 无需回切」。
  而此时 `app/evaluation/` 两个新模块 + 两个新测试**已经写完了**。
- **根因**：脚本只读 `git diff`（本次改动），**未跟踪的新文件不在 diff 里** ⇒
  **S5 孤儿模块检查形同没跑**（这是"看着绿、其实没验"的同族问题）。
- **本次处置**：`git add -N <新文件>`（intent-to-add）后再跑 ⇒ 才拿到真实的 S1~S5 结论（上表）。
- **登记**：本批每次跑漂移检查前**必须**先 `git add -N`；建议后续把这条写进脚本提示（**不属本批范围**，登记不修）。

### E1.6 S2 自答（1060 行 > 600）

- 1060 行里 **md 三件套 ≈ 700 行**（proposal + tasks + integration-log，本批交付物本身就要求"写清"），
  **代码 ≈ 360 行**（`metrics.py` / `criteria.py` / 两个测试文件）。
- **按 proposal D6 分开提交**：md 三件套一次提交、E1 代码一次提交 ⇒ 单笔提交不超阈值。

---

## §E2 — 受控问题集 + gold + 执行器 + 报告

**结论：完成（2026-10-03）。** 数据集 5 个文件 + 执行器 / 报告 / CLI + 29 条新测试。
⚠️ **但判据一个数字都没拿到**（见 §E2.4）——这是**结论**，不是遗漏。

### E2.1 落了什么

| 文件 | 内容 |
|---|---|
| `data/eval/MANIFEST.json` | 清单 + **rubric（A3）** + 标注人 / 日期 + 脏数据处理口径 + **224 vs 230 漂移登记** |
| `data/eval/controlled-qset-v3.json` | 14 题（12 库内 + 2 库外），逐题带 `source_doc` + `expected_points` |
| `data/eval/gold-multihop-v1.json` | 6 题，跳数 **2–4** + `hop_path`；**全部 `correct=null`**（A3：不自动判分） |
| `data/eval/gold-affiliation-v1.json` | **9 组** gold（shared_legal_rep 1 / shared_address 1 / shared_phone 1 / cycle 3 / amount_mismatch 3），逐条带 `evidence`；**`verified_against_live_output=false`** |
| `data/eval/baselines/fixture-baseline-v1.json` | **`provided=false`（不含任何基线测量值）**，只给 `self_test` 构造值 |
| `app/evaluation/dataset.py` | 加载 + 结构校验（缺字段 / 重复题 / `hops<2` / 空成员 ⇒ `DatasetError`） |
| `app/evaluation/runner.py` | offline / live + 7 判据注册表 + `self_test` + `upgrade_todo` |
| `app/evaluation/report.py` | JSON 报告 + `compare`（忽略 `generated_at`）+ `render` |
| `scripts/eval_acceptance.py` | CLI：`--offline/--live/--criteria/--out/--compare/--calibrate/--judgements` |
| `tests/test_evaluation_dataset.py`（11）、`test_eval_acceptance_cli.py`（9）、`test_eval_qset_parity.py`（3）+ metrics 组级口径（6） | 共 **+29** 条 |

**gold-affiliation 的 9 组是怎么来的（可核查，非拍脑袋）**：
`demo/affiliation/README.md` §3.1 给出植入数（9 组）→ 用 `suppliers.csv` 的
`legal_rep_id` / `address` / `phone` 相等推导出 shared_* 三组的成员 → 用
`shareholders.csv` 的持股边推出 2/3/4 环 → 用 `contracts/invoices/vouchers.csv`
三方金额推出 TR-0002/0003/0004。成员同时登记 `tax_id` 便于与真机 id 空间核对。

### E2.2 开工前探测（**只读**）

| 探测 | 结果 |
|---|---|
| `.gitignore` | `backend/data/eval/` **未被忽略** ⇒ 数据集入库；`backend/reports/` **已被忽略** ⇒ 报告产物不入库（正确分工） |
| Neo4j | 起 `kg-poc-neo4j` 成功；`attendance-demo-v1` **224** chunks、`affiliation-demo-v1` **128** chunks |
| ⚠️ **数字漂移** | `scripts/eval_controlled_qset.py` docstring 写「230 chunks」，**实测 224** —— 已登记进 `MANIFEST.json`，**不改原脚本注释** |
| PG | 本次新建容器；**13 张表全在但行数全 0**（`kg_versions` 0 / `documents` 0 / `qa_logs` 0） |

### E2.3 收尾三件套（**数字**）

| 项 | 结果 |
|---|---|
| `uv run pytest -q` | **814 passed / 3 skipped / 7 xfailed**（E1 收尾 777 ⇒ +29 ⇒ +7（id 空间归一化）⇒ **814**；733 + 81 = 814，skipped / xfailed 未变） |
| `ruff check .` + `ruff format --check .` | 全过（205 files formatted） |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 10** |
| `export_openapi.py --check` | **[OK]** 零 diff（本批未动端点 / schema） |
| `check_session_drift.py` | S1 ✅ / S2 ⚠️ **2584 行 > 600**（含 md + E1 + E2，按 D6 **分提交**）/ S3 ✅ / S4 ✅ / **S5 ✅ 无孤儿模块** |

### E2.4 ⚠️ 真跑 C2-c（**第一次**）：实测 `UNKNOWN`（没有数字）

```
uv run python scripts/eval_acceptance.py --live --criteria c2_c_citation_coverage
  [unknown] c2_c_citation_coverage  value=null  verdict=INDETERMINATE
  blocked_by=链路不可用：14/14 题请求失败（首错：HTTP 501）
              ——常见原因：PG 无 ready 的 kg_version（演示数据未重建）
```

- **根因（已取证）**：后端 `/api/v1/agent/query` 返回 **501**，detail = 「Neo4j 不可用:
  PG `kg_versions` 中无 ready 版本」；实测 PG **13 张表全 0 行**。
  上次会话的 PG 是 `--rm` 起的，演示数据随容器消失；Neo4j 虽仍有图，但 **PG 才是 active 版本的真源**。
- **处置**：**没有**重建演示数据（那要跑 ingestion，属"演示数据重建"，不在本批边界），
  **也没有**用 fixture 冒充实测 ⇒ 判据如实标 `UNKNOWN` + 原因。
- **要拿真值的前置动作**（已写进报告顶部）：重建演示数据
  （`ingest_attendance_policies.py` + `ingest_attendance_csv.py` + `POST /graph/versions/{v}/activate`），
  再重跑 `--live`；多跳还需人工判分（`--judgements`）。

### E2.5 真跑**顺带查出并修掉**的一个自身 bug（第二次跑仍在拦）

- **现象**：修复前，live 模式下单题 HTTP 失败（501）会**直接抛栈**，脚本崩 ⇒ 一份报告都拿不到。
- **为什么严重**：拿不到报告 ⇒ 「链路不可用」无法被表达成 `UNKNOWN`，
  正是"没测出来"最容易被写成"没这事"的入口。
- **修法**：新增 `ask_safe()` 收集失败；全题失败 ⇒ 降级 `UNKNOWN` + `blocked_by`（**不是 0**）。
- **守卫**：`test_live_link_unavailable_is_unknown_not_a_crash`（monkeypatch `ask` 抛 501）。

### E2.6 chunk 数漂移（230 vs 224）的处置：**不改写历史数字**

用户问「探测出的漂移要不要改原脚本」——我的结论是**改，但不是把 230 改成 224**：

- 230 **不是笔误**，是 2026-09-30 那次 `probe_e0_active.py` 的**实测留痕**
  （旁证：`tests/test_langextract_chunks.py` 记「230 chunks → 去重后 205」）；
  把它改成 224 = **伪造那次 probe 的记录**。
- 但它会被**误用**：TBD-7 的阈值推演拿它当分母。
- ⇒ 处置：注释处**补一行**（230 = 历史值 / 当前 224 / 一律读 `MANIFEST.json`），
  并把 MANIFEST 立为**单一真源**（补 `documents=15 / entities=2987 / measured_at /
  is_single_source_of_truth=true`）。

### E2.7 ✅ 用户拍板后：**重建演示数据 + 核对 gold id 空间 ⇒ 三条判据拿到真值**

用户裁决：① **重建演示数据**（成本不考虑）；② **gold id 空间按建议处理**。

#### ① 重建演示数据（实际只缺 PG 元数据）

```
uv run python scripts/ingest_attendance_csv.py          # ¥0，确定性
  → [PG] attendance-demo-v1 -> ready（实体 2625 / 关系 3637）
uv run python scripts/ingest_affiliation_sources.py     # ¥0
  → [PG] affiliation-demo-v1 -> ready（实体 176 / 关系 173）
```

**一个反直觉但重要的实测发现**：4 份 docx 的 chunk **并没有丢**——
丢失的只是 **PG 元数据**（`documents` / `kg_versions` 行数全 0），
而 chunk 在 Neo4j 里一直在（复测 224 chunks / 15 docs，与重建前**一致**）。
⇒ 重跑 docx 抽取（MinerU + LLM）在本次是**冗余**的；我起了一次，
MinerU 侧排队极慢（进程 18 分钟只用了 2.8 秒 CPU）⇒ **停掉**，
未让它并发写图干扰评测。**结论：演示语料不需要"重建"，只需要把 PG 元数据补回。**

#### ② gold 的实体 id 空间核对（**发现初版是错的**）

`AffiliationService.detect(kg_version=affiliation-demo-v1)` 真机输出 **9 条**，
分型与 gold 完全一致，但 **id 空间与 gold 初版不同构**：

| | gold 初版（错） | 真机实际 |
|---|---|---|
| 成员 id | `supplier_id`（S001…） | `SUBJECT:<税号>` / `CONTRACT:<合同号>` / … |
| `shared_*` 的 entities | 2 个主体 | **[主体A, 主体B, 共享节点]**（3 个） |
| `amount_mismatch` 成员 | 主体 | **三张单据**（合同 / 发票 / 凭证） |

⇒ 拿初版比对 ⇒ **恒 0 命中** ⇒ 召回被读成 0 ⇒ 误触发反证 F2。这正是当时置
`verified=false` 不出数的价值（那道闸拦住了一个假结论）。

**处置**（`data/eval/gold-affiliation-v1.json`）：id 空间改为 `graph_node_id`；
每组成员改用 `node_ids`（真机空间）；声明
`non_member_prefixes = [ADDRESS:, PHONE:, LEGALPERSON:]`（**共享证据节点不算成员**）；
`verified_against_live_output = true`；新增 `app/evaluation/affiliation.py`
做归一化（纯函数，7 条单测钉住，含真机 9 条输出快照）。

#### ③ 终值（2026-10-03，`reports/eval/live-*.json`）

| 判据 | 值 | 状态 | 判据 |
|---|---|---|---|
| **C2-c 引用覆盖率** | **1.00**（11 作答全有引用；含 span 亦 1.00；请求失败 0） | `measured_provisional` | **PASS** |
| **C2-a 隐性关联召回** | **1.00**（gold 9 组 / 检出 9 条 / 命中 9） | `measured_provisional` | **PASS(provisional)** |
| **C2-b 误报率** | **0.00**（误报 0 / 检出 9） | `measured_provisional` | **PASS(provisional)** |

- C2-a / C2-b 的阈值**刻意走 provisional**（A8：语料规模 8/60/30/9 不足 spec 的
  200/500/100/20，README §5 自己写明"不宣称召回 ≥ 0.80 / 误报 ≤ 0.15"）⇒
  即便 1.00 / 0.00 也**不给裸 PASS**，防止被读成 spec 验收结论。
- ⚠️ **C2-c 的 1 条拒答误伤**：Q8「标准工时制岗位的核心在岗时段是什么时候？」
  期望回答、**实际拒答**（其余 2 条拒答是预期拒答的库外题 Q13 / Q14）。
  引用覆盖率判据本身仍 1.00；这条误伤是**另一个**判据（拒答 0 误伤）的缺口，
  **按事实登记**，不在本批修（修它 = 动检索链路，属别的批次）。

### E2.8 三条自答

1. **换个人、换台机、断网能重跑？** ✅ `--offline` 不依赖 LLM / 网络 / Neo4j，CI 可跑、已由 9 条 CLI 测试钉住（含幂等）。
2. **有没有把"未完成"写成"完成"？** 没有——计划表里写「C2-c 本批做到 `MEASURED`」，
   实测是 `UNKNOWN`，已在 `proposal.md` **§4.4 逐条对照**改过来；`BLOCKED` / `UNKNOWN` 的 `value` 全为 `null`。
3. **结论是可执行的还是陈述？** 可执行：`eval_acceptance.py --offline` / `--live` / `--compare` / `--calibrate` 四条命令都可复跑，
   数字均来自命令输出（806 / ERROR 0 / 14-of-14 / 224）。

---

## §E3 — TBD-7 落 config + 判据接线 + 文档回填

**状态：未开工，待回填。**

回填时必须包含：① `config.py` 字段与**消费者代码行**（文件:行号）；② `.env.example` 同步行；
③ `check_seams.py` ERROR 0（**settings.* 有消费者**判据）；
④ **红线复核证据**：`git diff --stat specs/m6-ontology-incremental.md` ⇒ **应为空**（§3.4 一字未改）；
⑤ 矩阵 §5.1 / DR-D10 / `dev-doc-status.md` 的回填位置与 A1–A7 新编号；
⑥ 前端 `gen:api` + `typecheck` + `lint` 结果（**零 diff**）。

---

## §9 — 遗留与差异登记（**照实登记，不粉饰**）

### L1（E1.5）`check_session_drift.py` 对未跟踪文件是盲的
- **现象 / 依据**：新模块已写完，脚本仍回「与 HEAD 之间没有改动」；根因是它只读 `git diff`，未跟踪文件不在 diff 里 ⇒ S5 形同没跑。
- **处置**：每次跑前先 `git add -N <新文件>`（已写进 `tasks.md` 文首）。**修脚本不在本批范围**，仅登记。

### L2（E2.2）chunk 数**数字漂移**：230 vs 224
- **依据**：`scripts/eval_controlled_qset.py` docstring 写「`attendance-demo-v1` 230 chunks」；2026-10-03 实测 Neo4j 为 **224**。
- **处置（已闭环）**：原脚本注释里 **230 保留**（那是 2026-09-30 那次 probe 的**历史留痕**，改它等于伪造那条记录），
  改在**该处补一行**：声明 230 是历史值、当前实测 **224**，并指向 `data/eval/MANIFEST.json`
  （**"当前 chunk 数"的单一真源**）。MANIFEST 同步补 `documents=15 / entities=2987 / measured_at`。
- **连带影响**：TBD-7 的 32 000 阈值推演用了「230 × 23% ≈ 13 chunk/文档」，按 224 重算仍约 13 ⇒ 阈值**不变**，但**仍须** `--calibrate` 实测。

### L3（E2.4 → **已闭环**）演示数据随 PG 容器丢失
- **依据**：PG 13 张表行数全 0；`agent/query` 恒 501（无 ready `kg_version`）。
- **处置**：用户拍板重建 ⇒ 跑 CSV / affiliation 摄入补回 PG `kg_versions`（均 ready）。
  **实测澄清**：docx 的 chunk **没丢**（一直在 Neo4j，224 未变），丢的只是 PG 元数据
  ⇒ docx 重抽取是冗余的（MinerU 排队慢，已停）。详见 §E2.7 ①。

### L4（E2 → **已闭环**）gold 的实体 id 空间
- **依据**：真机输出用图节点 id（`SUBJECT:<税号>`），gold 初版用 `supplier_id`（**只是节点属性**）。
- **处置**：gold 改用 `node_ids` + 声明共享节点不算成员 + `verified=true`；新增
  `app/evaluation/affiliation.py` 归一化（7 条单测 + 真机 9 条快照）。详见 §E2.7 ②。

### L3（E2.4）演示数据随 PG 容器丢失 ⇒ live 判据拿不到数字
- **依据**：PG 13 张表行数全 0；`agent/query` 恒 501（无 ready `kg_version`）。
- **处置**：不重建、不冒充 ⇒ C2-c / 多跳 / C1 分子 **实测 `UNKNOWN`**。
- **是否需要用户裁决**：**是** —— 若希望本批拿到真值，需批准「重建演示数据」（会跑 ingestion，涉及 LLM 调用成本）。

### L4（E2）C2-a / C2-b 的 gold **实体 id 空间未与真机核对**
- **依据**：`gold-affiliation-v1.json` 用 `supplier_id`（`demo/affiliation/suppliers.csv`），而真机疑点输出的 id 空间**尚未取样确认**。
- **处置**：数据文件置 `verified_against_live_output=false` ⇒ 执行器**不出数**（避免 0 命中被读成"召回为 0"⇒ 误触发反证 F2）。
- **是否需要用户裁决**：**是** —— 需先跑一次 M4 疑点检测取真机输出样本，确认 id 空间后把该标志位置 `true`。

### L6（E2）改 `MANIFEST.json` 时把 JSON 写坏了（**自己的教训**）
- **现象**：在 `chunks_note` 里写了未转义的英文双引号 ⇒ `json.JSONDecodeError` ⇒ **11 条测试连带变红**（数据集是多个判据的公共上游）。
- **为什么值得记**：数据集文件是**手改的**，而 `ruff` / `pytest` 在提交前**不会**替你验 JSON 语法；
  上游一坏，红的是**下游一片**，很容易误判成"代码写错了"。
- **处置**：修引号 + 加一条 `json.load` 全量校验（5 个数据集文件全部过一遍）再跑测试。
- **待办**：建议后续把"数据集 JSON 语法校验"做成一条常设测试（本批未加，避免再扩范围）。

### L5（E2）新增登记项 **A8 / A9**（见 `proposal.md` §6）
- **A8**：`demo/affiliation/README.md` §5 明示语料规模（8/60/30/9）不足 spec §3 验收 6（200/500/100/20）⇒ **不宣称**召回 ≥ 0.80 / 误报 ≤ 0.15（缺口 S13）。
- **A9**：gold 标注单元与 M4 输出单元**不同构**（疑点是"组"，不是二元组）⇒ 指标层新增组级 `Finding` 单元，与 `Relation` 并存。
- 两者均**未改写 spec §3.4**，只登记。

---

## §10 — 批次收尾

**状态：未开工，待回填。** 收尾时逐条核对 `proposal.md` §8 出口判据，并回答三句自问：

1. **换个人、换台机、断网能重跑吗？**（`--offline` 是否真的不依赖 LLM / 网络 / Neo4j）
2. **有没有把"未完成"写成"完成"？**（`BLOCKED` 是否都是 `null` + `blocked_by`；有没有 `0.0` 冒充数字）
3. **每个结论是"可执行可核验"的，还是只是一句陈述？**（数字是否都带命令输出与来源）
