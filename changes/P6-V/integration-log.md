# P6-V 集成日志（2026-10-09）

- **批次**：[`../docs/delivery-plan.md` §9.2 序 5](../../docs/delivery-plan.md)（P5-J 并入）
- **主题**：M6 剩余读路径切版本继承读 + `agents.py` 接线 + `cost_metrics`
- **起点**：P6-U 收口，CI run **37916431340** 绿，工作区干净
- **状态**：✅ 五项主体已交付 + 真机证据（本地 live LLM）；⏳ 剩余缺口登记在 §9

---

## 1. 本批做了什么（按提交顺序）

| # | 提交 | 内容 |
|---|---|---|
| 1 | `feat(kg)` | 五条读路径切继承读（`fetch_all_subgraph` / `fetch_entity_detail` / `fetch_anchor_entity_ids` / `fetch_document_subgraph` / `fetch_reasoning_path`）+ `agents.py` 检索接线 + `documents.py` 图谱读 |
| 2 | `feat(rules)` | 考勤异常两条路径（`list_attendance_anomalies` / `explain_attendance_anomaly`）+ `rules/attribution.py` 六条 Cypher + 制度条款同源 |
| 3 | `feat(cost)` | `cost_metrics` 表 + 迁移（含 RLS）+ 服务 + 路由 501→200 + `COST_RATIO_ALERT_THRESHOLD` |
| 4 | `docs(adr,spec)` | ADR-0008 §7 清单 / specs/m6 §10.1.1 状态表回登（**独立提交，不混代码**） |
| 5 | `fix(eval)` | C3-a / C3-b 的 `blocked_by` 换成真实缺口 + 探针脚本 |

## 2. ADR-0008 §7：**7/7 已切**（回登表在 §7，原状态行保留）

| 路径 | 切换方式 | 判据用例 |
|---|---|---|
| `fetch_all_subgraph` | 服务层自建视野 | `test_all_subgraph_reads_the_whole_graph_after_a_rename` |
| `fetch_entity_detail` | 同上 | `test_entity_detail_reads_a_node_that_only_lives_in_the_old_version` |
| `fetch_anchor_entity_ids` | 同上（接上 `resolve_anchors` 早留的 `version_view`） | `test_anchor_fallback_finds_a_node_only_present_in_an_older_version` |
| `list_attendance_anomalies` / `explain_attendance_anomaly` | 三处共用同一视野 | `test_anomaly_paths_still_see_employees_outside_the_corrected_subgraph` |
| `fetch_document_subgraph` | 同上 | `test_document_subgraph_reads_chunks_from_the_old_version_and_the_corrected_entity` |
| `agents.py` 检索 | `_execute_query` 一路传 PG 会话 | 本批探针（live）+ 既有 smoke |
| `documents.py` 图谱读 | `db=session` | 同上（`test_graph_and_agent_routes`） |

**每条新用例都带「改前 vs 改后」对比**（改前 = 不传 `db` ⇒ `_read_view` 的两条兜底退单版本），
不是"切完即宣称"。

## 3. M4 端到端真机证据（本地 live LLM，**不进 CI**）

跑 `uv run python ../changes/P6-V/probe_m4_end_to_end.py`（有 `LLM_API_KEY`）：

```
[INFO] org_id=00000000-...-0001 kg_version=attendance-demo-v1
[OUT]  refused=False route=m3_graphqa
[OUT]  citations=['chunk-4585941b282e', 'chunk-1d9ec98da373', 'chunk-d3a412efdf55', ...]
[OUT]  token_usage=prompt_tokens=28545 completion_tokens=559 total_tokens=29104
[OUT]  answer_head='张伟（E001）2026-10-16 ... 出差状态与工单 BT-2026-0'
[COST] total=29104 doc_count=5 single_doc_cost=5820.80
```

两条同时出数：① 问答吃到继承读、给出带引用的答案；② token 真的落到了 `cost_metrics` 当日行。

## 4. 成本：建表 + 迁移 + 端点真实现

- **表**：`cost_metrics`（`models.py::CostMetric`，RLS 迁移 `df5ec5c9e1b1`，
  `tenant_isolation` 策略；G-26 表清单机械核对通过）
- **迁移真机可用**：本地 `alembic upgrade head` 实跑成功——在此之前 dev 库确实缺这张表，
  探针当场报错把它揪了出来（**有价值的一次报错**：本地 dev 库靠 `create_all`，
  与迁移相差一张表，CI 的迁移基线测试看不见这个缝）
- **端点**：`GET /api/v1/cost/dashboard` 501 → 200（默认区间 = 含今天共 30 天）
- **写入**：唯一写入方是 M3 问答（`agents.py` 第 5b 步）；拒答不落（`token_usage` 为 None）
- **聚合口径**：区间**先求和再相除**（用例钉住"不是对按天值再取一次平均"）

## 5. 偏离登记（X-3 / X-4 / X-5，均在 specs/m6 §10.1.1 第 11 行）

1. **X-3**：多一列 `counted_doc_ids`（JSON）——跨请求去重所必需，否则 `single_doc_cost`
   会随提问次数被刷低；
2. **X-4**：区间无数据返回全 0 + 空 `by_date` 并打 warning（契约没有"无数据"语义，本批不改契约）；
3. **X-5**：路由 `summary` / `description` **仍是占位期原文**（写着"恒 501"）——它是契约文本，
   改它必须连 `contracts/openapi.yaml` 与前端 TS 生成物一起提（跨角色，登记给下一批）。

## 6. C3-a / C3-b：**仍 BLOCKED，本批不宣称出数**

报告现在报的是真实缺口：

- `c3_a_single_doc_cost` → 缺 **M2 抽取侧 token 落点**（当前只有 M3 问答在记）
  + **TBD-7 未校准**（`EVAL_SINGLE_DOC_TOKEN_CEILING=32000` 是 provisional）；
- `c3_b_incremental_cost_ratio` → 缺 **增量重算**（`incremental_cost` / `full_rebuild_cost`
  无任何写入方 ⇒ 无分子）。

> "有了表 ≠ 能出数"：这是本批最容易被读错的一句，写在这里压住。

## 7. 门禁读数（本批终点 vs 起点）

| 项 | 起点 | 终点 |
|---|---|---|
| pytest（有图口径） | 1157 passed | **1167 passed / 5 skipped** |
| `ruff check` / `format` | 绿 | 绿 |
| `check_seams.py` | OK 12 | **OK 12（ERROR 0 / WARN 0）** |
| `export_openapi.py --check` | 零 diff | **零 diff**（描述文本刻意未动） |
| `check_startup_readiness.py` | 17/0/0 | 17/0/0（本批未改护栏） |
| 迁移 head | `3f7c1b90ad24` | **`df5ec5c9e1b1`** |
| `check_session_drift.py` | — | S2 提示改动量 1712 行（>600）——**本批确实大**，见 §8 第 3 条 |

### 8.0 ⚠️ CI **第一次是红的**（run `37925914567`，后端 Pytest 作业失败）——照实登记

失败的是本批新增的考勤异常用例，断言内容：

```
AssertionError: assert set() == {'E001'}      # tests/test_version_chain_readers.py:1155
```

- **症状**：「改前形态」（不传 `db` ⇒ 退回单版本）在本机读到 `{"E001"}`，**CI 读到空集**；
- **诊断**：那条断言写的是 `== {"E001"}`，而 E001 的考勤关系是否被增量重建重写进新版本，
  取决于重建的邻居复制口径（本机写进去了、CI 没写）——**它与本用例要判的事情无关**；
- **处置**：改成 `"E002" not in before` + `before < {"E001","E002"}`（把真正要钉的
  "单版本读漏人" 钉住），并补一条 `view.inherits_history` 的场景自检，防止
  「场景没造出来 ⇒ 两条读取结果碰巧一致」把判据架空。**不是放软，是去掉无关耦合**；
- **教训**：写「改前 vs 改后」对比时，**只对比本题关心的那一维**，别把邻居复制口径
  这类实现细节当成不变量钉死。

## 8. 过程中值得一提的四件事（**踩坑不是减分项，藏着才是**）

1. **`ON CONFLICT DO NOTHING` + `rowcount` 会把第二笔整段跳过**：同一天第二次记帐后
   表里只剩第一笔（测试 `assert row.token_usage_input == 300` 报 `100 != 300`）。
   没有就此替库找借口，直接改用 **SELECT FOR UPDATE + savepoint 竞抢**（最多两轮），
   两种结局只有「我建」或「我合」。少计比报错更难发现，这是本批最值钱的一次失败。

2. **`{e_scope}` 占位符撞 Cypher 内联属性图**：Cypher 自身带花括号
   （`{entity_type: 'EMPLOYEE', org_id: $org}`）⇒ `str.format` 直接
   `KeyError: 'entity_type'`。占位符改用 `@@e_scope@@`，理由写进了代码注释。

3. **`conftest.py` 有 autouse 恒空桩**：`fetch_anchor_entity_ids` 默认被打成（**无锚点**），
   真图用例必须挂 `real_graph_read_path` 撤桩。第一次跑锚点用例全绿也可能是在演桩。

4. **本批改动量 1712 行 / 4 提交**（drift S2 报警）：V1 决策允许摊大，但要**逐条独立提交**
   ——五个提交各自自洽、`git show` 能单条回滚。下一次同体量批次建议一开始就拆两批。

## 9. 剩余 / 不许被忘的（传给下一批）

| 项 | 现状 | 归属 |
|---|---|---|
| **X-5** 契约描述文本（写着"恒 501"） | 实现已是真的、文本还是旧的；要改须连 `openapi.yaml` + 前端 TS 生成物一起提 | 下一批（跨角色） |
| `agents.py` 的**证据片段**读取（`fetch_evidence_chunks`） | 未纳入本批（不在 ADR §7 七条内）⇒ 仍是单版本 | P6-W 或独立小批 |
| M2 **抽取侧 token 落点** | 无（langextract 只在日志打印）⇒ C3-a 拿不到真分母 | 下一批 |
| `incremental_cost` / `full_rebuild_cost` 写入方 | 无 ⇒ C3-b 无分子 | 增量重算批次 |
| **跨版本边**（P5H-6） | 仍不连（物理边不存在） | ADR §7 指针 5 |
| **as-of 排序口径** DB / Py 不一致 | 未动（候选 165 行够不着 400 才没触发） | **P6-V1** |
| **P6-T 判分 86 题** | 仍是 `UNKNOWN`（**人是瓶颈**，顺延至项目末期） | 必须传承到每一批 |
| `alert` 表 / R27 / R30 | 有意不做 | P2 遗留 |
<｜hy_place▁holder▁no▁813｜><arg_key:opensource>filePath</arg_key:opensource><arg_value:opensource>d:/AIProject/GraphRAG-Agent/changes/P6-V/integration-log.md