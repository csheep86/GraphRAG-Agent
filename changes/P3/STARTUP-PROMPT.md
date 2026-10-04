# P3-A 开工提示词（PG 侧租户隔离 RLS）

> 用途：另开新会话执行 P3-A 时，把下面「提示词正文」整段粘进去即可开工。
> 本文件**自包含**——不依赖本会话的任何上下文。

---

## 必读（按顺序）

1. `changes/P3/proposal.md` —— 八个坑的证据（每行都有文件行号，可复核）
2. `changes/P3/tasks.md` —— 本批**唯一**任务清单（裁决 + A1~A11 + 出口判据）
3. `docs/adr/ADR-0003-tenant-isolation-rls.md` §3.2 / §3.3 / §3.7 / §4.1 —— 权威口径
4. `docs/delivery-requirements-and-guardrails.md` 第 92-100 行（DR-B4 / B5 / B7 / B8 / B11 / B12）、第 169-170 行（G-9 / G-10）、第 206 行（B4「无独立断言」）

## 起跑基线（实测，2026-10-04）

`pytest` **853 passed / 3 skipped / 4 xfailed**｜接缝 OK 10｜契约零漂移｜`check_startup_readiness.py` 已生效 12 组
**RLS 零实现**：`backend/` 下 `CREATE POLICY` / `ROW LEVEL SECURITY` / `SET LOCAL` / `current_setting` 均 **0 命中**

## 已定裁决（**不许重开**）

| # | 裁决 |
|---|---|
| 1 | 跨租户**保留 403**（契约 `openapi.yaml:3121 / 3193 / 2867 / 1910` 明文且写「而非 404」）⇒ 存在性探测走**受控函数**（只返回 boolean + 表白名单） |
| 2 | 后台任务：`TaskSpec` **携带 `org_id`**，不开绕过口子 |
| 3 | 启动回收：**枚举租户 + 逐租户设 org**，**不给 `BYPASSRLS`** |
| 4 | CI 建**两个角色**：owner 建表 / 迁移，受限角色（`NOBYPASSRLS`）跑业务测试 |
| 5 | 只做 **P3-A（PG 侧）**；P3-B（图谱侧 + CI Neo4j + G-9 补齐）随 G-25，**不在本批** |

## 八个已识别的坑（落点见 tasks.md）

1. 依赖图顺序错：`get_session()` 拿不到身份，且 RBAC **先于**路由体查库（`deps.py:83-85` + `rbac/deps.py:61-69`）
2. `SET LOCAL` 每次 commit 后失效（`documents.py:246-248`）⇒ 必须挂 `after_begin` **每事务重放**
3. 后台任务不带 org ⇒ RLS 后**合法任务被误判成"记录不存在"**（`tasks/types.py:40-46` + `registry.py:106-113`）
4. **7 处**绕开请求依赖直建 Session（审计中间件 / 限流 / agent fail-open 审计 / 任务执行体 / manager / CLI）
5. 启动回收天然跨租户（`main.py:31-38` + `tasks/manager.py:183-205`）
6. 403 → 404：RLS 会让 11+ 条常驻 403 测试变红 ⇒ **按裁决 1 保留 403**
7. 表 owner 绕过 ⇒ CI 可能"全绿但 RLS 未验证" ⇒ 裁决 4（双角色）
8. 测试夹具直接访问租户表（`conftest.py:185-208` 等）⇒ `FORCE` 后失败

## Non-goals

❌ 不移除应用层 `org_id` 过滤（DR-B5：双防线并存）｜❌ 不写 `USING (true)`｜❌ 不新增 RLS 豁免表（唯一豁免 = `roles`；`users` **含** `org_id`）｜❌ 不做 P3-B / P2-C / P4 / G-23｜❌ 不改 ADR-0003 原文（守 R5）｜❌ 不为出口放宽判据

## 出口判据

- **G-26 常驻**（新增：RLS 策略机械断言，六条判据见 tasks.md §10）
- **G-10 转正**（先 XPASS 再摘 xfail；**只删标记不算转正**）
- `pytest` passed **不减 853**；xfailed ≤ 4；ruff 双绿；契约**零漂移**；接缝 ERROR 0；**CI 双角色下全绿**
- 集成日志 `changes/P3/integration-log.md`：实测数字 + 系统通道登记表 + A7 受控绕过登记 + G-26 实测结果

---

## 提示词正文（整段复制）

```
你要在本仓库执行批次 **P3-A（PG 侧租户隔离 RLS）**。开工前先按顺序读完这四份，再动代码：

1. changes/P3/proposal.md   —— 八个坑的证据（每行都有文件行号）
2. changes/P3/tasks.md      —— 唯一任务清单（已裁决，照做即可）
3. docs/adr/ADR-0003-tenant-isolation-rls.md §3.2 / §3.3 / §3.7 / §4.1
4. docs/delivery-requirements-and-guardrails.md 第 92-100、169-170、206 行

起跑基线（实测）：pytest 853 passed / 3 skipped / 4 xfailed；接缝 OK 10；契约零漂移。
RLS 当前零实现：backend/ 下 CREATE POLICY / ROW LEVEL SECURITY / SET LOCAL / current_setting 均 0 命中。

已定裁决（不许重开）：
1) 跨租户保留 403（契约明文写「而非 404」）⇒ 存在性探测改用受控函数（只返回 boolean + 表白名单）；
2) 后台任务 TaskSpec 携带 org_id，不开绕过口子；
3) 启动回收改为枚举租户逐租户设 org，不给 BYPASSRLS；
4) CI 建两个角色：owner 建表/迁移，受限角色（NOBYPASSRLS）跑业务测试；
5) 只做 P3-A；P3-B（图谱侧 + CI Neo4j + G-9 补齐）不在本批。

必须新增护栏 G-26（RLS 策略机械断言）——理由：需求基线第 206 行自认 B4「无独立断言」，
而 T1 通过不等于 RLS 生效（应用层 org_id 过滤本就能让 T1/T2 全绿）⇒ 没有独立断言的话
「RLS 已落地」无法机械证明。六条判据见 tasks.md §10。

纪律：
- 遇到两条要求冲突、或实现到一半发现原计划不成立 → 停下来，在 changes/P3/integration-log.md
  登记 BLOCKED 并写清证据，继续做其余项，不要卡住整批，也不要自行放宽判据或改规格。
- 不许猜：alembic head 用 `uv run alembic heads` 实测；含 org_id 的表清单以 models.py 为准逐表核对。
- 每条护栏转正必须「先真通过（strict xfail 下 XPASS ⇒ FAILED 即证据）再摘 xfail」，
  只删 xfail 标记不算转正。
- 不得改 ADR-0003 / 需求基线原文（守 R5），差异一律追加登记。
- 契约零漂移是硬要求（export_openapi.py --check 必须过）。

做完写 changes/P3/integration-log.md：实测前后数字、系统通道登记表、A7 受控绕过登记、
G-26 判据与实测结果、未决事项。最后跑全部门禁并汇报数字。
```
