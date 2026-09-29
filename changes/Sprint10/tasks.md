# Sprint 10 任务清单（v1.6.0，证据链与多跳）

> **分支**：`feature/sprint-10` | **提案**：[`proposal.md`](./proposal.md) | **勘察**：[`c0-recon.md`](./c0-recon.md)
> **纪律**：`tasks.md` 勾选 **≠** 完成，须有同目录 `integration-log.md` 的真机证据支撑（倒推计划 §6.3）
> **排期**：计划 12-02 → 12-18（**实际 09-29 开工**，S9 提前 43 天，本 Sprint 预计同样大幅提前）

---

## 批次 A：证据三元组落地（`char_offset` 从占位到精确）

**首日冻结**（已写入 proposal §2，改判据须先改提案）：D-A `char_offset` = 片段内相对偏移 + 新增 `char_end`；D-B 偏移由代码算、禁 LLM 产出；D-C 双档（span 级 / 回退 chunk 级）；D-D span 落 `:Entity`、CSV 派生写 null；D-E `confidence` 不补数字。

### A1 契约先行
- [x] `schemas/agent.py`：`Citation` 新增 `char_end: int`（含描述与 example）
- [x] `uv run python scripts/export_openapi.py` 重导契约，diff 仅 `Citation` 两处
- [x] `npm run gen:api` → `api.d.ts` 与契约零漂移

### A2 后端：span 进图（补"抽取有、入图丢"）
- [x] `kg/builder.py` 写 Entity 的 Cypher 补 `char_start` / `char_end`（无值写 null）
- [x] 单测：抽取产物带 span ⇒ 入图后 `:Entity.char_start/char_end` 等值（钉死不丢）
- [ ] 真机：重跑建图或补写，验证 LLM 抽取实体有 span、CSV 派生为 null（**待 A5**）

### A3 后端：引用换算
- [x] `graphs.py`：`EvidenceChunk` 新增 `entity_spans`，两条证据查询带出片段内实体 span
- [x] `agents.py:_to_citation`：`char_offset` / `char_end` 由 `entity.char_start − chunk.char_start` 确定性算；无 span 命中回退 `0` + `len(text)` + WARNING 日志
- [x] Prompt `kg_qa_v4.md`（**新增，不覆盖 v3**）：evidence 条带**实体提及文本**（非数字）；`load_prompt` 取最大版本 ⇒ 自动生效
- [x] 单测：换算函数（span 命中 / 提及模糊 ⇒ 回退 / span 与片段无交集 ⇒ 回退 / 无 span ⇒ 整段）

### A4 前端：高亮
- [x] 引用组件按 `[char_offset, char_end)` 在 `GET /documents/{id}/chunks/{chunk_id}` 返回的 `text` 内高亮（`splitHighlight` 区间优先，疑点页两参调用行为不变）
- [x] 回退档（`char_offset=0` 且 `char_end=len(text)`）高亮整段，不闪空白

### A5 真机验收
- [x] 写读闭环真机（**不依赖 PG**）：`:Entity` 17/17 落 span；证据回查带出 17 个 span；换算得 `[87,95)` / `[437,439)` —— 探针输出进 `integration-log.md`
- [x] 门禁：pytest 616 passed / ruff / `check_seams` OK 10 / `export_openapi --check` / 前端 tsc+lint 全绿
- [ ] **端到端问答真机**（`citations[].char_offset` 非 0）：需 **PG + 真实 LLM**，本机 PG 不可用 ⇒ 待 PG 就绪或批次 F 联调时补
- [ ] `kg_qa_v4` 是否真让模型输出 `#提及`：**未证前不得宣称"引用已精确到句"**（不遵循 ⇒ 回退整段，行为与改造前一致）
- [ ] 前端高亮真机截图
- [ ] `:Entity.confidence` 覆盖率 4.7% 的分层口径登记进 `dev-doc-status.md`（D-E）

---

## 批次 B：多跳遍历（`*1..3`）— 详见 [`../Sprint10.1/`](../Sprint10.1/)
- [x] 多跳答对率**口径先落文档**（对齐 `02-product-outline.md:293`）⇒ 再写代码（`Sprint10.1/proposal.md` §2）
- [x] Cypher `*1..3`（**S9.5 已有**，`reasoning.py:135`）——本批次做的是**域无关化**：终点白名单改并集 + 边类型不限定
- [x] 答案注入携带路径证据（`reasoning_path` 契约已有，S9.5 已接）
- [x] 跳数**不**参数化（D-G：`_MAX_HOPS=3` 与 PRD「3 跳内」一致；无消费点即不预留，R4）
- [x] 真机双域对照：关联方域 **0 行 → 20 行**；考勤域首选链不变（无 regression）
- [ ] 真机：单跳与 ≥3 跳分别可答（需 PG + LLM）
- [ ] 多跳答对率实测 ≥0.80（需 PG + LLM；口径已冻结，未测前不宣称达标）

## 批次 C：M3 检索覆盖（**先探针后定方案**）— 详见 [`../Sprint10.2/`](../Sprint10.2/)
- [x] 探针：无序截断 / 度数降序 / 均分配额 / **保底+补满** / 全量 五组对照（召回 + 结构 + 耗时，结论进 integration-log）
- [x] 按探针结论实施：`select_subgraph_nodes`（**按 `entity_type` 保底 + 组内度数降序 + 余量按度数补齐**）——治的是采样策略，不是数量
- [x] 真机验收（服务层）：500 节点 / **14 类全覆盖** / 边 623 / **锚点召回 100%**（改动前 50%、12 题丢 6 题）
- [x] 单测 6 条 + 门禁全绿（625 passed）
- [ ] **端到端问答真机**（拒答率是否下降）：需 PG + LLM ⇒ 与批次 A/B 的待验证项一起补

## 批次 D：docx 解析
- [ ] `_do_parse` 真实实现（现状 `return None`）+ 依赖引入
- [ ] 真机：docx 上传 → 解析 → 建图 → 问答

## 批次 E：时效 L2 + `as_of` 上 REST
- [ ] REST 层 `as_of` 参数（契约先行）+ 前端问答页时间入口（**一起做**，不造无入口参数）
- [ ] 路径时序一致性 + 失效视觉语义
- [ ] 验收矩阵验收项补登

## 批次 F：容器化（CP-D0，**与业务批次并行**）
- [ ] `Dockerfile`（backend / frontend）+ `docker-compose.yml` 起全套（Neo4j / PG / backend / frontend）
- [ ] 本地起全套 + 冒烟
- [ ] 同步 `docs/deployment-spec.md` §11 D-1 行：S11 → **S10**（现与 `sprint-calendar` CP-D0 口径分叉）
- [ ] 离线镜像包 **留 S11**（CP-D1）

---

## 收尾（Sprint 级）
- [ ] **CP-1**：把 D-1（`specs/m6` v0.1 → v1.0）/ D-3（schema-suggestion PoC）写进 **S11 `tasks.md`** 作带内任务
- [ ] **CP-D0**：容器化就绪
- [ ] release notes v1.6.0；bump `app_version` 1.5.0 → 1.6.0（+ 重导契约）；tag `v1.6.0`
- [ ] `sprint-calendar` §5 S10 行 + §6 追加；`dev-doc-status.md` 登记（含 `confidence` 覆盖率口径）
- [ ] 归档 `changes/Sprint10/` → `changes/archive/<日期>-Sprint10/`
