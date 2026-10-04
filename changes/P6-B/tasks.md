# P6-B 任务卡（A6 + L8 兑现）

## 边界
- **做**：C2-c 两档并列输出（补含拒答档）；拒答误伤立独立判据；误伤方向分家；测试 + 反向验证 + 文档订正。
- **不做**：修 Q8 链路；改 C2-c 分母；放宽拒答判定；A1 / L2 / TBD-7；新判据进 CI 门禁。

## 任务

- [x] 1. 写 `changes/P6-B/proposal.md` + 本任务卡（**先定边界再动手**）
- [x] 2. `runner.py`：C2-c 补 **含拒答档**（`coverage_including_refused`），判据值仍走排除拒答档
- [x] 3. `runner.py`：拒答方向分家 → `false_refusals`（误伤）/ `missed_refusals`（漏拒）
- [x] 4. 新增判据 `refusal_false_refusal`（值 = 误伤条数，阈值 0，越低越好，当前 FAIL）+ 注册 + `ALL_CRITERIA`
- [x] 5. `report.py`：人读摘要标口径（C2-c 行注明 `exclude_refused`），新判据独立成行
- [x] 6. 新建 `tests/test_eval_refusal_a6.py`（纯逻辑：两档 / 方向分家 / 判据语义 / 两档必须都输出）
- [x] 7. 反向验证：去掉含拒答档 / 把误伤混入 C2-c / 方向合并 ⇒ 各自判红
- [x] 8. **实测**：起后端跑 `--live --criteria c2_c_citation_coverage,refusal_false_refusal`（起不来 ⇒ 如实登记未实测）
- [x] 9. 文档订正：需求基线 C2-c 行（1.00 不含拒答 / 含拒答 0.786）、release notes、`L11(b)2` 勾销
- [x] 10. 全部门禁 + `check_session_drift` + 提交推送 + `changes/P6-B/integration-log.md`
