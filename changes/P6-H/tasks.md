# P6-H · 任务清单（受控题集 v3: 14 → v4: 40）

> 对应 [`proposal.md`](./proposal.md)；**Non-goals 10 条已冻结**。
> 目标：把单题翻转灵敏度 **7.14pp → 2.50pp**，让阶段 ⑤ 的阈值校准值得做。
> 硬约束：**v4 = v3 的 14 题一字不改 + 26 道新题追加**（不是重出）。

- [x] **T1** 写 proposal / tasks，冻结 Non-goals 10 条
- [ ] **T2** 读 `demo/attendance/policies/*.md` 六份真源，起草 26 道新题
      （24 制度 + 12 CSV + 4 拒答 = 40；**必须标注出处条款/行**）
- [ ] **T3** 落 `data/eval/controlled-qset-v4.json`（v3 **不动**）+ `QUESTIONS` 追加
      + `dataset.py` / `MANIFEST.json` 接线
- [ ] **T4** 版本硬编码整改：`runner.py` **8 处** `controlled-qset-v3` → v4；
      `parity` 测试的 `== 14` 改为读 MANIFEST items
- [ ] **T5** **E3 实测**：逐题 `--diagnose` 校验有据性（库内题召回非空 / 库外题拒答）
- [ ] **T6** **E2 验证**：live 跑一次，确认报告 `dataset_version = v4` 且 v3 残留 0 处
- [ ] **T7** **判分**：两侧 80 条按 `rubric-v1` 人工判 ⇒ C1 出 v4 数字 + 记录灵敏度 2.5pp
- [ ] **T8** 门禁（pytest / ruff / format / seams / 契约零 diff / drift S1–S5）+ 集成日志 + 提交
