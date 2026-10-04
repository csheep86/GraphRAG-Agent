# P3-C 集成日志 —— 修「`SET LOCAL` 后 GUC 变空串 ⇒ `''::uuid` 报错」（P3-B 未决 #1）

| 项 | 内容 |
|---|---|
| **批次** | P3-C（**单点 hotfix**，非新功能） |
| **日期** | 2026-10-04 |
| **触发** | P3-B 做 T1 补齐（`qa_logs`）时**实测撞到**，登记为 P3-B `integration-log.md` 未决 #1 |
| **用户指令** | 「上面发现的缺陷按你建议先修」（采纳建议修法 ①：谓词 `nullif`） |
| **出口判据** | `proposal.md` §1：① passed 不减；② 判据 8 真 PG 上绿 + 反向验证判红；③ 全部门禁 |

---

## 1. 门禁实测（**跑出来的**）

| 门禁 | 起跑（P3-B 收束后） | 收束（本批） |
|---|---|---|
| `uv run pytest -q` | **888 passed**（开真图开关） | **889 passed / 3 skipped / 3 xfailed**（+1 = G-26 判据 8） |
| `check_startup_readiness.py` | G-26 **11 项** | G-26 **12 项** |
| `ruff check` / `ruff format --check` | 双绿 | 双绿 |
| `check_seams.py` | 接缝 OK 10 / ERROR 0 | 接缝 OK 10 / ERROR 0 |
| `export_openapi.py --check` | 零漂移 | 零漂移 |

---

## 2. 改动清单

| 文件 | 改动 |
|---|---|
| `backend/app/db/rls.py` | `_policy_predicate()` → `org_id = nullif(current_setting('app.current_org', true), '')::uuid`；**模块 docstring 第 3 条与函数 docstring 一并改**（原写法"未设即 NULL"**本身就是错的**，不改会让下一个人继续踩） |
| `backend/migrations/versions/b7c4e1f9a2d3_rls_predicate_nullif_empty_guc.py`（新增） | 14 张租户表幂等重建策略（DROP + CREATE），`downgrade` 精确回退旧谓词 |
| `backend/tests/test_guardrails_rls.py` | 新增 **判据 8**：`test_g26_8_unbound_query_after_bound_txn_is_zero_rows_not_error` |
| `docs/delivery-requirements-and-guardrails.md` | DR-B4 行（谓词修正 + 迁移号 + 判据 8）、G-26 行（新增判据 ⑧、条数 25） |
| `changes/P3-B/integration-log.md` | 未决 #1 关闭（指向本批） |

**刻意没动**（Non-goals）：`app/db/session.py::after_begin`（与 ① 二选一，同时做会分不清靠哪道）、
"哪里会漏绑 org"的审查（另案）、契约、ADR-0003 原文、租户表清单 / 豁免表 / 受控函数。

---

## 3. 缺陷的**实测证据**（修之前）

```text
事务 1（绑 org A）：SELECT set_config('app.current_org', '<uuid-A>', true); SELECT … → 正常
事务 1 结束
事务 2（同一条连接、不绑 org）：
  SELECT current_setting('app.current_org', true)  ⇒ ''          ← 不是 NULL
  SELECT count(*) FROM documents
  ⇒ psycopg.errors.InvalidTextRepresentation: invalid input syntax for type uuid: ""
```

**根因**：`app.current_org` 是**自定义** GUC；自定义 GUC 在被 `SET LOCAL` 用过之后，
事务结束时会还原到它的 **reset 值**——那是**空串**，不是"未设置"。谓词裸 `::uuid`
⇒ 空串进 `uuid` 转换 ⇒ `22P02` ⇒ 500。

**为什么难发现**：只在"该连接跑过一次绑 org 的事务之后"才出现 ⇒ **首次请求正常、第二次起崩**；
`/api/v1/health` 不受影响（只 `SELECT 1`）；既有 888 条用例全绿（当前无被测路径踩到）。

---

## 4. 修复后的实测

| 场景 | 结果 |
|---|---|
| 判据 8：绑 org 跑一次 → 同一条连接不绑 org 再查 | **0 行，不抛错**（正向对照：绑了 org 时 ≥1 行） |
| `alembic upgrade head` 在**空库**上跑到底（生产升级路径） | 迁移 `b7c4e1f9a2d3` 执行成功；`pg_policies.qual` 实测为 `org_id = (NULLIF(current_setting('app.current_org'::text, true), ''::text))::uuid`（`documents` / `qa_logs` / `users` 抽查三张，USING 与 WITH CHECK 同式） |
| 反向验证：把 `nullif` 去掉 | `1 failed`，报错原文即上文 `invalid input syntax for type uuid: ""` ⇒ **判据 8 不是恒绿** |

> 既有部署两条路都能拿到修复：① `alembic upgrade head`（迁移）；
> ② compose 的 `db-init` 每次 `up` 都会以 owner 重放 `apply_tenant_rls`（DROP + CREATE，幂等）。

---

## 5. 未决事项

| # | 事项 | 级别 | 处置 |
|---|---|---|---|
| 1 | ~~"哪里会漏绑 org"尚未审查~~ | ✅ **已审（2026-10-04，P3-D）** | 见 `changes/P3-D/`：审计结论 = 运行时**没有**漏绑路径（唯一不绑的 `system_session()` 只调受控函数）；但暴露三个结构性缺口，已收口两个（**部署升级路径断** / **测试脚手架掩盖漏绑**），第三个（`/auth/login` 未来缺口）只登记不实现 |
| 2 | ADR-0003 §3.3 与 `docs/adr/ADR-0003-tenant-isolation-rls.md:87-88` 里仍写着旧谓词（裸 `current_setting(... )::uuid`） | 低 | 按 **R5 不改 ADR 原文**，差异已登记在需求基线 DR-B4 行；若日后要统一，需走登记流程 |
| 3 | G-25（评测判据进 CI） | 中 | 仍未开工；CI 的 `neo4j` service 已由 P3-B 建好 |
| 4 | `git push` 失败（2026-10-04 本批收束后） | 低 | 无人值守规则允许重试一次；两次均 `Connection was reset` / `Could not connect to github.com:443`（已知**间歇性网络**问题，与门禁 / 权限无关）。提交 `dd426d2f` 与日志提交**仍在本地**（`main...origin/main [ahead N]`）。**处理**：网络恢复后执行 `git push origin main`（用户上次连续重试第 9 次成功） |

---

## 6. 复现命令

```bash
cd backend
uv run pytest -q tests/test_guardrails_rls.py -k g26_8     # 判据 8
# 反向验证（去掉 nullif ⇒ 必须红）
#   把 app/db/rls.py 的 `nullif(current_setting('{ORG_GUC}', true), '')` 改回裸 `current_setting('{ORG_GUC}', true)` 再跑上面那条
uv run python scripts/check_startup_readiness.py            # G-26 应为 12 项
```
