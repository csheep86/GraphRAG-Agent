# P6-J · 任务清单（M1：轻量 lexical 重排，让 question 参与图侧证据选择）

> 对应 [`proposal.md`](./proposal.md)（Non-goals 9 条已冻结）与 [`integration-log.md`](./integration-log.md)
> **拍板**：D1 **M1**（不做 M2 / M3）/ D2 接受「改标识 + 40×2 全判」/ D3 越过 10% 认可但须写明换了一代

- [x] **T1** 补回复现脚本（`_tmp_probe_recall.py`）⇒ 红灯基线复现：三条目标 chunk **全被切掉**
- [x] **T2** 索引带回打分片段（`snippet`，前 400 字）+ 决策理由写进代码注释
- [x] **T3** `select_evidence_chunks` 加 `question` / `snippets` 入参（字符 bigram 词面分，**零新依赖**）
- [x] **T4** `question` 一路传下来：`agents.py` → `fetch_evidence_chunks` → `select_evidence_chunks`
- [x] **T5** `RETRIEVER_GRAPH` 改名 `graph_mentions+lexical_rerank`（旧数字不得混用）
- [x] **T6** 单测 9 条（命中占保底 / 并列退化 / 空 question / 无命中 / 无片段 / 确定性 / bigram 口径）
- [x] **T7** 正向验证：三条目标 chunk **全部进入** 32 条
- [x] **T8** **反向验证**：① 不传 question ⇒ 三条重新被切掉；② `git stash` 真撤代码 ⇒ 同样被切掉
- [x] **T9** 40×2 按 **rubric-v2** 全量重判（`_judged_by=architect` 非匿名）
- [x] **T10** live C1 × 3 ⇒ **17.65%（3 遍一致）**，越过 10%（PASS provisional）
- [x] **T11** 门禁 + `tasks.md` / `integration-log.md` + 摊 diff 给用户确认（**不自行 push**）

---

## 未决（需另开批次，本批不碰）

| # | 事项 | 为什么不在本批 |
|---|---|---|
| 1 | 候选集**仍是结构性窗口**（子图采样不看 question）：目标片段若**不在** 213 条候选里，重排救不回来 ⇒ R22 未关闭 | Non-goals 第 9 条不动抽取/子图；扩候选集是另一件事（方向② 实体链接 / ③ 向量召回） |
| 2 | `RETRIEVER_GRAPH` 换代的归因漂移：C1 从此测的是「图结构 + 词面重排」 | 已**显式登记**（改名 + 本日志 §5），**不**通过改回去来"救纯度" |
| 3 | 阈值校准（阶段 ⑤ / TBD-7） | Non-goals 第 1 条 |
| 4 | `expected_points` 粒度不均 ⇒ 题权重不等 | P6-I 遗留 2，独立于本批 |
| 5 | H6 403 / 制度入图器自检恒 FAIL / P7-B / G-12 / MANIFEST 语料统计过期 | Non-goals 第 6 条 |
| 6 | 复现脚本 `_tmp_probe_*.py` 已按约定删除 ⇒ 反向验证改由单测钉住 | 见 integration-log §4.3 |
| 7 | ~~**C1 已到顶 17.65%**（图侧 40/40，唯一的上升路径是让基线掉分＝作弊）⇒ 后续图侧改进在 C1 上不可见，待用户拍板 A / B / C~~ **已裁决（2026-10-05，用户在 P6-J 收尾对话中拍板）⇒ 采纳 A**：接受 C1 在本口径下封顶 **17.65%** 并把它**降级为"记过账的历史指标"**；B（扩/换题集）与 C（换语料）**暂不做**。⇒ **下一批要动"候选集仍是结构性窗口"这条根因，必须自带新判据**（C1 已不可能反映任何图侧改进），判据由下一批的 proposal 定义并另行拍板 | 执行者建议 A，用户已采纳；下一批评据待定 |
