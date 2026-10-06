# P6-O · 任务清单（G-12 转正）

> 上游：`changes/P6-N/`。边界见 `proposal.md`（Non-goals **10 条，编号列表**）。
> **顺序不能反**：T1 是只读调查批，**先查证再造**。
> 进度与实测：**2026-10-06 T1–T5 已完成**，证据见 `integration-log.md`。

- [x] **T1 调查批（只读，¥0）**
      - [x] T1.1 查 `domain_profile` 是否**有代码消费者**（全局 grep；无消费者 ⇒ 按 proposal §3
            O-D2 前置**不许写该字段**，需另找有实证的差异维度或升级用户）
            → **实测：`backend/` 0 命中（全仓仅 ADR-0007 与 P6-O 文档提及）⇒ 零消费者**
      - [x] T1.2 确认两个业务域（attendance / affiliation）的 `kg_version` **确实都在库里**
            （实证"差异是真的"；取真机读数，不要引文档）
            → **实测：`kg_versions` 仅 1 条 `attendance-demo-v1`；`affiliation_tasks` / `affiliation_suspicions` = 0 ⇒ 前提不成立**
      - [x] T1.3 候选变体名过**契约词频检查**（proposal §2）⇒ 不为 0 就换名
            → **实测：`internal-demo` = 0 次（对照 `demo` 3 / `default` 60）⇒ 可用**
      - [x] T1.4 机械核对 `app_version`（决定 `base_ref` 写什么）
            → **实测 `get_settings().app_version` = 1.6.0 ⇒ `base_ref: v1.6.0`**
- [x] **T2** 落地第二个变体 `deploy/variants/internal-demo.yaml`：
      字段对齐 `ADR-0007-plugin-delivery.md:73-85`；`customer` 值 = 文件名 stem；
      `base_ref` = T1.4 的机械读数
      （⚠️ **未写 `domain_profile`**：零消费者 + 差异实证不成立，见 `integration-log.md` §5）
- [x] **T3** 摘 `test_g12_variant_matrix_builds` 的 `@pytest.mark.xfail(strict=True)`；
      机械验证判据 ①（PASS）②（G-14 仍 PASS）③（`check_startup_readiness.py` G-12 → `[OK]`）
      （摘前实测 `[XPASS(strict)] ⇒ FAILED`）
- [x] **T4** **反向验证**：删掉第二个变体 ⇒ G-12 那条**变红**；还原 ⇒ 绿；
      `git grep` 确认无临时残留
- [x] **T5** 门禁全绿（ruff / `check_seams` ERROR 0 / 契约零 diff / 全量 pytest 0 回归）
      + `integration-log.md` + 需求基线 & `dev-doc-status.md` 的 G-12 状态登记
      （**保留**"绿灯只代表机制可跑、不代表多客户交付已验证"这条注记）
      （⚠️ 绝对值 ≥998 以 **CI 终裁** —— 本地 991 = 999 − 8 条真图用例 skip，见日志 §4 ④）
- [x] **T6** 摊 diff（自动提交；push 失败先重试，仍失败就把命令给用户）+ **CI 实证回登**
      → **提交 ✅**：`8e80935`（7 files / +144 / −28）+ `2afb855`（状态登记）
      → **push ✅ 第 19 次成功**（前 18 次 `Recv failure` / `Failed to connect ...443`，**非 DNS**；
      **未**用 force、**未**换远程）
      → **CI ✅ 全绿**：run **`37433603894`**（sha `2afb855`）四 job success；后端 pytest
      **997 passed / 5 skipped / 2 xfailed / 0 failed**（CI 基线 996 ⇒ **+1 = G-12 转正，0 回归**）
      → ⚠️ **判据 ④ 的字面阈值 998 未达**：本地 991 = 999 − 8 条真图用例 skip；CI 997 = 基线 996 + 1。
      差值已归因，**判据本身未放宽**（启用条件仍 ≥2）
