# P6-I · 任务清单（rubric-v1 → rubric-v2：要点分级）

> 对应 [`proposal.md`](./proposal.md)（Non-goals 9 条已冻结）与 [`integration-log.md`](./integration-log.md)
> **拍板**：D1 改 / D2 方案 C（core/secondary 分级）/ D3 先做前置验证

- [x] **T1** 决策文档：现状 vs 分层三案对比 + 陷阱说明 + Non-goals 9 条
- [x] **V1** 给 40 题标注 core / secondary（草案，不落 git-tracked 文件）
- [x] **V2** 要点级重判 11 条 false + 9 条 true 抽样（依据单调递增 ⇒ **无需 80 条全判**）
- [x] **V3** 回算 C1 并与推算对照 —— **偏差 0.00pp < 1.5pp ⇒ 推算成立**
- [x] **T2** 落地 rubric-v2：v4 JSON 加 `secondary_points` / MANIFEST rubric 升版 /
      loader 字段 / 判分表迁移（graph Q5、Q7 翻 true）
- [x] **T3** 新增 `secondary_points` 自洽测试（挡「假清单」与「无 core ⇒ 全都判对」）
- [x] **T4** live 复跑 C1 × 3 ⇒ **8.82%（3 遍一致），仍未达 10%**
- [x] **T5** 门禁 + 集成日志 + 提交

---

## 未决（需另开批次，本批不碰）

| # | 事项 | 为什么不在本批 |
|---|---|---|
| 1 | **图侧「长条款特定 span」召回弱于 dense**（Q20 / Q22 / Q26）⇒ C1 距阈值 1.18pp 的真实来源 | Non-goals 第 8 条：属被测链路，须另开批次 ⇒ **建议作为下一批优先项** |
| 2 | `expected_points` 粒度不均（n = 1~4）⇒ 题权重不等 | 建议独立于 rubric 处理 |
| 3 | MANIFEST 语料统计过期、H6 403、入图器自检、P7-B、G-12 | Non-goals 第 7 条 |
| 4 | 阶段 ⑤ TBD-7 阈值校准 | **须在本批之后**：rubric 已定，阈值才有稳定的尺子 |
