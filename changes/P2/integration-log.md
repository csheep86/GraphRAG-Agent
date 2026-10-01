# P2 实测集成日志

> **定位**：事后实测证据。事前计划见 [`proposal.md`](./proposal.md)、任务清单见 [`tasks.md`](./tasks.md)。
> 三者不可互相替代——**计划写"打算怎么做"，日志写"实际发生了什么"**。
>
> 批次：**P2-A（DR-B13 `users` 表）**｜日期：2026-10-01
> 环境：Windows 11 + Docker Desktop + `postgres:16-alpine` + Python 3.11 / uv

---

## 0. 起跑状态（`check_startup_readiness.py` 实测）

已生效 **8** 条、部分生效 **2** 条、挂起 **4** 条、开工地雷 **4** 项，
其中 **「users 表已建（DR-B13，P2 第一步）」= ❌**；G-18 与 G-24 均为 xfail 挂起。

---

## 1. P2-A 实测

### 1.1 表结构（PG 16 真机，`changes/P2/probe_users_migration.py`）

```
users 列       = ['created_at', 'id', 'org_id', 'password_hash', 'status', 'updated_at', 'username']
users 索引     = [['org_id'], ['org_id', 'status'], ['username']]
users 唯一约束 = [['username']]
users 检查约束 = ["status::text = ANY (ARRAY['active', 'disabled'])"]
alembic_version = a1f3c9d27b08
```

三条与 expected 完全一致：7 列（逐字照 `specs/m5-permission-audit.md` §4.1）、
`org_id` 打头索引（ADR-0003 §3.1）、`username` 唯一（spec §4.1）。

### 1.2 迁移三步走（同一个脚本，`downgrade base` 之外补了「只退一步」）

| 步骤 | 实测 |
|---|---|
| `upgrade head` | 13 张表，`users` 在列；`alembic_version = a1f3c9d27b08` |
| `downgrade b3e5a1c70d42`（**退一步**） | 12 张表，`users` 消失，**其余表不受影响** |
| 再 `upgrade head`（重放） | 13 张表，`users` 回来 ⇒ 不是单行道 |

为什么要单独验「退一步」：`tests/test_migrations_baseline.py` 只验了 `downgrade base`
（全退到空）——**退一步的安全性没人验**，而现场回滚正是退一步，不是退到零。

### 1.3 G-18 转正（不是"只删 xfail"）

建表后 `test_g18_users_table_exists` 由 **XFAIL 变 XPASS(strict) ⇒ FAILED**（CI 必红），
这与 P1-C 处理 G-8 / G-9 的情形相同。**同时把判据补强**到四条：

1. 表存在；
2. 列集合 **逐字等于** spec §4.1 的 7 列（不多不少）；
3. 有 `org_id` **打头**的复合索引（ADR-0003 §3.1）；
4. `username` 有唯一约束。

只摘标记不动判据的话，删掉 `org_id`、改名 `username`，G-18 依然绿 —— 那是假防御。
另加 `test_g18_password_hash_is_not_in_public_contract`：敏感字段不得出现在契约里。

**反向确认（不得假设）**：`test_g24_rbac_three_granularity_matrix` 仍 **XFAIL**
—— 它的 missing 列表虽然划掉了 `users`，但 RBAC 主体（`roles` / `user_roles` /
端点强制校验）依旧零代码 ⇒ 本批**没有**把 P2-B 逼上台面。

### 1.4 RK-4 机械化：「G-18 转正 ≠ 账号体系落地」（你 2026-10-01 交代）

只写进文档的边界**三个月后没人会翻**，而 G-18 的绿灯**看起来**就像"用户体系做完了"。
所以做了两层机械处置（对应 proposal RK-4）：

| 层 | 做法 | 实测 |
|---|---|---|
| **看得见** | `check_startup_readiness.py` 新增 `SCOPE_CAVEATS`，G-18 绿灯**正下方**印出：⚠️ 只验「users 表存在且形状正确」——它当前 0 消费者；SSO / RBAC / License 分属 P2-C / P2-B / P4 | 已实测打印出来（G-18 = 3 项） |
| **拦得住** | `test_g18_users_consumers_are_registered`：`app/` 下任何引用 `User` 的模块必须先登记进 `USERS_CONSUMER_MODULES`（**当前为空**），并交代 ① 归属哪条 DR ② 所需列随本批迁移 ③ 接缝 1 是否需扩写 ADR-0004 §2.1 ④ 护栏是否同步转正；反向也查「登记了却无引用」的僵尸登记 | **注入验证**：临时加一个引用 `User` 的文件 ⇒ 测试 **红**；删除后转绿 ⇒ 它真在拦，不是恒绿 |

与 CODEBUDDY.md「预留必须有登记」是同一条纪律，只是这里拦的是**引用**而不是字段。
它**不**拦"表还没人用"——那正是本批预期；它拦的是"有人开始用了却没登记、没交代归属"。

### 1.5 环境项（你 2026-10-01「改吧，未来也不用 sqlite 了」）

本机 `backend/.env` 的 `DATABASE_URL`：`sqlite:///./dev.db` ⇒
`postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag`（实测
`get_settings().database_url` 已读成 PG）。该文件不进 git，改它只影响本机。
⚠️ **本机 dev 库要重建**：切过去后旧 SQLite 数据自然弃用，首次使用跑
`uv run alembic upgrade head` 建表（旧 `dev.db` 我没删，留在 `backend/` 等你处置）。

### 1.6 陈旧口径同步（三类，都不动 ADR 原文）

| 位置 | 原口径 | 处置 |
|---|---|---|
| `app/services/auth/local.py:5` | 「users 表按 **T10** 裁决不建」 | 改为「T10 已被 **DR-B13** 推翻；users 已于 P2-A 建表；**本实现仍不查库**，接线归 P2-C」。**不删** T10 原始记录 |
| `docs/delivery-requirements-and-guardrails.md` | DR-B13 行「❌ 未建」、G-18 行「🟡 骨架已就位」、§3.1 B13 行「待建」、§5 状态清单 | 全部更新为 ✅ 已建 / 已生效，并登记三条差异与遗留 |
| `docs/delivery-plan.md` §4 注 / §8.1 | 「ORM 12 张，没有 users」 | 标注为**开工前快照**，P2-A 后已 13 张 |

`ADR-0003` §3.1 第 77 行「`users` 本批次未建」**未动** —— 守 **R5**（不篡改 ADR 原文），
差异与状态登记在 `delivery-requirements-and-guardrails.md` §5 的 📌 三条里。

---

## 2. 收尾三件套

| 检查 | 起跑 | P2-A 后 |
|---|---|---|
| `uv run pytest -q` | 710 passed / 3 skipped / **8 xfailed** | **713 passed / 3 skipped / 7 xfailed**（G-18 从 xfailed 转 passed，另新增 G-18 两条：敏感字段 / 消费者登记；**无失败**） |
| `ruff check .` / `ruff format --check .` | 双绿 | 双绿（186 files） |
| `check_startup_readiness.py` | 已生效 8 条、地雷 4 项 | **已生效 9 条**（G-18，**3 项**）、**地雷 3 项**，「users 表已建」✅；G-18 绿灯下方新增边界提示（§1.4） |
| `export_openapi.py --check` | 零漂移 | **零漂移**（本批 Non-goals 要求契约零 diff，实测达成） |
| `check_seams.py` | ERROR 0 / OK 10 | ERROR 0 / OK 10（未受影响） |
| `check_session_drift.py` | 指向 `changes/P1` | 指向 `changes/P2/proposal.md`（8 条边界） |

> ⚠️ 新迁移文件**不进 lint**：`backend/pyproject.toml` 的 `[tool.ruff] extend-exclude = ["migrations"]`
> 早已裁决（autogenerate 产物人工审阅入库，等价性由 `test_migrations_baseline.py` 钉死）。
> 单独跑它会报 UP035 / I001 —— 与既有 5 个迁移文件同形态，**不是**本批引入的。

---

## 3. 遗留（**不在本批边界内**）

| # | 事项 | 去向 |
|---|---|---|
| 1 | `username` 按 spec 取**全局 unique**，与多租户「同名不同 org」存在张力 | 若真出现，单开一批改 `(org_id, username)` 复合唯一（proposal RK-2） |
| 2 | `documents.uploaded_by` / `ontology_schemas.confirmed_by_user` **未**加指向 `users.id` 的外键 | 演示库已有真实数据，补 FK 属**不可逆**清洗；随 P2-C 首次真实账号链路一并处理 |
| 3 | `users` 表**仍 0 消费者** | 接线分属 P2-B（RBAC）/ P2-C（SSO）/ P4（License） |
| 4 | PG 容器 `graphrag-pg` 仍在跑（`-p 5432`），本地 pytest 需要它 | 不用时 `docker stop graphrag-pg`（`--rm` 会自动删除） |
| 5 | 本机残留旧 SQLite 文件 `backend/dev.db`（2.1 MB）与 `_alembic_empty.db`（280 KB） | 切 PG 后已无用途；**我没删** —— 若要清理等你一句话 |
| 6 | P2-B / P2-C 接线时**必须先登记** `USERS_CONSUMER_MODULES` | 判据已就位（§1.4），登记即那批的开工闸门 |

---

## 4. 边界声明（写在最后，防止被日后外推）

- **G-18 转正 ≠ 账号体系落地**。本批只证明「`users` 表存在且形状正确」：
  它没有登录、没有权限、没有席位，三者分别归 **P2-C / P2-B / P4**。
- **本批没有动任何认证语义**：`LocalAuthProvider` 仍走 dev token / dev header，
  **不查库**（一查全线测试就红）；接缝 1 的实现集合仍是 `{LocalAuthProvider}`，
  改它必须先扩写 ADR-0004 §2.1（否则 CI 必红）。
- **范围已守死**：契约零 diff、零 API、零 CRUD —— `users` 此刻是一张**没有被调用的表**，
  这是「先解阻塞」的有意为之，不是半成品。
