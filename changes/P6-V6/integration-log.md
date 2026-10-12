# P6-V6 集成日志（**实测证据**）

> 与 [`proposal.md`](./proposal.md) §5 的 K1~K6 一一对应。
> 本批所有结论均来自**命令输出**，没有一条来自文档转述或推理。

---

## 1. V6-a：到底是谁以 superuser 挂在临时库上

### 1.1 CI 原始日志（`gh run view --job 114640885816 --log-failed`，非转述）

```
run 38196713884 / head 60a5bbb（docs-only）
query = 'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %(name)s'
params = {'name': 'graphrag_rbac_547ca1bbda2f'}
E  psycopg.errors.InsufficientPrivilege: permission denied to terminate process
E  DETAIL:  Only roles with the SUPERUSER attribute may terminate processes of
            roles with the SUPERUSER attribute.
1 failed, 1282 passed, 7 skipped
```

### 1.2 角色属性（`docker exec graphrag-pg psql -U graphrag -c ...`，本地实读）

| rolname | rolsuper | rolbypassrls |
|---|---|---|
| `graphrag` | **t** | t |
| `app_owner` | f | f |
| `app_rls` | f | f |

⇒ 建库 / 删库走的 `app_owner` **不是 superuser**；`graphrag` 是唯一超级用户。

### 1.3 抓现行（把 autovacuum 限速到 `cost_delay=100ms / cost_limit=1` 钉住它）

```
[row] (1342, 'client backend',    'app_owner', '', 'idle',   False, 'ROLLBACK')
[row] (1347, 'autovacuum worker', None,        '', 'active', None,  'autovacuum: VACUUM ANALYZE public.churn')
[A] HIT -> (1347, 'autovacuum worker', None, '', 'active', None, 'autovacuum: VACUUM ANALYZE public.churn')
[B] app_owner 去 terminate 这个 pid
    (psycopg.errors.InsufficientPrivilege) permission denied to terminate process
    DETAIL: Only roles with the SUPERUSER attribute may terminate processes of
            roles with the SUPERUSER attribute.          ← 与 CI 逐字一致
[C] app_owner 直接 DROP DATABASE（worker 还在）
    (psycopg.errors.ObjectInUse) database "probe_v6a" is being accessed by other users
```

**⇒ 根因假设证实（不是证伪）**：元凶是 `backend_type = 'autovacuum worker'`，
它以 **bootstrap superuser** 身份运行（故 `usename` 为 NULL，但角色是 superuser），
`app_owner` 既杀不掉它、它又照样阻塞 `DROP DATABASE`。

### 1.4 排除掉的备选

| 备选 | 排除依据 |
|---|---|
| 外部 superuser 客户端连到临时库 | 库名 `graphrag_rbac_<uuid12>` 一次性随机；且全仓 grep 确认**没有任何测试用超级用户连 scratch 库**（`graphrag:graphrag` 只出现在 config.py 默认值与 `init_rls_roles.py` 的 `--admin-url`，后者只连 `graphrag_test`） |
| `logical replication launcher` | 实读 `pg_stat_activity`：`usename=graphrag` 但 **`datname` IS NULL** ⇒ 不匹配 `WHERE datname = :name` |
| background writer / checkpointer / walwriter / autovacuum launcher | 同上，`datname` 全为 NULL |

---

## 2. 顺带实测：一次失败的 `DROP DATABASE` 会让 PG **干等 5 秒**

```
[drop #0] 5.06s -> OperationalError: ObjectInUse: database "probe_drop" is being accessed by other users
[drop #1] 5.08s -> 同上
[drop #2] 5.09s -> 同上
```

⇒ **不能用"反复 DROP"当重试手段**：真删不掉时要白等几十秒，且等待期间拿不到
"是谁占着"。改成**廉价轮询 `pg_stat_activity`**，等干净了再删一次。
（守卫用例耗时因此从 **55.4s 降到 5.8s**。）

---

## 3. 修法（`backend/tests/pg_scratch.py::drop_database()`，**只改这一个函数**）

1. **只踢踢得动的**：`backend_type = 'client backend'` + `usename = current_user`
   + `pid <> pg_backend_pid()`。
2. **剩下的不硬杀，等它自己走**：轮询 `pg_stat_activity`（10 × 0.5s）等该库上
   再无其他行；不在失败路径上重试 `DROP`。
3. **等不到就响**：抛 `RuntimeError`，并把残留连接的
   `pid / backend_type / usename / state / query` 全列出来。
   **不吞异常**（Non-goal 1 / R-9）；`DROP` 仍失败也一并转成这个错，不许静默。

---

## 4. 判据 K1~K6

| # | 判据 | 结果 | 证据 |
|---|---|---|---|
| **K1** | V6-a 有真实行证据、能指名"是谁" | ✅ | §1.3 抓到 `pid=1347 autovacuum worker`；以 app_owner terminate ⇒ 与 CI **逐字相同**的 `InsufficientPrivilege` |
| **K2** | 目标用例连跑 ≥ 5 次全过 | ✅ **6/6** | `run 1..6 : 1 passed`（2.79s ~ 4.22s） |
| **K3** | 反向守卫：造"杀不掉的连接" ⇒ 必须报错、不许静默 | ✅ | 新增 `tests/test_pg_scratch_drop.py::test_drop_database_raises_instead_of_silently_leaving_db`（用 `app_rls` 占库 ⇒ `pytest.raises(RuntimeError, match="删不掉")` + 断言库还在）；另配正向 `test_drop_database_kicks_own_role_connections` 证明过滤条件没写错 |
| **K4** | `pytest tests -q` 不降 | ✅ | 本地 **1251 passed / 43 skipped**（= 基线 1249/43 **+ 新增 2**）；CI 上 **1287 passed / 7 skipped**（= 基线 run `38198414806` 的 1285/7 **+ 2**） |
| **K5** | `ruff check .` + `ruff format --check .` 全量绿；`check_seams.py` OK 12 / ERROR 0 | ✅ | `All checks passed!` / `294 files already formatted` / `ERROR 0 / WARN 0 / OK 12`；另 `check_startup_readiness.py --self-test` 7 条全过 |
| **K6** | CI 全量 run 四项 success | ✅ | run **`38201283243`**（head `1d87a0f`）：后端 / 契约 / 前端 / 汇总 **全 success** |

---

## 5. 边界对照（6 条 Non-goals 逐条）

| Non-goal | 是否守住 |
|---|---|
| 1. 不许 `try/except` 吞异常 | ✅ 反而**新增**了"删不掉必须抛错"的显式路径（K3 钉住） |
| 2. 不许给 `app_owner` 提权 | ✅ `app_owner` 权限一字未改 |
| 3. 不许改测试断言让它绿 | ✅ 未碰 `test_rbac.py` 任何断言 |
| 4. 不顺带重构 `pg_scratch.py` | ✅ diff 只落在 `drop_database()` 内（含两个**嵌套** helper，未新增模块级函数） |
| 5. 不动 CI 的 PG 配置 | ✅ **未改 `ci.yml`**（根因不在 CI 配置 ⇒ D1 未触发） |
| 6. 不做交付动作 | ✅ 契约零漂移（CI 契约 job success） |

`check_session_drift.py`：S1 读到 6 条边界 / S2 `1 文件 / +100 行` / S3~S5 全清 ✅

---

## 6. 清理与遗留

- 临时探针 `backend/tmp_v6a_probe.py` **已删除**（未进版本库）；
  它对本地 PG 做的 `ALTER SYSTEM`（`autovacuum_naptime` / `cost_delay` / `cost_limit`）
  **已 `ALTER SYSTEM RESET` 并 `pg_reload_conf()`**，临时库 `probe_v6a` / `probe_drop` 已删。
- 已同步更正 `changes/P6-V4/new-session-prompt.md` §11 第 4 条那条「已知 flaky」
  —— 它不再成立（见该文件）。
- 已落成下一批提示词 `changes/P6-V6/new-session-prompt.md`（P6-V5：C3 真值 + TBD-7 裁决包）。

## 7. 本批**顺带实测**、但属于下一批（P6-V5）的事实

跑全量 `pytest tests -q` 做 K4 时，发现本机 `cost_metrics` **不再为空**（P6-V4 的口径是
「本机 / CI 均空」⇒ **已过期**）：

```
stage='extraction'  org_id=00000000-0000-4000-8000-000000000001
metric_date=2026-10-12   token_usage_total=0   doc_count=0   counted_doc_ids=[]
single_doc_cost=0   incremental_cost=NULL   full_rebuild_cost=4   cost_ratio=0
created_at=2026-10-12 03:47:29+00   ← 全量 pytest 的运行窗口
```

⇒ 这行是**测试写的**，不是真实抽取；`--live` 直接读 C3 会把它读成"真值"。
本批**不处置**（属 P6-V5 边界），已写进下一批提示词 §6 坑 4 + V0 判据：
**开工第一步先定位并隔离它**。
