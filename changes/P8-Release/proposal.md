# P8-Release · 上线 gate 终审（A6）

> **日期**：2026-10-13 ｜ **来源**：[`docs/delivery-plan.md`](../../docs/delivery-plan.md) §9.2 序 10 + [`docs/release-readiness-audit-2026-10-13.md`](../../docs/release-readiness-audit-2026-10-13.md) §3 A6
> **一句话**：把矩阵逐行对一次账，走完「gate 三件套」，出 `v2.0.0` release notes 并打 tag。
> 🔒 **零缺口**：所有 G 进 🟢；C1~C3 / 多跳 / 拒答全达标且**不触发 F1~F5**。

## 1. 前置（缺任一不得开工）

- [ ] **P6-T** 判分完成 ⇒ C1 与多跳真值非 `None`
- [ ] **P7-C / P7-D / P7-E** 完成（B1 / B2 / B3 / B4 / B6）
- [ ] **P7-F** 阈值已裁决并回填（C3 转 MEASURED）
- [ ] **P7-G / P7-H** 完成（交付缺陷 + 升级回滚双人留证）
- [ ] **P7-I** 完成（L2 端到端读数与差异登记）
- [ ] **P7-J** 完成（私钥离线处置）
- [ ] 本次审计 §5.1 的 5 处过期口径**已用机械读数复核后订正**

## 2. 做什么

1. **逐行对账**：`docs/acceptance-traceability-matrix.md` §3.1 / §3.4 / §4 / §5.1，**任一行「判据」或「验收人」为空 ⇒ 不得收尾**。
2. **gate 三件套**（`docs/dev-doc-status.md:162` P3-1）：`check_startup_readiness.py` 全 🟢、`check_seams.py --strict`、契约零漂移 + 前端 typecheck/lint。
3. `docs/release-notes/v2.0.0.md` + `app_version` bump + **tag `v2.0.0`**（bump 与打 tag 同一动作，漏 re-export 契约必红）。
4. 把**禁止外推项**写进 release notes 显著位置（例：G-12 绿灯只代表矩阵机制可跑，**不代表多客户交付已验证**）。

## 3. Non-goals

1. **不做任何 '顺便' 的功能修补**——发现缺口即"未达成"，登记后另立批次，**不许在终审期改产品**。
2. **不放宽任何判据、也不删除 xfail**（转正的唯一方式是让测试真的通过）。
3. **不替 P6-T 判分、不替 P7-H 签字**。
4. **不写没跑过的判据**（每条 claim 都要能贴机器输出）。

## 4. 出口判据

1. `check_startup_readiness.py`：🟢 全覆盖，🟠 / 🟡 / 🔵 **逐条有解释与处置登记**。
2. 矩阵全表无空判据 / 空验收人；每行状态与实际读数一致。
3. `check_seams.py --strict` 通过；`export_openapi.py --check` 零 diff；`gen:api` 无 diff。
4. C1~C3 / 多跳 / 拒答全部达标，**且 F1~F5 未触发**（触发 ⇒ 走显式降级决议，**不许偷发版**）。
5. release notes 落地 + tag `v2.0.0` 已推送并 `git ls-remote --tags` 可核。
6. CI 四 job 全绿。

## 5. 升级用户的四种情况

1. 任一条准入线未达标 ⇒ **停下**（要么补做，要么走 F1~F5 的显式降级决议）。
2. 发现新的零缺口项 ⇒ 回到 P7-* 队列补齐，不在本批扩范围。
3. 文档互相矛盾且判定不清 ⇒ 以**机器读数**为准并登记悬空引用。
4. CI 红且复核两遍仍红 ⇒ 带 job 名 + 失败行 + 归因。
