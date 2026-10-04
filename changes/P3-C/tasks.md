# P3-C 任务清单 —— 修「`SET LOCAL` 后 GUC 变空串 ⇒ `''::uuid` 报错」（P3-B 未决 #1）

> 边界见 `proposal.md` §2（**开工前先读 Non-goals**）。起跑：`pytest` **888 passed**。

- [x] **C1** `app/db/rls.py`：谓词改 `nullif(current_setting('app.current_org', true), '')::uuid`
      + 改模块 docstring 第 3 条与函数 docstring（原说法"未设即 NULL"**本身是错的**）
- [x] **C2** 新迁移：14 张租户表幂等重建策略（DROP + CREATE），`downgrade` 回退旧谓词
- [x] **C3** `tests/test_guardrails_rls.py` **判据 8**：同一条连接上"先绑 org 跑一次、再不绑 org 查"
      ⇒ **0 行不抛错**；并断言此时 GUC 是 `''`（把事实钉进测试）
- [x] **C4** 反向验证：去掉 `nullif` ⇒ C3 判红
- [x] **C5** 文档：需求基线 DR-B4 / G-26 行；`changes/P3-B/integration-log.md` 未决 #1 关闭；
      `changes/P3-C/integration-log.md`
- [x] **C6** 收束门禁：pytest（+1）/ ruff 双绿 / 接缝 OK 10 / 契约零漂移 / readiness G-26 +1

## 不做（改完回头逐条对照）

1. 审查"哪里会漏绑 org"（另案）
2. 同时改 `session.py::after_begin`（与 C1 二选一）
3. G-25
4. 改契约 / ADR-0003 原文
5. 改租户表清单 / 豁免表 / 受控函数
