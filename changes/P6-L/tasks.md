# P6-L · 任务清单（让哨兵第一次真触发——用现成的更大语料）

> 对应 [`proposal.md`](./proposal.md)（Non-goals **9 条**已冻结）
> **拍板**：L-D1 **不造语料**（用现成 `affiliation-demo-v2`，988 chunk = 4.6×）/
> L-D2 **只出机械量、不判分** / L-D3 脚本加 `--kg-version`+`--org-id` /
> L-D4 新增**在 CI 上真跑**的用例 / L-D5 v2 是疑点检测语料 ⇒ **默认不跑题集**
> **上游**：[`changes/P6-K/`](../P6-K/)（哨兵已建、本语料 213/213 零损失、R22 仍挂起）

- [x] **T1** 三件套：`proposal.md` + 本文件（F6 决议：三件套与 `integration-log.md` 并存，**不启用** OpenSpec CLI）
- [x] **T2** `backend/scripts/probe_candidate_window.py` 加 `--kg-version` / `--org-id` / `--with-questions`；换版本时**默认不跑题集**，汇总段对空表打印 `N/A`（**不**除零、**不**给 0）；新增 **[S] 生产采样档**作主读数
- [x] **T3** 真机跑 v2：`--kg-version affiliation-demo-v2 --org-id 5dea8f62-…` ⇒ **U 档 988/988 = 100%**、**S 档 355/988 = 35.93%**（侦察粗估 57%，真机更糟——产品按 `entity_type` 保底采样比"随便取 500"更偏）
- [x] **T4** 新增真机用例 `test_sentinel_fires_on_a_larger_corpus`：在 v2 上断言**哨兵确实 warn**（**CI 上不 skip**，因 CI 会先导入该语料；CI 上语料缺失 ⇒ **fail** 不是 skip）
- [x] **T5** **反向验证**：撤掉 `_warn_if_candidate_window_narrow` 的告警体 ⇒ T4 那条**变红**（共 5 红）；还原 ⇒ 11 绿
- [x] **T6** `integration-log.md`：贴真机输出 + **R22 补登「已在 988 chunk 语料上实测劣化到 35.93%」（仍不关闭）** + 收尾三问
- [x] **T7** 门禁全绿：`pytest` **989 passed**（+1，0 回归）/ ruff / `check_seams`（ERROR 0）/ `export_openapi --check`（零 diff）/ `check_session_drift`（**S1 读到 9 条边界**）—— ⏳ 摊 diff 给用户（**不自行 push**）

---

## 验收判据（**必须真跑**，不能读代码得出）

| # | 判据 | 怎么算跑过 |
|---|---|---|
| ① | 脚本对 v2 **独立重跑**出机械量 | S 档**窗口完整率 < 100%**（U 档应为 100%） |
| ② | 哨兵在**真实语料**上确实喊 | T4 断言 warn 命中，且**CI 上不 skip** |
| ③ | **反向验证** | 撤告警体 ⇒ T4 红；还原 ⇒ 绿 |
| ④ | 全量 `pytest` 零回归 | ≥ 988 passed / 3 skipped / 3 xfailed |
| ⑤ | 门禁全绿 | ruff check / ruff format --check / check_seams / export_openapi --check / check_session_drift |
| ⑥ | **CI 绿**（R26 已修 ⇒ backend job 第一次真跑 pytest） | 四个 job 全 ✓ |

## 未决（需另开批次 / 用户裁决，本批不碰）

| # | 事项 | 为什么不在本批 |
|---|---|---|
| 1 | 要不要造更大语料 / 造多大 | 等本批劣化数据才有判据（L-D1） |
| 2 | 方向②实体链接 / ③向量召回（O2 本体） | Non-goals 第 4 条 |
| 3 | 判分谁做 / C1 是否复活 / 扩换题集 | 用户已裁决**后置** |
| 4 | 给 v2 配问答 gold 做跨域评测 | Non-goals 第 9 条（不同域，本批不下泛化结论） |
| 5 | H6 403 / 入图器自检 / P7-B / G-12 / MANIFEST / CI 5 条恒定 skip | Non-goals 第 7 条 |
