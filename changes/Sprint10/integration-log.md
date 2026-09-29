# S10 批次 A 真机验证记录（证据三元组 / `char_offset` 精确化）

> **日期**：2026-09-29 | **分支**：`feature/sprint-10`
> **环境**：Neo4j 5.26（`kg-poc-neo4j` 容器，bolt 7687 ✅）；**PostgreSQL ❌ 不可用**（本机无 PG 服务 / 无容器，5432 未监听）
> **探针**：`probe_a0_evidence_state.py`（现状勘察）、`probe_a1_span_roundtrip.py`（写读闭环，可复跑）

---

## 1. c0 现状勘察（只读，决定批次范围）

```
:Chunk 355 条：char_start / char_end 非空 355 / 355（INTEGER NOT NULL）；page 非空 30；id 形态 chunk-<12hex> ✅
:Entity 2948 条：confidence 非空 139（4.7%）；char_start / char_end / evidence_span 非空 **0**
Entity 属性键全集：canonical_name confidence created_at date entity_type gate group_id id in_time
                  kg_version labels mention name name_embedding org_id out_time summary trace_id uuid
证据边：HAS_CHUNK 355 / MENTIONS 482；:RELATION 3645 条 confidence 非空 69
```

三条结论直接改写了 plan §17 的范围，详见 [`c0-recon.md`](./c0-recon.md)：
① `:Chunk` 落库**已完成**，不重做；② `confidence` 是**覆盖率 4.7%** 而非"没写"（CSV 派生实体天然无置信度）；③ 真缺口只有一处——**span 在入图时被丢弃**。

---

## 2. A5 写读闭环（真 Neo4j + 真抽取产物）

样本：`doc_id=dbafd407-0bbc-58d2-8355-e7c10c730525`（真实制度文档，17 实体 / 10 关系 / 2 片段）。
写入独立 `probe-span-…` 版本，**跑完即清理**，不污染 active 版本。

```
产物: entities=17（含 span 17） relations=10 chunks=2
写入: BuildStats(entity_count=17, relation_count=10, chunk_count=2, evidence_edge_count=19)
写侧核对: :Entity 总数=17  char_start 非空=17  char_end 非空=17      ← c0 时是 0，现 100%
读侧核对: chunks=2  带 span 的片段=2  span 总数=17
  span 级: chunk-367b8de204be#<提及> → [87, 95)  / len=278  精确命中=True
  回退档: chunk-367b8de204be        → [0, 278)             （+ agent_citation_span_fallback WARNING）
  span 级: chunk-dd8356f65149#<提及> → [437, 439) / len=521 精确命中=True
  回退档: chunk-dd8356f65149        → [0, 521)
结论: span 级精确命中 2 / 2
已清理 probe version: probe-span-20260929T133537Z
```

**验收对照**（proposal §5）

| 验收项 | 结果 |
|---|---|
| `char_end` 进契约 + `gen:api` 零漂移 | ✅ 契约 diff 仅 `Citation`；前端 tsc/lint 通过 |
| `:Entity` 出现 span + 单测钉死"抽取有 ⇒ 入图不丢" | ✅ 真机 17/17；单测 `test_stage2_writes_entity_span_into_graph` |
| `char_offset` 不再恒 0 | ✅ 真机 `[87,95)` / `[437,439)`，均落在 `(0, len(text))` 内 |
| 回退档可复现且不静默 | ✅ `[0, len(text))` + `agent_citation_span_fallback` WARNING |
| 前端按 `[char_offset, char_end)` 高亮 | ✅ 已实现（区间优先，摘录定位退为回退）——**未截图**，见 §4 |

---

## 3. 门禁数字

| 项 | 数字 |
|---|---|
| pytest | **616 passed / 3 skipped**（批次前 611 ⇒ +5） |
| ruff check / format | All checks passed / 169 files formatted |
| 契约零漂移 | `export_openapi --check` OK（diff 仅 `Citation` 两处） |
| `check_seams` | ERROR 0 / WARN 0 / **OK 10** |
| 前端 | `gen:api` → `typecheck` → `lint`（+ prettier）全通过 |

---

## 4. 未验证 / 待办（**不伪装**）

| # | 项 | 原因与后续 |
|---|---|---|
| 1 | **`kg_qa_v4` 是否真让 LLM 输出 `chunk-<id>#<提及>`** | 需 **PG + 真实 LLM**：PG 当前不可用，本批次**未**做端到端问答真机。这是"主档"生效的唯一未证环节——**未证前不得宣称"引用已精确到句"**；后续在 PG 可用时补（或并入批次 F 容器化后的联调） |
| 2 | 端到端问答 `citations[].char_offset` 非 0 | 同上，依赖 1 |
| 3 | 前端高亮真机截图 | 依赖 1~2；当前仅有区间逻辑 + 单测口径 |
| 4 | `:Entity.confidence` 覆盖率 4.7% 的**分层口径**登记进 `dev-doc-status.md` | 裁决 D-E 的落文档动作，收尾时做 |

**已证的是**：写侧（span 进图）、读侧（span 回查）、换算（真数据 `[87,95)` 非占位）、回退（整段 + 告警）、契约与前端类型一致。
**未证的是**：模型是否遵循 v4 的新证据格式——它只影响"精度是否真的提升"，**不影响**正确性（不遵循 ⇒ 回退整段，与改造前一致）。
