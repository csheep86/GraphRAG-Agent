# Sprint 10.4 开工前侦察（¥0，2026-09-30）

> 问题：**知识时效 L2 现在能不能做？**
> 方法：`probe_l2_temporal.py` 直连演示库实算（不调 LLM、不读旧结论）。
> 结论：**不能直接做——地基是空的。**

## 1. 实测（三行决定一切）

| 项 | 实测 |
|---|---|
| `documents.document_date`（**L0 上游**） | **有值 0 / 共 17** —— 演示文档**全部没有日期** |
| `attendance-demo-v1`（active，4039 条关系） | `valid_from` / `valid_to` / `expired_at` / `source_document_id` 覆盖 **全部 0%** |
| `affiliation-demo-v1`（311 条关系） | 同上，**全部 0%** |
| 全库兜底「哪些版本带时序字段」 | **只有 15 条**，且 `kg_version = None`（**无版本归属的残骸**——应是 S9 L1 验证 `n=3` 时留下的，图后来重建过：`attendance-demo-v1` 的 `ready_at = 2026-09-30 01:44`，就是今天凌晨） |

**即：ADR-0005 的 L0 / L1 在代码里完成了，但在当前演示库里一条可用数据都没有。**
S9 声称「`CP-T1` + `CP-T2` 双闸门达成、真机 n=3 达 3/3」——那 15 条 `kg_version=None` 的边很可能就是当年的验证残骸；今天的库是**重建后**的，时序数据没有跟着回来。

## 2. 为什么是 0%（根因，不是巧合）

1. **上游没数据**：L0 第一项是 `Document.document_date`，实测 **0/17** ⇒ `valid_from` 无来源；
2. **写字段的 Cypher 覆盖面窄**：`builder.py` stage-3.1 / 3.2 只给 **M4 主体层两条边**（`LEGAL_REP` / `REGISTERED_AT`）写四字段；通用抽取边（`:Entity`）**根本不走这两条 Cypher**；
3. **R4 不猜值**：抽取没给 `valid_from` 时保留 `None`（`builder.py` 注释明写「不猜、不补」）⇒ 上游空 ⇒ 下游必然空。

## 3. 第三个坑：L2 的两块作用在不同图层上

- **多跳路径查询**（`reasoning.py:_CYPHER_PATHS`）走 **`:Entity`**：`attendance-demo-v1` 3667 条、`affiliation-demo-v1` 173 条；
- **时序边**在 **M4 主体层**（`:Subject` / `:LegalPerson` / `:Address`）；
- ⇒ **两者不相交**：就算把时序字段补上，"路径时序一致性"也要先决定——是让通用层边也带时序，还是让路径查询覆盖 M4 层。**这是架构级选择，不是改几行 Cypher。**

## 4. 前端那块反而是最容易的（好消息）

- `frontend/src/components/graph/graph-canvas.tsx` 是**自绘 SVG**（自研 `computeForceLayout`，无第三方图库），边色是 `EDGE_IDLE` / `EDGE_ACTIVE` 两个常量 ⇒ **虚线 / 灰度完全可控**；
- 契约 `GraphEdge.properties` 是 `additionalProperties: true` 的**自由对象** ⇒ 时序字段若在关系属性里，**前端能读到，不必改契约**。

## 5. 三个候选方向（待裁决）

| 方向 | 做什么 | 代价 | 风险 |
|---|---|---|---|
| **A. 先补地基再做 L2** | 给演示语料补 `document_date` → 重跑抽取 / 建图让四字段真落库 → 再做 L2 三块 | 最大（要重跑建图，且考勤语料天然无"披露日"） | 唯一能让 L2 **真机可验**的路 |
| **B. L2 只做代码 + 单测** | 用合成数据钉死判据，真机验证留待语料有日期之后 | 小 | **"看起来做了、演示时看不见"**——正是本仓库反复警惕的假完成 |
| **C. L2 延后，先收尾 S10** | 把「时序数据未落地」登记为缺口，先做文档 / 版本收尾 | 小 | S10 排期含 L2 ⇒ **打不了 `v1.6.0`**（tag 的树须含 notes 声称的全部交付，S8 三次重打 tag 的教训） |

## 6. 我的建议

**先 A 的探路部分、再决定**：A 的关键未知是"**考勤语料能不能给出真实日期**"——
考勤 CSV（请假 / 工单 / 员工表）**有业务日期字段**（请假起始日、工单创建日），制度文档有发布日期。
⇒ 值得先花 ¥0 探一次：现有 17 份文档里**有多少能机械抽出日期**，再决定 A 是否可行。
若可行 ⇒ 走 A；若不可行 ⇒ 走 C（把 L2 与"时序数据地基"一起登记为下一批，S10 先收尾能收的部分）。
**不建议 B**（假完成）。

---

## 附：新对话接手指引

本批次上下文全在以下文件，新对话读它们即可，无需回溯聊天记录：

| 文件 | 内容 |
|---|---|
| 本文 `00-recon.md` | 探查结论与三方向 |
| `probe_l2_temporal.py` | 可重跑的探查脚本（`uv run python ../changes/Sprint10.4/probe_l2_temporal.py`） |
| `docs/adr/ADR-0005-temporal-knowledge-model.md` | L0 / L1 / L2 定义与仲裁规则 R1–R4 |
| `docs/optimization-plan-2026-09.md` §3 P3 | 同上（执行版口径） |
| `docs/acceptance-traceability-matrix.md` §3 / §7 | L2 要追加的验收项（**只追加编号，不重排**） |
