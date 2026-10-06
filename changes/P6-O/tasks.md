# P6-O · 任务清单（G-12 转正）

> 上游：`changes/P6-N/`。边界见 `proposal.md`（Non-goals **10 条，编号列表**）。
> **顺序不能反**：T1 是只读调查批，**先查证再造**。

- [ ] **T1 调查批（只读，¥0）**
      - [ ] T1.1 查 `domain_profile` 是否**有代码消费者**（全局 grep；无消费者 ⇒ 按 proposal §3
            O-D2 前置**不许写该字段**，需另找有实证的差异维度或升级用户）
      - [ ] T1.2 确认两个业务域（attendance / affiliation）的 `kg_version` **确实都在库里**
            （实证"差异是真的"；取真机读数，不要引文档）
      - [ ] T1.3 候选变体名过**契约词频检查**（proposal §2）⇒ 不为 0 就换名
      - [ ] T1.4 机械核对 `app_version`（决定 `base_ref` 写什么）
- [ ] **T2** 落地第二个变体 `deploy/variants/<名>.yaml`：
      字段对齐 `ADR-0007-plugin-delivery.md:73-85`；`customer` 值 = 文件名 stem；
      `base_ref` = T1.4 的机械读数
- [ ] **T3** 摘 `test_g12_variant_matrix_builds` 的 `@pytest.mark.xfail(strict=True)`；
      机械验证判据 ①（PASS）②（G-14 仍 PASS）③（`check_startup_readiness.py` G-12 → `[OK]`）
- [ ] **T4** **反向验证**：删掉第二个变体 ⇒ G-12 那条**变红**；还原 ⇒ 绿；
      `git grep` 确认无临时残留
- [ ] **T5** 门禁全绿（ruff / `check_seams` ERROR 0 / 契约零 diff / 全量 pytest ≥ 998）
      + `integration-log.md` + 需求基线 & `dev-doc-status.md` 的 G-12 状态登记
      （**保留**"绿灯只代表机制可跑、不代表多客户交付已验证"这条注记）
- [ ] **T6** 摊 diff（自动提交；push 失败先重试，仍失败就把命令给用户）
