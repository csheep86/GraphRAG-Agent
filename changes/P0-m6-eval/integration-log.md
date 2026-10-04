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

### L10（E3.5 后续）**实测结论 + P6 开工前待裁清单**（2026-10-03）

#### 实测（用户要求「实测后再定」）

| 类 | 判据 | 实测结果 | 结论 |
|---|---|---|---|
| **A** | **C2-a / C2-b** | **2.72 秒**，**零 token**，出真值 `recall=1.0000` / `fpr=0.0000`（`PASS(provisional)`） | **进 CI 成立** ⇒ 已登记 **G-25** |
| **B** | C2-c / 多跳 | ⚠️ **未实测** | 见下 |

- **B 类为什么没测**：当前 PG `documents=0` / `kg_versions=0`（见 **L7**），且**未起 backend 服务、无 LLM key**
  ⇒ 现在跑出来的数**没有意义**（空库问答 ⇒ 要么全拒答、要么报错，会得到**假绿或假红**）。
  守 **R-9**：宁可登记"未实测"，**不拿空库跑出来的数去定节奏**。
- ⇒ **「B 类留证节奏」现在仍不能定**：须在**有语料 + 链路可用**之后实测一次（耗时 / token / 波动），
  才定得了是"每周"还是"每里程碑"。**这是 P6 开工后第一步要补的实测**。

#### P6 开工前待裁清单（排序 = 建议的裁决顺序）

| # | 待裁项 | 为什么它阻塞开工 | 要裁什么 |
|---|---|---|---|
| ~~**1**~~ | ~~**A1：RAG 基线的定义与实现归属**（最硬）~~ ✅ **已裁（2026-10-03）** | C1「图谱增益 ≥10%」的**分母不存在**，而它是 P6 出口判据第 3 条的**第一项** ⇒ **不裁 A1，P6 无法收口** | ✅ 已裁：**唯一变量 = 检索方式** + **基线 = 向量检索 dense top-k**（不以 BM25 为主，防刷绿）+ **分数 = 答对率** + **归属 P6 开工第一步**；全文见 **L10-A1** |
| ~~**2**~~ | ~~**A8：语料规模缺口**~~ ✅ **已裁（2026-10-03）** | 8/60/30/9 vs spec 的 200/500/100/20 ⇒ 不裁，P6 全量判据**只能停在 provisional**，"召回 ≥0.80 / 误报 ≤0.15"**不得宣称达标**（`demo/affiliation/README.md` §5 已写明不宣称） | ✅ 已裁：**扩标、不改 spec** + **补统计口径（判定用置信界）** + **语料分层（算法层 / 端到端）**；全文见 **L10-A8** |
| ~~**3**~~ | ~~**A6 + L8：C2-c 分母是否含拒答**~~ ✅ **已裁（2026-10-03）** | 矩阵字面分母是"总答案数"，而现脚本**排除拒答**；**L8** 的 Q8 拒答误伤与它**直接耦合**——裁"含拒答"则 11/14 = **0.786 < 1.00** ⇒ **触发 F3，MVP 直接 NO-GO** | ✅ 已裁：**分母 = 排除拒答**（不改行为）+ **补输出含拒答档** + **拒答误伤立独立判据（当前 FAIL，归 P6 必修）**；全文见 **L10-A6** |
| ~~**4**~~ | ~~**"独立环境"的定义**~~ ✅ **已裁（2026-10-03）** | P6 纪律是「独立环境留证 + 内部当第一个客户」，不定义 ⇒ 这条纪律**落不了地** | ✅ 已裁：**交付演练环境 = 从交付物（固定 tag 镜像）部署、非从源码起**；独立度取**(b) 独立 compose + 独立卷/端口/.env**；**执行人 ≠ 写脚本的人**（一人执行一人见证）；留证落 `docs/drills/`；术语与 G-9 的"图谱验证环境"**分流**；全文见 **L10-ENV** |
| 5 | **A3：多跳判分**（开工后裁，📌 **但不得拖到收尾**） | 未判分 ⇒ 多跳答对率恒 `UNKNOWN`（**不是 0**） | 📌 **落点已定（2026-10-03，见 L12）**：**P6 第一步产出答案后立刻裁**（判分要人、要排期，拖到收尾 = 没人判或赶工判）；前置 = 答案产出；裁**谁判 + rubric 定稿**。⚠️ 不得因未判分就当 0 或当已通过 |
| 6 | **TBD-7 收敛口径**（开工后裁） | 阈值已有 provisional 32 000，但"多少样本实测才算收敛"未定 ⇒ 一次 `--calibrate` 就被当成收敛 | 📌 **落点已定（2026-10-03，见 L12）**：**与 G-25 同批、由同一次实测定**；判据形态 = **连续 N 次 `--calibrate` 相对波动 < X%** 才算收敛（**一次 calibrate 不得算收敛**）；N / X 数值由人裁 |
| 7 | ⚙️ **非裁决、是前置依赖** | P5-M6 未交付 `cost_metrics` + 增量重算 ⇒ C3-a / C3-b **不可能出数**（不是裁决能解决的） | —— |

#### L10-A1 ✅ **A1 裁决：C1 的 RAG 基线**（2026-10-03）

> **为什么它排第一**：**基线越弱，增益越高。** C1 = `(图谱 − 基线)/基线 ≥ 10%` 是**相对指标**，
> 而基线可自由选 ⇒ 选一个足够弱的基线就能刷出 >10% ⇒ **C1 变成可被操纵的判据**。
> 这与 **R-9「恒绿失效」**同源：判据存在，但**绿不绿由选基线的人决定**。
> ⇒ 所以裁决的第一原则**不是"选哪个算法"**，而是**先把除检索方式外的所有变量钉死**，
> 让增益**只能**归因于检索方式。

**裁决条款**

1. **共因冻结（唯一变量 = 检索方式）**：两侧**同 chunk 池**（同文档 / 同切分 / 同 chunk id）／
   **同 `k`**（喂给 LLM 的 chunk 数）／**同生成模型与温度**／**同 prompt 版本**／**同问题集与判分口径**（A3）。
   *依据*：**G5 只约束了「同数据集 / 同问题集 / 同标注口径」，没有约束基线本身**（proposal §6 A1 原文）⇒ 本次补足。
2. **基线检索 = 向量检索（dense top-`k`）**；**不以 BM25 为主基线**——BM25 在中文长文档上偏弱 ⇒
   基线分低 ⇒ 增益虚高 ⇒ **刷绿**。BM25 只作**敏感性对照**，不作判据。
3. **分数 = 受控问题集上的答对率**：矩阵 §5.1 C1 行**只写了 `(图谱 − 基线)/基线`，没写"分数是什么"**；
   本次按 fixture 的 `graph_accuracy` / `baseline_accuracy` 补定。
   ⚠️ **连带成本**：基线侧也要**人工判分**（A3）⇒ **判分工作量翻倍**。
4. **防刷绿三条**：① **基线分必须落盘**（只落增益则 `(图谱−基线)/基线` 无法复核）；
   ② **`baseline_spec` 进报告**（检索方式 · `k` · 模型 · prompt 版本 · chunk 池版本）；
   ③ **反向守卫**：基线侧 `k` **不得小于**图谱侧、且**不得**换模型或换 prompt（单测钉住）。
5. **归属 = P6 开工第一步**（与 G-25 的 `neo4j` service 并列）；**不归 P5**——基线检索不是产品功能，
   客户不会用它，放 P5 等于让功能批次背一个评测专属实现。
6. **G5 声明**：基线是**项目内自建**向量基线，**非客户现有系统** ⇒ 增益**只对该基线成立**，须写进 release notes。

**订正（不粉饰）**：`BaselineRunner` 协议**并未建立**（`backend/` 内零匹配）——
proposal §6 写的是"出 `BaselineRunner` 协议 + fixture 基线"，实际**只落了 fixture 数据文件**。

**P6 开工时照此执行**：向量检索基线实现 + 双侧判分 + `baseline_spec` 落报告 + 反向守卫单测。

#### L10-A8 ✅ **A8 裁决：C2-a / C2-b 的语料规模**（2026-10-03）

> **最硬的发现不是"规模小"，而是"统计上根本判不出"**：
> 现有 **9 组** gold 测出 1.00，直觉上"满分 ⇒ 达标"。但
> **9/9 的 95% 单侧置信下界 = `0.05^(1/9)` ≈ 0.717 < 0.80**（Clopper-Pearson **精确**值）
> ⇒ **即便观测到满分，统计上也支持不了「召回 ≥ 0.80」**。
> 同理 **误报 0/9 的上界 = `1 − 0.05^(1/9)` ≈ 0.283 >> 0.15** ⇒ 完全不支持「误报 ≤ 0.15」。
> ⇒ 这不是"精度差一点"，是**样本量根本不足以判定该判据**。

**裁决条款**

1. **扩标，不改 spec**：spec §3 验收 6 的 200 合同 / 500 发票 / 100 凭证 / **20 组植入**保持不变——
   改小 = 放宽验收标准 = 拆护栏（§8 表格 ❌ 那类）。植入 **20 组 = 五类疑点 × 每类 ≥4 组**
   （现有 9 组已覆盖五类：`shared_legal_rep` / `shared_address` / `shared_phone` / `cycle` / `amount_mismatch`）。
   ⚠️ **须新写语料生成器**：`demo/affiliation/` 现**只有 5 个手工 CSV、无生成脚本** ⇒ 扩量的真实成本在此。
2. **补统计口径（本次最关键）**：报告**必须输出 `n` 与 95% 单侧置信界**，
   **判定用界，不只用点估计**。spec 的点估计门槛保留（<16 组即 FAIL），
   但**要宣称达标还须界达标**：

   | 判据 | 用哪一侧 | 扩到 20 组后，实测须满足 |
   |---|---|---|
   | **C2-a 召回 ≥0.80** | **下界** | 须命中 **≥19 组**（19/20 下界 ≈**0.82** ✓）；**16/20 的下界仅 ≈0.62 ✗**；18/20 ≈0.75 ✗ |
   | **C2-b 误报 ≤0.15** | **上界** | **误报必须 0 条**（0/20 上界 ≈**0.139** ✓）；**1 条即不成立**（1/20 ≈0.18 ✗） |

   ⇒ 这条把「**踩线达标**」机械地挡在外面——**卡在 0.80 / 0.15 上通过，统计上不成立**。
3. **gold 植入必须"在文本中有体现"**：现 gold 是**从 CSV 结构化字段推导**出来的
   （`legal_rep_id` / `address` / `phone` 相等、持股边、三表金额）⇒ 检测算法读的是**同一批字段**
   ⇒ 命中是**必然的** ⇒ 现在的 1.00 测的是「**推导一致性**」，**不是**「发现隐藏关联的能力」。
   ⇒ 扩标时植入的关联必须同时有**文本证据**（合同 / 发票正文），否则测的仍是"读字段"。
4. **语料分层（不许混）**：
   - **L1 算法层**：合成语料扩至 200/500/100/20 ⇒ **判 C2-a / C2-b**（忠于 spec 判据）。
   - **L2 端到端**：真机文档走 M2 抽取 ⇒ 小样本，**只留证与声明，不作达标判据**（规模不足以判）。
   - *依据*：`contracts.csv` 是 **PDF 合同的替身**——`demo/affiliation/README.md` 明示
     "只验算法层、不验 PDF 抽取"，spec §4.6.6 / **S9.12-1** 已登记该偏离。
   - 报告须带 **`corpus_layer`** 字段标明是哪一层。
5. **归属 P6**：新写生成器 + 20 组植入（含文本体现）+ 真机小样本。
6. **G5 声明**：L1 是合成语料 ⇒ 须写明「仅验证算法层，**未经端到端验证**」。

**禁止**：❌ 用小样本（9 组）的 1.00 宣称达标／❌ 改 spec 规模／
❌ 推导式 gold 冒充文本埋藏关联／❌ 把 L1 算法层结果说成端到端。

> **订正（2026-10-04，P6-A 实算，不改动上面 L10-A8 的裁决条款）**：
> 上表里的置信界是**近似值**，与 **Clopper-Pearson 精确值**不符（精确实现见
> `backend/app/evaluation/stats.py`，单测 `tests/test_eval_corpus_a8.py`）：
>
> | 观测 | 上表（近似） | **精确值** | 后果 |
> |---|---|---|---|
> | 19/20 下界 | ≈0.82 ✓ | **0.7839 ✗** | **19/20 并不支持召回 ≥0.80**，20 组须 **20/20 全中** |
> | 18/20 下界 | ≈0.75 | 0.7174 | — |
> | 16/20 下界 | ≈0.62 | 0.5990 | — |
> | 1/20 误报上界 | ≈0.18 | **0.2161** | 同样更严（误报仍须 0 条） |
>
> ⇒ **真实门槛比上表更严**。裁决的**方向完全正确**（判定用界、误报必须 0 条），
> 只是数值偏乐观。**P6-A 的实测恰好是 20/20 + 0 误报 ⇒ 结论不受影响**（下界 0.8609 / 上界 0.1391）。

#### L10-A6 ✅ **A6 + L8 裁决：C2-c 的分母是否含拒答**（2026-10-03）

> **这个裁决直接决定 MVP 是不是 NO-GO**，所以先把数字摆出来：
> 实测 **14 题 / 11 条作答 / 3 条拒答**（其中 **2 条是预期拒答的库外题 Q13 / Q14**，**1 条是误伤 Q8**）。

| 口径 | 算式 | 值 | 对 C2-c（**硬约束 = 1.00**） |
|---|---|---|---|
| **排除拒答**（现脚本） | 11 / 11 | **1.00** | ✅ PASS |
| **含全部拒答**（矩阵字面"总答案数"） | 11 / 14 | **0.786** | ❌ **触发 H12 反证 F3 ⇒ MVP 直接 NO-GO** |
| 折中：只排除"预期拒答"、误伤仍算 | 11 / 12 | **0.917** | ❌ 同样 < 1.00 ⇒ **同样 NO-GO** |

⇒ **只要分母含任何拒答，C2-c 就不可能 = 1.00** ⇒ **F3 必触发**。

**裁决：C2-c 分母 = 排除拒答**（= 现脚本口径，**不改行为**）

1. **判据本意如此**：C2-c 锚定 M3 §3 验收 2 / M4 §3 验收 4，约束的是「**给出的答案**必须能回溯到原文」——
   **拒答没有给出答案**，谈不上"它的引用"。把拒答塞进分母，是**用一个指标管两件事**。
2. **拒答误伤属于另一条判据**：**L8** 已写明它是 Sprint 6 §5.3 验收第 1 条「**拒答 0 误伤**」的缺口，
   并明确「两条判据**不能互相顶替**」⇒ 让它去拦它该拦的地方。
3. **否则一个缺陷被两个判据重复惩罚**，且直接触发 NO-GO ⇒ 惩罚过重、口径混乱；
   更糟的是会**诱导"为了让 C2-c 绿而去放宽拒答判定"**——那才是最危险的假绿。

**配套三条（必须一起落，否则裁决就成了掩盖问题）**

1. **报告必须同时输出「含拒答」那一档**：`runner.py:240-241` 的 `metric` 与 `strict`
   **两处都传 `include_refused=False`**（只有 `require_span` 是两档）⇒ **含拒答那档从未输出**，
   而 §E1.2 登记的是"两档**都**输出" ⇒ **本批承诺未兑现**（见 **L11(b)2**）⇒ P6 第一步补。
2. **「拒答误伤」立为独立判据**，当前 = **FAIL**（1 条 Q8）⇒ **归 P6 必修**
   （L8 原议独立批次 `P0-refusal` 或并入 M3 检索修复批；本次一并裁决为 **归 P6**，与 L8 建议不冲突）。
3. **release notes 须写明**：C2-c 的 1.00 **不含**拒答题；拒答误伤 1 条**单独计**且**当前未达标**。

**禁止**：❌ 拿 C2-c 的 1.00 去掩盖拒答误伤（**L8**：两条判据不能互相顶替）；
❌ 为让"含拒答档"变绿而放宽拒答判定（那会制造"该拒的不拒"，**比误伤更糟**）。

> ⚠️ **给你的一句话**：若你裁「含拒答」，MVP **立刻 NO-GO**（0.786）。裁决权在你，
> 但后果必须先摆出来。我建议的是**排除拒答 + 把误伤单独立判据**——
> **缺陷没有消失，只是归到了正确的账上**。

#### L10-ENV ✅ **「独立环境」的定义**（2026-10-03）

> **先分流术语**：文档里"独立环境"出现在**两个不同语境**，指的不是一回事，必须分开命名：

| 语境 | 出处 | 指什么 | 本次命名 |
|---|---|---|---|
| **演练 / 安装验收** | `deployment-spec` §6.4 / §10 第 9 项；需求基线 §8「内部当第一个客户」 | 模拟客户拿到的环境 | **交付演练环境** |
| **图谱侧隔离验证** | G-9「CI 无 Neo4j ⇒ 独立环境留证」 | 能起 Neo4j 的临时环境 | **图谱验证环境**（且随 G-25 落地而**作废**——CI 一旦加了 neo4j，就不需要"留证"了） |

**裁决：交付演练环境的定义与判据**

1. **本质 = 从「交付物」部署，不是从源码起**。
   - **判据**：部署命令里**没有 `build:`**，只有 `image: <固定 tag>`（**非 `latest`**），且该 tag
     **就是要交付给客户的那个 tag**。
   - *依据*：**客户拿不到我们的源码** ⇒ 从源码起的演练，**证明不了客户能装上**。
   - ⇒ 这使本项**依赖 DR-A6 / G-19（版本化镜像）**——那是 **P1 的产出**，P6 只是**消费方**
     （G-19 当前仍是 🟡 骨架：`backend` / `frontend` 仍为 `build:` 且无 `image:`）。
2. **"独立"到什么程度**（三选一）：
   - (a) 独立主机 / VM —— 最真，成本最高；
   - (b) **本机上的独立 compose 项目 + 独立数据卷 + 独立端口 + 独立 `.env`** —— **建议采用**；
   - (c) 复用开发机上现有服务 —— ❌ **不算独立**（有开发残留 / `.env` 污染 / 已建好的图）。
   - ⇒ 留证文件须记录 **hostname / 端口 / 镜像 tag / 数据卷名**，否则**无法复核"它独立"**。
3. **谁执行：执行人 ≠ 写部署脚本的人**。
   - 自己写的脚本自己跑验收 = **自证**，是最弱的证据（违反本仓一贯的"不自我认证"纪律）。
   - ⇒ 至少两人：**一人执行、一人见证**，**两人都在留证文件上署名**。
   - *说明*：`deployment-spec` §10 第 9 / 10 项写的是「人工 | DevOps + **客户**」；
     内部演练时"客户"这栏由**见证人**充当，并**标注「内部演练，非客户现场验收」**（§8 ❌ 条款）。
4. **频率**：恢复演练 **每季度至少一次**（§6.4 已定）；安装验收 **每个 GA 候选版本一次**。
5. **留证落点与命名**：`restore-drill-<日期>.md` / `install-acceptance-<日期>.md`，
   落 **`docs/drills/`**（新目录，P6 建）；**必须显式标注「内部演练，非客户现场验收」**。

**禁止**：❌ 在开发机上从源码起服务即宣称"独立环境演练完成"；
❌ 把内部演练对外表述为客户现场验收；❌ 执行人 = 本人且**无见证人**。

### L11 已裁条款的**落地归属** + 两处**当前不一致**（2026-10-03，均归 **P6 第一步**）

> P0-m6-eval **已收尾并提交**，重新动代码要重跑全套门禁 ⇒ 下述**实现项一律不现在做**，
> 但**必须显式登记**（不让它静默存在）。P6 第一步本来就要重写评测层（A1 基线 / A8 扩标 / 统计口径），
> **一起做比拆开做省**。

**(a) 实现清单（随 A1 / A8 裁决一同落 P6 第一步）**
- **A1**：向量检索基线实现 + **双侧判分**（基线侧也要人判）+ `baseline_spec` 落报告 + 反向守卫单测。
- **A8**：新写语料生成器 + 20 组植入（**须含文本体现**）+ 真机小样本（L2）+ 报告 `corpus_layer` 字段。
- **A8 统计口径**：报告输出 `n` + 95% 单侧置信界；**判定用界**（C2-a 下界 / C2-b 上界）。

**(b) 两处「当前不一致」——必须在 P6 开工前知道**

1. **A8 与现有报告标记冲突**：报告给 C2-a / C2-b 标的是 `PASS(provisional)`，
   但按 **L10-A8** 的新裁决，**9 组的下界 0.717 < 0.80** ⇒ 真实语义应是
   「**样本效力不足、判不出**」，而不是 PASS。
   ⇒ 两者**打架**；现在不改代码，**但 P6 补统计口径时须一并订正**
   （建议新增 `underpowered` 语义：`n` 与置信界进报告，界不达标 ⇒ 不得标 PASS）。
2. **A6 的「两档输出」未兑现**：§E1.2 登记的是「`citation_coverage(include_refused=)` 两档**都实现、都测**」，
   但 `runner.py:240-241` 的 `metric` 与 `strict` **两处都传 `include_refused=False`**
   ——只有 `require_span` 是两档 ⇒ **「含拒答」那一档从未被输出过**（`metrics.py` 支持，runner 没调用）。
   ⇒ 属**本批已承诺未兑现**（不是新功能），P6 第一步补一行即可；**见 L10-A6 的两档数字**。

### L12 剩余两条待裁的**落点与前置**（2026-10-03 登记；**不阻塞开工**，但**不许拖**）

> 这两条**不是现在能裁的**——A3 需先有答案、TBD-7 需先实测。本次裁的是**"何时裁 / 前置是什么 /
> 判据长什么样"**，避免它们以"开工后再说"的名义无限期滑走。

**A3（多跳判分）——落点：P6 第一步产出答案后**立刻**裁，不得拖到收尾**
- *为什么不能拖*：判分要**人**，要排期；而多跳答对率是 **C2 的组成部分**。
  拖到收尾 ⇒ 要么没人判、要么赶工判 ⇒ 两种都会产出不可信的数字。
- *前置*：先有**答案产出**（E2 数据集 + live 跑）⇒ 与 **A1 的实现**、**A8 的扩标**同处 P6 第一步。
- *要裁什么*：**谁判** + **rubric 定稿**。
- ⚠️ **禁止**：❌ 因"未判分"就把多跳答对率当成 0，或当成"已通过"——
  它的正确状态恒为 `UNKNOWN`（**不是 0 也不是 PASS**）。

**TBD-7（成本阈值收敛口径）——落点：与 G-25 同批，由同一次实测定**
- *为什么绑一起*：两者要的是**同一次实测**（P6 第一步实测全量 live 的**耗时与 token**）⇒ 别跑两轮。
- *判据长什么样*（建议形态）：**连续 N 次 `--calibrate` 的相对波动 < X%** 才算收敛。
- ⚠️ **禁止**：❌ **一次 `--calibrate` 就算收敛**（当前 provisional 32 000 正是这么来的，
  这是本批已登记的隐患）。
- *留给人裁的*：**N 与 X 的具体数值**（须先看到实测的波动分布才定得了，不拍脑袋）。

### L13 **P6 开工时机评估**（2026-10-03）：**时机不合适 ⇒ 不开工**；并**订正 G-25 的落点**

> ⚠️ **自我订正**：裁完 L10 四条口径后我说过"**P6 现在可以开工**"——**这是错的**。
> 那四条是 **P6 开工后要用的口径**，不是 **P6 能不能开工**的条件。
> 我只核了前者，**没核 P6 这个阶段在整体排期里的前置**。

**为什么现在不能开工（四条，任一条都够）**

1. **阶段顺序**：`changes/P2/tasks.md` 明写执行顺序（2026-10-01 用户确认，**风险优先**）：
   **P2-B → P2.5 → P3 → P2-C → P4 → P5 → P6**。现状：**P2-A 已完成**，
   **P2-B / P2-C 未开工** ⇒ **P6 前面隔着 6 个批次**。
2. **P6 自己的物理前提都不存在**：**L10-ENV** 刚裁定「独立环境 = **从固定 tag 镜像部署**」，
   而 **G-19 实测**：`deploy/docker-compose.yml` 的 `backend` / `frontend` **仍是 `build:`、无 `image:`**
   （骨架挂起）⇒ **连交付物都没有**，「内部当第一个客户」**无从谈起**。
   ⇒ **我裁的定义，反过来卡住了 P6 自己**。
3. **出口判据出不了数**：**C3-a / C3-b 依赖 P5-M6 的 `cost_metrics` + 增量重算**
   （待裁清单第 7 项：这是**前置依赖**，**不是裁决能解决的**）⇒ 现在开工也**无法收口**。
4. **E2 / E4 未做**：恢复演练（DR-E2）、安装验收 10 项脚本化（DR-E4）均 **⏳ 未做**。

**G-25 落点订正：由「P6 第一步」改为「随 P3」**

- 我在 **L9** 写过「G-25 可提到 P6 第一步」——**忽略了 G-9 图谱侧属 P3** 这个事实。
- G-25 与 **G-9 图谱侧**（DR-B11 隔离，归 **P3**）**共用同一个 `neo4j` service + 同一份受控种子数据**
  ⇒ **共用工程项应按更早的那个排** ⇒ **落 P3**，不单开、也不提前到 P6。
- 护栏仍**登记两条**（G-9 / G-25 对应需求不同：隔离 vs 评测，"一条绿了分不清哪半绿"），
  但**工程项只有一次**。

**现在该开什么**：**P2-B（DR-B9 RBAC 三粒度）**
- P2-A 已完成；P2-B **无待裁阻塞**（决策项已于 2026-10-01 全部处置）；
- 开工闸门明确：**首次在 `app/` 引用 `User` 前**须登记 `test_guardrails.py::USERS_CONSUMER_MODULES`；
- 出口明确：**`test_g24_rbac_three_granularity_matrix` 转正**（G-24 由骨架转常驻门禁）。

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
