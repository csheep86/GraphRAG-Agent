# P6-D · L2 端到端：先定边界，再决定本批做哪几跳

> **日期**：2026-10-05 ｜ **状态**：第一步（**只写文档，不改代码**）
> **上游**：阶段 ②（P6-C）已推送 `7118c88f`；阶段 ①（P7-A）优先级结论已把 ③ 排在 ④ 之前
> **目标**：定义「端到端」= 什么，逐跳给出「输入 / 输出 / 可机判判据 / 当前是否打通」，
> 把 **L1 / L2 的区分固化进归因字段 `corpus_layer`**，然后**只做**判为「未打通」且本批能做完的跳。

---

## 1. 采纳的既有口径（**有建议项 ⇒ 直接采纳，不重新讨论**）

仓库里**已经有** L1 / L2 的定义，不需要本批发明：

> **L1 算法层**：合成语料，**直接由** `scripts/ingest_affiliation_sources.py` 入图，
> **不经过 M2 抽取链路** ⇒ 只验证算法判据，**未经端到端验证**（A8 裁决 4 / G5 声明）
> —— `backend/data/eval/gold-affiliation-v2.json::source.corpus_layer_note`

配套依据：

- `docs/delivery-requirements-and-guardrails.md` **DR-A8′**：L0/L1/L2 分层是**纪律**，
  口径写进 ADR 即可（ADR-0007 的 L0/L1/L2 是**定制分档**，与语料层**不是同一套**——
  ⚠️ **两处编号同形而含义不同**，本批只沿用"语料层"那一套，不碰定制分档）。
- `app/evaluation/criteria.py:68` 的 `Provenance.corpus_layer` 字段与
  `report.py:145` 的打印行**已经存在** ⇒ 本批是**让它随实测结果变化**，不是新建字段。

⇒ **本批采纳的判定口径（一句话）**：

| 层 | 判据 |
|---|---|
| **L1** | 语料**不经 M2 抽取**直接入图（合成 / CSV 直灌）⇒ 结论只对**算法层**成立 |
| **L2** | **真机文档 → M1 解析 → M2 抽取 → 入图 → 检索 → 问答 → 引用回溯**全链走通，且**不经合成替身** |

**这条判据必须是机器可读的**：由链路实测结果反推，而不是人写一句"我觉得这是 L2"
（§4 T4 会把这条变成可执行断言）。

## 2. 逐跳链路表（**每一跳都给了证据路径**）

> 「当前是否打通」一列 = **2026-10-05 本环境的实测/代码事实**，不是文档说法。

| # | 跳 | 入口（绝对路径） | 输入 → 输出 | 可机判判据 | 当前 |
|---|---|---|---|---|---|
| **H1** | 真机文档入库 + M1 解析 | `backend/app/api/v1/routes/documents.py` → `app/tasks/registry.py::_do_parse:202` → `app/services/parsing/mineru.py`（+ `page_index.py`） | `demo/attendance/*.docx` → storage 落盘 + parse artifact | `documents.status` 流转 + artifact 可读；`_do_parse` 有单测 | ✅ **已实现**（依赖 MinerU 凭据） |
| **H2** | M2 抽取 | `app/tasks/registry.py::_do_extract:479` → `app/services/extraction/langextract.py::LangextractClient.extract_entities_relations:817` | parse artifact → `entities.json` / `relations.json` / `chunks.json` | 产物非空 + 目标实体类型命中；失败进 `FailedChunk` | ✅ **已实现**（**本批不重写**） |
| **H3** | 入图（三段式） | `app/tasks/registry.py::_do_kg_build:708` → `ThreeStageKgBuilder`；演示脚本 `scripts/ingest_attendance_policies.py` | entities/relations → Neo4j `MERGE` + PG `kg_versions` 回填 `ready` | PG `kg_versions.status='ready'` **且** 图里 `:Chunk` / `:Entity` / 目标连边计数 > 0 | ❌ **未打通**：`bridge_governed_by()` 桥接边 **= 0 条**（跨源路径连不上）⇒ 无 QA `ready` 版本 |
| **H4** | 检索 | 图侧 `app/services/graphs.py::select_evidence_chunks` / `fetch_evidence_chunks`；基线侧 `fetch_chunk_pool`（P6-C 新增）+ dense top-k | question → evidence chunks | 非空 + 同输入可复现 | ✅ 代码已实现；⚠️ **依赖 H3 出 ready 版本**才谈得上端到端 |
| **H5** | 问答 | `POST /api/v1/agent/query` → `app/services/agents.py::AgentService` | question → answer + citations | 有 ready 版本 ⇒ 200 + citations；无 ⇒ **501** | ❌ **未打通**：本环境恒 **501**（`kg_versions` 无 ready；图库现存 `kg_version` 只有 `affiliation-demo-v1/v2`） |
| **H6** | 引用回溯 | `app/services/documents.py::get_document_chunk:382`（HTTP 端点在 `routes/documents.py`） | `chunk_id` → 原文片段 | 命中 ⇒ 返回 text/page/char 区间；缺失 ⇒ **404**（不返回空串） | ✅ **已实现**（数据源是落盘 `chunks.json`，**不查 Neo4j** ⇒ 图谱挂了也能溯源） |

### 2.1 L1 / L2 分界的**代码级证据**

| 层 | 落地脚本 | 是否经 M2 |
|---|---|---|
| **L1** | `backend/scripts/ingest_affiliation_sources.py`（合成 CSV → 直接入图）；`gen_affiliation_corpus.py` 生成，gold `v1/v2` 的 `source.corpus_layer="L1"` 已登记 | ❌ **绕过** |
| **L2** | `backend/scripts/ingest_attendance_policies.py` —— 脚本头自述：M1 走 `document.parse`（MinerU，docx 后缀）、M2 走 `document.extract`（LangExtract + `kg_extraction_v2`）、末段 `kg.build` 三段式 | ✅ **走全链** |

⚠️ **归因陷阱（必须在本批解决）**：`runner.py:86` 的 `QSET_CORPUS_LAYER = "L1"` 是**写死的常量**。
如果 H3–H5 打通了而它没变，一份 **L2 的实测结果会被标成 L1**（反向也成立：改一行常量就能把 L1 说成 L2，
而**没有任何机器证据**能证伪）。⇒ §4 T4 要求它随链路实测反推。

## 3. Non-goals（**边界先定死，不许边写边定**）

1. **不把 L1 的结论说成 L2**——报告里 `corpus_layer` 与实际链路不符即视为**假绿**；
2. **不重写 / 不改造 M2 抽取链路**（`langextract.py` 属另一条线）；H2 只做"有没有产物"的判据；
3. **不改 A8 已落的两版 gold 语料**（`gold-affiliation-v1/v2.json` 及其扩标产物）；
4. **不动任何判据阈值**（C1 的 10% 归阶段 ⑤；C2-a/b/c 口径不动）；
5. **不改契约**（`contracts/openapi.yaml` 零 diff）；
6. **不顺手修发现的小 bug**，只登记到它所属的需求条目；
7. **不做"看起来像端到端"的替身**：例如用合成语料灌进图再标 L2——那正是本批要防的。

## 4. 本批要做的事（**只做判为「未打通」且本批能做完的跳**）

| 任务 | 内容 | 落在哪 |
|---|---|---|
| **T1** | 诊断 H3：`bridge_governed_by()` 为什么 0 条（是节点类型缺失、正文缺名称、还是 artifact 没读到）⇒ 给出**根因**，不是猜测 | 只调查 + 登记 |
| **T2** | 若 T1 的根因落在**本批可修范围**（脚本级 / 数据级，不动 `langextract.py`）⇒ 修，使跨源连边 > 0 且**幂等可复现** | `scripts/ingest_attendance_policies.py` |
| **T3** | 打通 H5：拿到一个真机 `ready` 的 `kg_version`，`POST /agent/query` 返回 200 + citations；**如实记录**跑了几遍 | 链路 + 日志 |
| **T4** | 让 `corpus_layer` **随实测反推**（不再写死），并补反向验证：把 L2 判成 L1（或反之）必须判红 | `runner.py` / `report.py` + 测试 |
| **T5** | 一条**可复现**的端到端冒烟脚本/判据：逐跳输出「通 / 不通」+ 最终 `corpus_layer` | `backend/scripts/` 或 `tests/` |
| **T6** | 若 H3–H5 **修不好** ⇒ **如实登记 UNKNOWN + 卡在哪一步**，并说明 C1 / 拒答类判据因此仍不可测 | 集成日志 |

## 5. 出口判据

1. 逐跳表每跳的「当前是否打通」有**实测证据**（不是读代码推断）；
2. 报告里**看得出** `corpus_layer` 是 L1 还是 L2（且与实际链路一致）；
3. 若打通 ⇒ 给一次**真机**问答的实测记录（题号 / 是否拒答 / 引用数 / 跑了几遍）；
4. 若没打通 ⇒ 明确写「未实测 + 卡在第几跳 + 下一步是谁的事」；
5. 门禁数字照旧登记（pytest passed **不减** / ruff / seams / openapi / drift S1–S5）。

## 6. 已默认采纳项（用户可推翻，均已在本文登记）

| 采纳 | 依据 |
|---|---|
| L1/L2 采用「是否经 M2 抽取」作为判据 | `gold-affiliation-v2.json::source.corpus_layer_note` + DR-A8′ |
| ADR-0007 的 L0/L1/L2（**定制分档**）**不**用于语料层 | 两者编号同形含义不同；DR-A8′ 注明语料层是"纪律" |
| 本批先修 H3 的**脚本级**根因，不动 `langextract.py` | 阶段 ③ Non-goals 第 2 条（M2 属另一条线） |
