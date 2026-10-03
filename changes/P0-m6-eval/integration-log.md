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

用户问「探测出的漂移要不要改原脚本」——**最终结论 = 撤**（改过一版 `a7495cfd`，已 `git revert` 为 `dd2a56c`）：

- 230 **不是笔误**，是 2026-09-30 那次 `probe_e0_active.py` 的**实测留痕**
  （旁证：`tests/test_langextract_chunks.py` 记「230 chunks → 去重后 205」）；
  把它改成 224 = **伪造那次 probe 的记录**。
- 但它会被**误用**：TBD-7 的阈值推演拿它当分母。
- ⇒ **最终处置（撤）**：脚本**恢复原样**；改为
  ① MANIFEST 立为**单一真源**（补 `documents=15 / entities=2987 / measured_at /
  `is_single_source_of_truth=true`）；
  ② **防误用的警示落在可改处**——`config.py` 的 `eval_single_doc_token_ceiling`
  注释（E3 落地）明写「只准读 MANIFEST 的 224，脚本里的 230 是历史值、不可当分母」。
  **为什么不留那笔**：本批红线明写「不改该脚本」，留它等于用「注释无害」为由放宽红线；
  而目的（防 230 被当分母）已由 ② 等价达成。详见 §9 **L2**。

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

### E3.1 `config.py` 字段 + **消费者**（2026-10-03 落地）

| 项 | 落点 |
|---|---|
| 字段 | `backend/app/core/config.py` → `eval_single_doc_token_ceiling: int = Field(default=32_000, gt=0)` |
| **消费者 ①** | `backend/app/evaluation/runner.py::resolve_cost_ceiling()`（C3-a 阈值与来源） |
| **消费者 ②** | `backend/app/evaluation/runner.py::eval_single_doc_cost()`（判据带出 `threshold` / `threshold_source`） |
| **消费者 ③** | `backend/scripts/eval_acceptance.py::_calibrate()`（打印当前 ceiling + **当场判一次**实测均值 vs 阈值） |
| `.env.example` | 新增 `EVAL_SINGLE_DOC_TOKEN_CEILING=32000`（含 provisional 说明 + 校准命令 + 「230 不可当分母」警示） |

**为什么阈值来源要分两档**（`resolve_cost_ceiling`）：
``Settings`` 分不出「默认值」与「人显式设的值」，而这两者在验收时分量完全不同——
env 显式设置 ⇒ `env-override`（人工裁决过 ⇒ 判定可给真 PASS / FAIL）；
否则 ⇒ `provisional`（⇒ 只给 `PASS(provisional)`，不构成 TBD-7 收敛证据）。
实测两档都验过：`27500 vs 32000 ⇒ PASS(provisional)`、`env=25000 ⇒ FAIL`。

### E3.2 D3 复核：C3-b 阈值**不落 config**
- `metrics.py::COST_RATIO_SIGNIFICANT = 1.00`（来源：矩阵 §5.1「显著 < 1.00」，人工裁决定值）。
- 理由照旧：与 spec §6 的 `COST_RATIO_ALERT_THRESHOLD` 撞名 + **无真实消费者**（无增量重算）
  ⇒ 落 config 即**幽灵配置**。
- 它由 `runner.eval_incremental_cost_ratio` **读取并带进判据** ⇒ 常量**不是孤儿**。

### E3.3 判据接线（不做孤儿脚本）
- `docs/acceptance-traceability-matrix.md` §5.1：新增「**可执行命令**」列（指到
  `scripts/eval_acceptance.py`），8 行状态按本批**实测**刷新（C2-a 1.00 / C2-b 0.00 /
  C2-c 1.00 / 其余 `BLOCKED` / `UNKNOWN` 并写明缺什么）。
- `docs/delivery-requirements-and-guardrails.md` **DR-D10** 行：状态由「⏳ 评测脚本待建」
  ⇒ 「🟡 已建」，依据列回填脚本路径 + 实测数值。
- `docs/dev-doc-status.md`：新增 **§10 评测口径增补登记 A1–A9**（**新章节、只追加**，
  守 **R5**），含每条缺陷的处置与证据路径。

### E3.4 红线复核（**证据**）
```bash
git diff --stat 820e6f57 HEAD -- specs/ contracts/
# ⇒ **空**。spec §3.4 与契约一字未改（本批未新增 / 未改任何端点）
uv run python scripts/check_seams.py        # ERROR 0 / WARN 0 / OK 10（新字段有消费者）
uv run python scripts/export_openapi.py --check   # [OK] 零 diff
```

### E3.5 怎么接进「收尾三件套」与 `check_session_drift.py`
- **收尾三件套**：`uv run pytest -q`（**818**）/ `ruff check` + `format --check` 全过 /
  `check_seams.py` ERROR 0 / `export_openapi.py --check` 零 diff。
- **`check_session_drift.py` 的接线**：本批新增的 `settings.*` 字段 ⇒ 由 **S3** 拦
  （`.env.example` 必须同步）；新增 `app/evaluation/*` 模块 ⇒ 由 **S5** 拦
  （必须被 `scripts/eval_acceptance.py` 真实 import，本批已满足）。
  ⚠️ 跑之前**必须 `git add -N`** 新文件，否则 S5 等于没跑（见 §E1.5）。
- **CI 接线：结论 = **不接**，归 **P6**（本批未做，登记为 **L9**）**。
  我原先的理由是「它不依赖 LLM / 网络 / Neo4j，且幂等」——**这个理由恰好是"不能现在接"的论据**：
  正因为它什么都不依赖，实测 offline 下 **7 条判据全部 `value=null / INDETERMINATE`**、
  **退出码恒 0**（只有 `verdict == FAIL` 才退 1）⇒ 接进 CI 就是**恒绿失效**门禁（**R-9**），
  会制造「CI 绿 = 准入线在拦」的假象——正是开工自检要防的那一类。
  仓内已有同型先例：`check_startup_readiness.py` 正因**恒退 0**被明写为「**只打日志，不做门禁**」。
  落点与两个前置见 **§9 L9**。

---

## §9 — 遗留与差异登记（**照实登记，不粉饰**）

### L1（E1.5）`check_session_drift.py` 对未跟踪文件是盲的
- **现象 / 依据**：新模块已写完，脚本仍回「与 HEAD 之间没有改动」；根因是它只读 `git diff`，未跟踪文件不在 diff 里 ⇒ S5 形同没跑。
- **处置**：每次跑前先 `git add -N <新文件>`（已写进 `tasks.md` 文首）。**修脚本不在本批范围**，仅登记。

### L2（E2.2）chunk 数**数字漂移**：230 vs 224
- **依据**：`scripts/eval_controlled_qset.py` docstring 写「`attendance-demo-v1` 230 chunks」；2026-10-03 实测 Neo4j 为 **224**。
- **处置（已闭环，2026-10-03 定稿 = **撤**）**：原脚本注释里的 **230 原样保留**——
  ① 它是 2026-09-30 那次 probe 的**历史留痕**（旁证：`tests/test_langextract_chunks.py`
  记「230 → 去重后 205」），改成 224 = **伪造那条记录**；
  ② 本批红线（`proposal` §2 Non-goals + `tasks.md`「开工前必读（红线）」第 4 条）
  明写**不改该脚本**。
  我曾改过一版（补指向注释，`a7495cfd`），**已 `git revert`（`dd2a56c`）**——
  越界就是越界：留它等于用「注释无害」为由放宽红线，下次就有先例可援引。
- **防误用改落在可改处**：`config.py` 的 `eval_single_doc_token_ceiling` 字段注释
  （E3 落地）明写「chunk 数一律读 `MANIFEST.json`；脚本里的 230 是历史值、不可当分母」；
  MANIFEST 同步补 `documents=15 / entities=2987 / measured_at / is_single_source_of_truth=true`。
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

### ~~L3（E2.4）演示数据随 PG 容器丢失~~ —— **已被上文「L3（E2.4 → 已闭环）」取代**
- 本节是**当时的开口项**（等待用户裁决），**保留为历史**，勿再按它行动：
  用户已拍板重建 ⇒ 已闭环（见上文 L3 已闭环条目 + §E2.7）。
- 原记录：PG 13 张表行数全 0；`agent/query` 恒 501 ⇒ C2-c / 多跳 / C1 分子 **实测 `UNKNOWN`**
  （不重建、不冒充）。

### ~~L4（E2）C2-a / C2-b 的 gold 实体 id 空间未核对~~ —— **已被上文「L4（E2 → 已闭环）」取代**
- 同样是**当时的开口项**，保留为历史：真机取样后已核对并**发现初版是错的**
  （`supplier_id` 只是节点属性）⇒ 已改为真机 id 空间 + `verified=true`（见上文 L4 已闭环条目）。

### L7（E2.7）PG 元数据：**核心已补；剩余部分登记到「演示 / 换版前」再补**
- **已补（本批）**：`kg_versions` 两条均已 **ready**（`ingest_attendance_csv.py` +
  `ingest_affiliation_sources.py`，**¥0**）⇒ 判据链路恢复（C2-c 实测 **1.00**）。
- **关键实测（反直觉）**：4 份 docx 的 **chunk 从未丢失**——Neo4j 侧
  `attendance-demo-v1` = **224 chunks / 15 docs / 2987 entities**，与"重建"前**一致**。
  丢的只是 **PG 元数据**。PG 现状：`documents` **1 行**（摄入中断留下的行）、
  `kg_versions` **2 行 ready**、PG **无 chunks 表**（chunk 在 Neo4j）。
- **不现在补 docx 的三条理由**：① 问答链路已实测可用（C2-c = 1.00，引用带 `doc_id`）
  ⇒ 对本批任何判据**零增量**；② MinerU 云解析排队极慢（实测 18 分钟只用了 2.8 秒 CPU）
  且要花 LLM 成本；③ 它的收益是 `documents` 表完整（前端列表 / 演示观感），**不是判据**。
- **何时补**：**演示验收前**，或**受控问题集换版（v4）前**——换版要按 active 语料重出题，
  那时才真需要重抽。命令：`uv run python scripts/ingest_attendance_policies.py`
  （脚本有「复用 Document 行」逻辑，可续跑）。
- **恢复清单（PG 容器重建后）**：只需两条 ¥0 脚本即可恢复判据链路 ⇒
  `ingest_attendance_csv.py` + `ingest_affiliation_sources.py`（**无需**重跑 docx 抽取）。

### L8（E2.7）C2-c 实测中的 **1 条拒答误伤**（Q8）—— **不在本批修，按事实登记**
- **现象**：Q8「标准工时制岗位的核心在岗时段是什么时候？」期望回答、**实际拒答**；
  另 2 条拒答（Q13 / Q14）是**预期**拒答的库外题 ⇒ 误伤 **1 / 14**。
- **它属于哪条判据**：**不是** C2-c（引用覆盖率实测 1.00 ⇒ PASS），
  而是 Sprint 6 §5.3 验收第 1 条的「**拒答 0 误伤**」——两条判据**不能互相顶替**。
- **什么时候修**：**立独立批次**（建议 `P0-m6` 之后的 `P0-refusal`，或并入 M3 检索修复批）。
  ① 修它 = 动 M3 检索 / 路由 / 拒答策略 ⇒ **越过本批 Non-goals**（本批只建评测体系，
  不改被测链路）；② 修之前先做 **¥0 取证**（`scripts/eval_controlled_qset.py --diagnose`，
  只复算候选集、不调 LLM）⇒ 先分清是「候选集没召回」还是「闸门 / 阈值把答案拒掉」，
  否则修的是猜的那一个。
- **本批做了什么**：只**按事实登记**（报告 `detail.refusal_mismatches` 可查，含期望值与实际值），
  **没有**顺手改链路。

### L9（E3.5）**判据进 CI**：归 **P6**，且 P6 开工前须先裁决两个前置
- **为什么不现在接**：`--offline` **恒退 0**（`main()` 只有 `verdict == FAIL` 才 `return 1`，
  而 offline 下 7 条判据全 `value=null / INDETERMINATE`，2026-10-03 实测）⇒ 接进 CI 即
  **恒绿失效**（**R-9**），并制造「CI 绿 = 准入线在拦」的假象。
  仓内同型先例：`check_startup_readiness.py` 因恒退 0 被降级为「只报告、非门禁」。
- **为什么不落 P5-M6**：P5-M6 落 `cost_metrics` 只解开 **C3-a 的分母**，但 ① 取值仍需 live；
  ② CI 的 backend job **现在只有 postgres、无 `neo4j` service**（护栏 **G-9** 那条正是"待加"）、
  也无 LLM key ⇒ **到 P5-M6 结束，CI 里的 `--offline` 依旧恒退 0** ⇒ 落点不对。
- **为什么落 P6**：P6 = 运维与评测，出口判据就是 **D10 的 C1–C3 达标**（≥10% / ≥0.80 / ≤0.15 / =1.00），
  且 P6 的纪律是「独立环境留证」⇒ 判据门禁与 E1~E4 同批，不单开批次。
- **P6 开工前必须先裁决的两件事**：
  1. **CI 到底能不能跑 live**：依赖 **G-9**（backend job 加 `neo4j` service）+ LLM 侧取舍
     （注入 key / 录制回放 / 或明写"live 判据只在独立环境留证、不进 CI"）。
     这决定它在 CI 里是**真门禁**还是**只留证**。
  2. **怎样让它成为真门禁而非恒绿**：见下方**裁决建议**——结论是两个前置实为**一件事**。

#### L9 裁决建议（2026-10-03，待裁）

> 取证：`_detect_findings()` 调的是 `AffiliationService().detect(kg_version, org_id, limit=500)`
> ——**只读 Neo4j，零 LLM、零 HTTP**；C2-a/C2-b 被 blocked 的原因是 `mode != "live"`，
> **不是**"没有 LLM key"。CLI 已有 `--criteria` 参数 ⇒ 命令现成：
> `--live --criteria c2_a_hidden_relation_recall,c2_b_false_positive_rate`。

**建议 1：不要按 live/offline 二分，按「是否吃 LLM」三分**

| 类 | 判据 | 依赖 | 建议去向 |
|---|---|---|---|
| **A** | **C2-a / C2-b** | **只吃图**，确定性、**零 token** | **进 CI 作真门禁** |
| **B** | C2-c / multihop | 吃 LLM（`POST /api/v1/agent/query`） | **不进 CI** → P6 独立环境留证 |
| **C** | C1 / C3-a / C3-b | 缺 A1 基线 / 缺 P5-M6 | 等 A1 与 P5-M6，届时再判 |

- **B 类不进 CI 的三条理由**：① LLM 输出**非确定性** ⇒ 门禁 **flaky**；
  **flaky 门禁比恒绿门禁更伤**（随机红会逼人重跑，最后干脆 ignore）；
  ② 每次提交烧 token；③ 得起 backend + 注入 key，暴露面变大。
- **因此：不建议给 CI 加 LLM key，也不建议做录制回放**（录制的响应会过期、维护重、且钉不住能力退化）。

**建议 2：弃掉我原先的「真机快照离线复算」方案——它是劣解**

> 自我订正：上一条 L9 写的「用 9 条真机输出快照当输入，让 C2-a/C2-b 离线可复算」**建议作废**。

- 快照复算的输入是**固化**的 ⇒ 只能拦「**指标函数**被改坏」，
  **拦不住「检出能力退化」**（检测算法变坏了，但喂的还是旧快照 ⇒ 算出来还是旧值 ⇒ 照样绿）。
  ⇒ 那又是一种「**绿，但不代表达标**」的假象，与 §8 表格里 ❌ 的那类同源。
- **正解是真跑图**：CI 起 Neo4j + 导入**受控种子语料** ⇒ 检测算法退化 ⇒ 疑点输出变 ⇒ **真红**。
- ⇒ **建议 1 与建议 2 是同一件事**：不是两个前置，是**一个工程项**。

**建议 3：与 G-9 图谱侧合并做（一次投入，三处收益）**

- G-9 图谱侧在需求基线 **§8 已裁决**：「给 `ci.yml` 的 backend job 加 `neo4j` service
  （现只有 postgres）⇒ 由『独立环境留证』升格为**真 CI 必过**」，
  并明写 ❌「继续以『CI 无 Neo4j』为由停在留证，却宣称已验证」。
- 两者要的是**同一个 `neo4j` service**，且都要**受控种子数据**
  （G-9 要 A/B 两个 org 的数据；L9 要 M4 gold 对应的语料）
  ⇒ **合并为 P6 的一个子项**：加 service → 导入种子数据 → ① G-9 图谱侧转正
  ② C2-a/C2-b 进 CI ③ C2-a/C2-b 成为非恒绿门禁。
- 落点：可**提到 P6 第一步**（它不依赖 P5-M6 的 `cost_metrics`，只依赖"CI 加 neo4j"）。

**建议 4：CI 里的 C2-a/C2-b 只判「不退化」，不判「达标」**

- 语料是 **8/60/30/9 vs spec 的 200/500/100/20** ⇒ 报告里是 **provisional**；
  拿它判"达标"＝用演示语料宣称 spec 达标（正是 §8 ❌ 那类）。
- ⇒ CI 用**基线 delta**（记上次值，跌幅超阈值才红）；**绝对达标线留给里程碑 live 留证**。

**两条必须避的陷阱**

1. **空图陷阱**：CI 的 Neo4j 若不导入数据 ⇒ 检测 0 疑点 ⇒ 召回 0 ⇒ **假红**。
   种子语料必须**受控、可复现**，不能是"某次真机留下的库"。
2. **边界 flaky**：召回卡在 0.80 附近时，微小改动就红 ⇒ 用 delta + 容差，不要拿绝对阈值卡边。

**开工前需实测一次才能定**：全量 live 跑一轮的**耗时与 token** ⇒ 才定得了 B 类留证的节奏
（每周 / 每里程碑）。建议 P6 第一步就是实测并把数字登记，**不要拍脑袋定频率**。
（本次仅给出建议，**阈值与取舍仍由人裁决**。）

- **本批做了什么**：只**按事实登记 + 给出建议**，**没有**接进 CI。

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
