# P3-E 任务清单 —— G-25：C2-a / C2-b 进 CI 成真门禁

> 边界见 `proposal.md` §3（**开工前先读 Non-goals**）。起跑：`pytest` **892 passed**。

- [x] **E1** `app/evaluation/gate.py`：门禁纯逻辑
      - value=None ⇒ fail；基线缺项 ⇒ fail（不许跳过比对）
      - 空图守卫：gold_count>0 且 detected_count==0 ⇒ fail
      - 退化：recall 下降 / fpr 上升超容差 ⇒ fail；**不达标 ⇒ 不 fail**（只 warning）
- [x] **E2** `scripts/eval_acceptance.py`：`--gate` / `--baseline` / `--tolerance` / `--update-baseline`
- [x] **E3** `data/eval/baselines/ci-c2-v1.json`：**实测**生成并入库（带 git_hash / 语料版本）
- [x] **E4** `ci.yml`：backend job 加「导入受控种子语料 → 跑 --gate」步骤 + 失败摘要的复现命令
- [x] **E5** `tests/test_eval_ci_gate.py`：纯逻辑 6 条 + 真图端到端 1 条
- [x] **E6** 反向验证：6 条纯逻辑各自判红；真图「purge 后不导入」⇒ gate 红
- [x] **E7** 文档：需求基线 G-25 行转 ✅；`delivery-plan.md` P6 行；集成日志
- [x] **E8** 收束门禁：pytest（+7）/ ruff 双绿 / 接缝 OK 10 / 契约零漂移

## 不做（改完回头逐条对照）

1. 判达标（CI 只判不退化）
2. 改指标函数 / 报告格式 / 四态状态机
3. 给 CI 加 LLM key、让 C2-c / 多跳进 CI
4. A8 语料扩标
5. TBD-7 收敛口径
6. 改契约 / ADR 原文、动租户隔离代码
