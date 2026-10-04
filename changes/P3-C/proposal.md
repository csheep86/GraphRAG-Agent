# P3-C 提案 —— 修「`SET LOCAL` 结束后 GUC 变空串 ⇒ `''::uuid` 报错」（P3-B 未决 #1）

| 项 | 内容 |
|---|---|
| **批次** | P3-C（**单点 hotfix**，不是新功能） |
| **日期** | 2026-10-04 |
| **触发** | P3-B 集成日志 **未决 #1**：做 T1 补齐（`qa_logs`）时实测发现 |
| **状态** | 🟡 进行中 |
| **用户指令** | 「上面发现的缺陷按你建议先修」（采纳建议修法 ①） |

---

## 0. 缺陷（**实测复现**，不是读代码推测）

```text
-- 事务 1（应用正常路径：绑 org A）
SELECT set_config('app.current_org', '<uuid-A>', true);   -- SET LOCAL
SELECT … FROM qa_logs …;                                  -- ✅ 只看到 A 的行
-- 事务 1 结束（commit / rollback）

-- 事务 2（**同一个池化连接**、未绑 org 的系统路径 / 运维脚本 / 漏绑的通道）
SELECT current_setting('app.current_org', true);          -- ⇒ ''  ← 不是 NULL！
SELECT … FROM qa_logs …;
-- ⇒ ERROR 22P02: invalid input syntax for type uuid: ""
```

**根因**：`SET LOCAL` 在事务结束后会把自定义 GUC 还原到 **reset 值**，而自定义 GUC 的
reset 值是**空串**——不是"未设置"。于是 `app/db/rls.py` 的谓词
`org_id = current_setting('app.current_org', true)::uuid` 拿到 `''` 时做的是
`''::uuid` ⇒ **直接报错**，而不是设计文档承诺的「比较为 NULL ⇒ 一行不命中」。

**为什么这是缺陷而不是"更严格"**：ADR-0003 §3.3 与 `rls.py` 顶部三条硬约束之三写的
是 fail-closed（0 行）。现在是 **500**，且只在"该连接上跑过一次绑 org 的事务之后"
才出现 ⇒ **首次请求正常、第二次起崩**，是最难复现的那一类。

**影响面（已查证）**：`/api/v1/health` 不受影响（只 `SELECT 1`）；现有 888 条用例全绿
⇒ 当前无被测路径踩到。**但它是一颗定时炸弹**：任何"未绑 org 却查租户表"的新路径
（运维脚本 / 系统通道漏绑 / 逃生阀审计）都会踩到。

---

## 1. 修法（采纳建议 ①，最小改动）

| # | 落点 | 改动 |
|---|---|---|
| **C1** | `backend/app/db/rls.py::_policy_predicate()` | 谓词改为 `org_id = nullif(current_setting('app.current_org', true), '')::uuid` ⇒ 空串与 NULL **都**退化为 NULL ⇒ 比较不命中 ⇒ **0 行**（恢复文档承诺的 fail-closed）。同步改模块 docstring 第 3 条与函数 docstring（原注释里"未设即 NULL"的说法**本身就是错的**，必须一起改，否则下一个人还会踩） |
| **C2** | 新迁移 `<rev>_rls_predicate_nullif_empty_guc.py` | 14 张租户表**幂等重建**策略（DROP + CREATE）；`downgrade` 回退到旧谓词。**既有部署的升级路径**（`alembic upgrade head`）必须能拿到它 |
| **C3** | `backend/tests/test_guardrails_rls.py` 新增 **判据 8** | 在**同一条连接**上：先跑一个绑 org 的事务，再在不绑 org 的情况下查 ⇒ 断言 **0 行且不抛错**（顺便断言 GUC 此时确实是 `''`，把这个事实钉在测试里） |
| **C4** | 反向验证 | 把 `nullif(…)` 去掉 ⇒ C3 **必须红** |
| **C5** | 文档 | 需求基线 DR-B4 / G-26 行；`changes/P3-B/integration-log.md` 的未决 #1 关闭；`changes/P3-C/integration-log.md` |

### 出口判据

1. `pytest` passed 不减（888 起跑，+1 = 判据 8）；
2. 判据 8 在**真 PG** 上绿，且反向验证（去掉 `nullif`）判红；
3. 全部门禁：ruff 双绿 / 接缝 OK 10 / 契约零漂移 / readiness G-26 条数 +1。

---

## 2. Non-goals（本批**不做**）

1. ❌ **不修**「未绑 org 的查询为什么会发生」那一侧（系统通道 / 运维脚本的 org 绑定审查）——
   本批只保证**发生了也不会 500**，即恢复 fail-closed 语义；"哪里会漏绑"属另案；
2. ❌ **不动** `app/db/session.py` 的 `after_begin`（建议修法 ②）：与 ① 二选一，
   同时做会让人分不清到底靠哪一道；
3. ❌ **不做** G-25（评测判据进 CI）——与本批无关，仍未开工；
4. ❌ **不动**契约 / ADR-0003 原文（守 **R5**，差异登记在需求基线）；
5. ❌ **不扩** `RLS_EXEMPT_TABLES`、不改租户表清单、不改受控函数。
