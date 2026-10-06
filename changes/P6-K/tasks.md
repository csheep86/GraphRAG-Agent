# P6-K · 任务清单（只建「候选窗口哨兵」，不建召回）

> 对应 [`proposal.md`](./proposal.md)（Non-goals 9 条已冻结）与 [`integration-log.md`](./integration-log.md)
> **拍板**：D1 **= O1**（只建哨兵）/ D2 **机械判据**（窗口完整率 + 必然丢失率，不依赖人工判分）/ D3 **只 warn + 一份可复跑脚本**（不新增表、不改契约、不加 `settings.*`）
> **上游裁决**：P6-J 收尾的**裁决 A** —— C1 在本口径封顶 **17.65%**，已降级为记过账的历史指标 ⇒ **本批不得用 C1 出数、不得宣称任何"召回增益"**

- [x] **T1** 补齐批次三件套：本文件 `tasks.md`（F6 决议：三件套与 `integration-log.md` 并存，**不启用** OpenSpec CLI）
- [x] **T2** `changes/P6-K/_probe_candidate_coverage.py` ⇒ 固化为 `backend/scripts/probe_candidate_window.py`（**常驻**诊断），输出**只保留机械量**，去掉对 `p6j-dryrun.json`（P6-J 一次性产物）的依赖（`7936f31`）
- [x] **T3** `fetch_evidence_chunks` 加**窗口哨兵留痕**：候选行被 `index_limit` 截断，或 `候选 < 版本内 chunk 总数` ⇒ `logger.warning` 一条（**不改返回值 / 不改契约 / 不加配置项**）（`7936f31`）
- [x] **T4** 单测（`backend/tests/test_evidence_window_sentinel.py`）：合成 rows 钉住两个方向 —— 「被截断 ⇒ 留痕被调用」/「未截断 ⇒ 不打日志」；`index_limit` 调小只在**单测内 monkeypatch**，产品默认值不动 ⇒ **10 条全绿**（`7936f31`）
- [x] **T5** 真机复跑：新脚本独立重跑 ⇒ 复现 **213 / 213**（窗口完整率 **100%**，撞上限 **0/40**，必然丢失率 **0/40**）
- [x] **T6** **反向验证**（硬验收，与 P6-J 撤代码那次同规格）：R1 撤告警体 ⇒ **4 条红**；R2 撤调用点 ⇒ **3 条红**；还原后 10 条全绿
- [x] **T7** 门禁全绿：`pytest` **988 passed**（+10，0 回归）/ `ruff check` / `ruff format --check` / `check_seams.py`（ERROR 0）/ `export_openapi.py --check`（零 diff）/ `check_session_drift.py`（S3–S5 OK）
- [x] **T8** `integration-log.md`：回帖探针原始输出作为对照 + **R22 只改措辞（不关闭）** + 收尾三问
- [x] **T9** 摊 diff 给用户确认（**不自行 push**）

---

## 验收判据（**必须真跑**，不能读代码得出）

| # | 判据 | 怎么算跑过 |
|---|---|---|
| ① | 新脚本**可独立重跑**并复现 213/213 | `uv run python scripts/probe_candidate_window.py` 输出 `窗口完整率 100%` |
| ② | 哨兵在**人为构造的丢数据场景**下确实 warn | 单测内 monkeypatch `index_limit` 调小 ⇒ 断言 warning 被调用 |
| ③ | `export_openapi.py --check` **零 diff** | 命令退出 0 且无输出 diff |
| ④ | 全量 `pytest` **零回归** | 通过数不低于基线（978 passed / 3 skipped / 3 xfailed） |
| ⑤ | **反向验证**：撤掉留痕 ⇒ 两条单测变红 | `git stash` 撤 T3 代码后跑 T4 ⇒ **红**；还原后 ⇒ 绿 |

## 未决（需另开批次，本批不碰）

| # | 事项 | 为什么不在本批 |
|---|---|---|
| 1 | **O2**：造一份更大的语料（让 500 采样真的开始丢 chunk），再比选方向②实体链接 / ③向量召回 | D1 已裁决另开批次；本批只建哨兵 |
| 2 | 方向②/③ 的实现（O3） | 已否决：本语料 40/40，任何召回改动都**无可证伪的新读数** |
| 3 | C1 阈值校准 / 扩换题集 / 换语料 | Non-goals 第 1 / 5 / 6 条 |
| 4 | H6 403 / 制度入图器自检恒 FAIL / P7-B / G-12 / MANIFEST 语料统计过期 | Non-goals 第 7 条 |
| 5 | 三个配额 `_GRAPH_NODE_LIMIT` / `_EVIDENCE_CHUNK_INDEX_LIMIT` / `_EVIDENCE_CHUNK_LIMIT` | Non-goals 第 8 条（**本批连默认值都不许动**） |
| 6 | R22 关闭 | Non-goals 第 9 条：本批**只改措辞为「已量化：当前规模零损失，窗口随规模劣化」**，保持**挂起** |
