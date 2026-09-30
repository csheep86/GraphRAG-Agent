# S10 批次 C 真机验证记录（M3 检索召回）

> **日期**：2026-09-29 | **分支**：`feature/sprint-10`
> **环境**：Neo4j 5.26 ✅；**PostgreSQL ❌ 不可用** ⇒ 未跑端到端问答（不需 PG 的部分全跑了）
> **探针**：`probe_c0_recall.py`（五方案对照）、`probe_c1_verify.py`（改动后服务层验收）

---

## 1. 改动前：五方案对照（active 图 `attendance-demo-v1`：2764 实体 / 3645 边）

问句 12 条 = 图上**度数最高 / 最低各 6 个**实体的真实名字；
golden 锚点 = 全量集上机械反查（`anchor_ids_for_question`），**不含人工判分**。

| 方案 | 节点 | 类型 | 内部边 | 孤立点 | 锚点召回 | `POLICY_CLAUSE` | `OVERTIME` | `LEAVE` |
|---|---|---|---|---|---|---|---|---|
| current（无序截断，原实现） | 500 | 13 | 546 | 26 | **50%（丢 6 题）** | 53 | 30 | 15 |
| degree（度数降序，概览口径） | 500 | 12 | 581 | 0 | **50%（丢 6 题）** | 34 | **2** | **0** |
| quota（每类型均分） | 359 | 14 | 470 | 7 | **100%** | 35 | 30 | 17 |
| **quota_floor（保底 + 余量按度数补满）** | 500 | **14** | **623** | 7 | **100%** | 35 | 30 | 17 |
| full（全量，对照） | 2764 | 14 | 3645 | 31 | 100% | 60 | 30 | 17 |

两条**与直觉相反**的实测结论：

1. **"对齐概览的度数降序"解决不了问题**：名额几乎全给了 `ATTENDANCE_RECORD`（388 个），
   `LEAVE` 掉到 **0**、`OVERTIME` 剩 **2** ⇒ 问"请假 / 加班"时制度落点没了；锚点召回仍是 50%
   （被挤掉的恰恰是问句里那些具体的员工 / 工单）。
2. **按类型占比分配也不行**：考勤记录占全图 30% ⇒ 按比例就把名额吃掉（`LEAVE` 剩 3）。
   ⇒ 小类型必须**保底**。

## 2. 改动后：服务层真机验收（`probe_c1_verify.py`，走 `fetch_all_subgraph`）

```
截断=True
候选集: 节点 500 / 类型 14 / 边 623（内部 623）；孤立点 11；全量实体 2764
锚点召回: 100%（12 条问句，全丢 0 条，总锚点 12）
对照（改动前）: 50%（12 条问句，全丢 6 条）
```

节点上限**保持 500**（不放量 ⇒ 不把成本转嫁给 Prompt token），内部边 546 → **623**。

## 3. 实现要点（`backend/app/services/graphs.py`）

- `_QUERY_ALL_ENTITY_SUBGRAPH` 拆两段：`_QUERY_SUBGRAPH_NODE_INDEX`（只回 `id / type / degree`）
  → Python 侧 `select_subgraph_nodes` 选 → `_QUERY_SUBGRAPH_BY_IDS` 取完整节点 + 边；
- **为什么不放 Cypher 里一步做完**：Cypher 侧要 `reduce` + `UNWIND`，而 **`UNWIND` 空列表会
  吞掉整行**（余量为 0 时整条查询返回空 ⇒ 空图，把故障伪装成"图上没数据"）；
- 顺带修掉一个漂移隐患：`eval_controlled_qset.py::diagnose` 原先**复刻**线上 Cypher，
  现在改为调 `GraphService.fetch_all_subgraph`（诊断结论才不会与线上逻辑分叉）。

## 4. 门禁

| 项 | 数字 |
|---|---|
| pytest | **625 passed / 3 skipped**（批次前 619 ⇒ +6） |
| ruff check / format | 通过 / 170 files |
| 契约零漂移 | OK（**无契约变更**） |
| `check_seams` | ERROR 0 / WARN 0 / OK 10 |

## 5. 端到端真机（真实 DeepSeek）——顺带还掉 A / B 两批的债

**前提更正（重要）**：此前三批都写着"端到端需 PG + LLM，本机 PG 不可用"——
**这个前提是错的**。开发库是 **SQLite**（`DATABASE_URL=sqlite:///./dev.db`），
`AgentService.query` 只走 Neo4j + LLM，而 `.env` 里 DeepSeek 已配置 ⇒ 端到端一直能跑。
（早该先读 `.env` 而不是先下结论。）

探针 `probe_e2e_abc.py`，问句全部用图上真实实体名（员工 `于静` / 条款 `2026 年 1 月 1 日`）：

| 问句 | refused | 引用 | `reasoning_path` |
|---|---|---|---|
| 于静 上个月加班了多少小时？ | **False**（medium） | 1 条 `[0, 41)` | **3 跳**：于静 →销售经理→ 不定时工作制 → 加班规定（document/document/graph） |
| 于静 的加班时长是否违反了…规定？ | **False**（low） | 1 条 `[0, 41)` | **3 跳**（同上） |
| 量子计算在考勤排班中的最佳实践？（域外） | **True** `no_grounded_evidence` | 0 条 | 0 跳 |

对三批的意义：

- **批次 B（多跳）**：首次拿到**端到端**证据 —— 真实问答里 `reasoning_path` 有 3 跳、
  每跳 `source/relation/target/origin` 齐全、来源混合 document 与 graph（此前只有构造层证据）；
- **批次 C（召回）**：问"具体员工"的两题都**非拒答**（这类锚点正是改动前会被挤出候选集的形态）；
  域外题仍**诚实拒答**（反证 F3 未被破坏）；
- **批次 A（引用 span）**：引用是 **`[0, 41)` 回退整段**——active 版本是 **CSV 派生域，
  本来就没有 span**（裁决 D-D），回退整段是**预期行为**，不是回归。
  ⚠️ 探针第一版把判据写成 `char_end != 0` ⇒ **恒真**，会把"回退"读成"命中"，已修
  （正确判据：`char_offset > 0` 才算 span 级）。

## 6. 顺带修的诊断工具（`scripts/repro_agent_query.py`）

打桩版一直报假故障，两处桩都过期了：

1. `_fake_invoke` 返回单字符串，而 `_invoke_chat_with_retry` 现在是 `(answer, usage)`
   二元组 ⇒ 解包抛 `ValueError`，被 tenacity 重试 3 次后伪装成「LLM 调用失败」；
2. 假 citation 用编造的 `chunk-1` ⇒ 被引用构造判"无据"拒答（这**是正确行为**：
   引用必须能回溯到真实注入的片段）。现改为**从 `system_prompt` 里抓本次注入的 chunk id**。

修完 1a / 1b 全绿。（同类漂移第二次出现了：`eval_controlled_qset.py` 复刻 Cypher、
这里复刻返回签名 ⇒ 诊断脚本必须调服务层入口，或在注释里写明它复刻了什么。）

## 7. 未完成

| # | 项 | 原因 |
|---|---|---|
| 1 | 多跳答对率 ≥0.80 实测 | 缺的不是环境，是**人工判分**（要跑 `eval_controlled_qset.py` 全量 + 人读答案）；未测前不宣称达标 |
| 2 | 拒答率 A/B 对照数字 | 改动前没留基线，单次问答不能当拒答率 |
| 3 | span 级引用的端到端 | active 版本是 CSV 派生域（无 span）；需切到有抽取产物的文档 |
| 4 | `kg_qa_v4` 的 `#提及` 是否被模型遵循 | 要抓 LLM 原始输出看；未证前不得宣称"引用已精确到句" |

**不宣称**：本批只证到"候选集里该有的实体在了" + "真实问答能出 3 跳路径"；
**没有**证明答案质量提升（答对率要人工判分）。

---

## 8. 批次 D：docx 真机解析（`probe_d_docx_parse.py`，真 MinerU 云）

**任务卡写的「`_do_parse` 现状 `return None` + 依赖引入」已过期**：Sprint 9.5 批次 B2
就把真实实现落好了（`app/tasks/registry.py::_do_parse`，`_PARSE_MIME_TO_SUFFIX` 已含
docx 的 mime）⇒ 本批次真正缺的只是**真机证据**。

链路走服务层（跳过 HTTP，避免把"端口没起"当成"解析不通"）：
`documents` 行 → 源文件 put 进存储层 → `_do_parse` → 读回产物。

| 样本 | 结果 |
|---|---|
| `attendance-policy-2026.docx`（2139 B） | `full.md` **799 字符** / `content_list` 1 项 |
| `fieldwork-attendance-rules.docx`（2191 B） | `full.md` **1090 字符** |

markdown 内容正确（标题、文件编号 HR-ATD-2026-001、生效日期、条款正文都在）⇒
**docx 解析链路真机通**，无需再写代码。

踩到的三个坑（都记在这，避免重复踩）：

1. `alembic upgrade head` 撞 `table entity_merge_candidates already exists` ——
   `dev.db` 里 13 张表**早就建好了**，只是 `alembic_version` 落后 ⇒ 用
   **`alembic stamp head`**（不是 upgrade）；
2. 直接 `from app.tasks.registry import _do_parse` 会撞循环导入
   （`app.tasks.manager` ↔ `app.services.documents`）⇒ 先 `import app.main`；
3. `documents.trace_id` 是 **Uuid 且 NOT NULL**，给字符串会报
   `'str' object has no attribute 'hex'`。

**未做**：docx → 建图 → 问答（抽取 + 建图这一段没跑）、HTTP 上传端到端。
