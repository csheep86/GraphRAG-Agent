# P2 任务清单

> 与 [`proposal.md`](./proposal.md) 配套。**批次边界以 proposal §4 Non-goals 为准**。
> 每批收尾都要跑：`uv run python scripts/check_startup_readiness.py`，确认对应护栏**真的从「挂起」变「已生效」**。
> 只删 xfail、测试没真通过 —— **不算转正**（proposal 所引行动指引第 2 条）。

**状态（2026-10-01）**：**P2-A 进行中**（表 + 迁移 + G-18 转正）；P2-B / P2-C 未开工。
事后实测证据与遗留事项记 [`integration-log.md`](./integration-log.md)
（本文件是事前计划，两者不可互相替代）。

---

## P2-A — DR-B13 `users` 表（✅ 已完成）

### A0 开工前实测（2026-10-01）

| 探测量 | 实测结果 |
|---|---|
| `users` 是否有 spec | ✅ `specs/m5-permission-audit.md` §4.1，7 列口径明确 |
| Alembic head | `b3e5a1c70d42`（s9.13） |
| G-18 判据 | `test_guardrails.py:141`，只判「表存在」，`xfail(strict=True)` |
| G-24 连带风险 | 其 missing 列表含 `users` ⇒ 建表后**必须实测**它是否仍 XFAIL（不得假设） |
| `users` 的消费者 | **0 个** ⇒ 本批不接线、不加 API |

### A1 模型 —— `backend/app/db/models.py`

- [x] 加 `USER_STATUS_VALUES = ("active", "disabled")` + `class User(Base)`，
      `__tablename__ = "users"`，字段**逐字照 spec §4.1 的 7 列**
- [x] `__table_args__`：`ck_users_status`（两档）、`uq_users_username`（spec 的 unique）、
      `ix_users_org_id_status`（ADR-0003 §3.1：复合索引 `org_id` 打头）
- [x] `created_at` / `updated_at` 用既有 `utcnow` 惯例；模块文档补本批说明
- [x] 遗留登记：`username` 全局 unique（照 spec）与多租户同名账号的张力 —— 见 proposal RK-2
      （已登记至 `integration-log.md` §3 遗留 1 / `delivery-requirements-and-guardrails.md` §5 📌）

### A2 迁移 —— `backend/migrations/versions/`

- [x] 新增 `a1f3c9d27b08_add_users_dr_b13.py`，`down_revision = "b3e5a1c70d42"`
- [x] `upgrade()` 建表 + 三个索引/约束；`downgrade()` 对称 `drop_table`（含索引先删）
- [x] 验证：`alembic upgrade head` 后 `psql -Atc '\d users'` 见 7 列 + 约束齐备；
      `tests/test_migrations_baseline.py` 通过（迁移结果 == ORM 元数据）
- [x] 验证：downgrade 回 `b3e5a1c70d42` 后 `users` 消失（`\dt` 仅剩 12 张）

### A3 G-18 转正 —— `backend/tests/test_guardrails.py`

- [x] 摘掉 `test_g18_users_table_exists` 的 `@pytest.mark.xfail(strict=True)`
      （建表后它会 XPASS ⇒ CI 必红，**必须**当场处理）
- [x] **判据补强**（决策点 1）：表存在 **+** 列集合 == spec §4.1 的 7 列 **+**
      `org_id` 打头索引存在 **+** `username` 唯一约束存在
- [x] **RK-4 机械化**（你 2026-10-01「G-18 转正 ≠ 账号体系落地，看看怎么处理好」）：
      `test_g18_users_consumers_are_registered` —— `app/` 下任何引用 `User` 的模块
      必须先登记进 `USERS_CONSUMER_MODULES`（当前为**空**），并交代 ① 归属哪条 DR
      ② 所需列随本批迁移 ③ 接缝 1 是否需扩写 ADR-0004 §2.1 ④ 护栏是否同步转正；
      另在 `check_startup_readiness.py` 增 `SCOPE_CAVEATS`，G-18 绿灯旁**直接印出**这条边界
- [x] 同步改写 `docs/delivery-requirements-and-guardrails.md` 里 **G-18 那行的判据描述**（不许只改代码）
- [x] 反向确认：`test_g24_rbac_three_granularity_matrix` **仍 XFAIL**（实测不是 XPASS）

### A4 陈旧口径同步

- [x] `app/services/auth/local.py:5` —— 「users 表按 T10 裁决不建」改为「T10 已被 DR-B13 推翻，
      users 已于 P2-A 建表；本实现暂不查库，接线归 P2-C」
- [x] `docs/delivery-requirements-and-guardrails.md`：DR-B13 行状态更新；§5 状态清单把 G-18
      由「骨架已就位（挂起）」移入「已生效」区
- [x] `docs/delivery-plan.md` §8.1 的「ORM 表 = 12 张，没有 users」标注为开工前快照
- [ ] ⚠️ **未动** ADR-0003 原文（守 R5）：§3.1 第 77 行「users 本批次未建」是历史陈述，登记在本批日志

### A5 收尾三件套 + 留证 ✅

- [x] `uv run pytest -q` ⇒ **712 passed / 3 skipped / 7 xfailed**
      （基线 710 / 3 / 8：G-18 由 xfailed 转 passed，另新增敏感字段 1 条 ⇒ **xfailed 8 → 7、passed +2**，无失败）
- [x] `uv run ruff check .` + `uv run ruff format --check .`（186 files）⇒ 双绿
      ⚠️ 新迁移文件**不进 lint**（`pyproject.toml` 的 `extend-exclude = ["migrations"]` 既有裁决，非本批引入）
- [x] `uv run python scripts/check_startup_readiness.py` ⇒ **G-18 进 🟢**（已生效 **8 → 9** 条，G-18 共 2 项）；
      地雷区「users 表已建」❌ → **[OK]**（4 → 3 项）
- [x] `export_openapi.py --check` ⇒ **零漂移**（Non-goals 要求契约零 diff，实测达成）；`check_seams.py` 仍 ERROR 0 / OK 10
- [x] 实测证据写入 `changes/P2/integration-log.md`（含 `probe_users_migration.py` 的三步走留证）
- [x] 环境项（你 2026-10-01「改吧，未来也不用 sqlite 了」）：本机 `backend/.env` 的
      `DATABASE_URL` 由 `sqlite:///./dev.db` 改为 `postgresql+psycopg://...@localhost:5432/graphrag`
      （实测 `get_settings().database_url` 已读成 PG）。⚠️ 本机 dev 库需 `alembic upgrade head` 重建建表

### A-出口判据（一句话）

`check_startup_readiness.py` 里 **G-18 进「🟢 已生效」**，且 G-24 **仍是 XFAIL**。

### A-Non-goals（边界提醒）

- **不**做 RBAC（`roles` / `user_roles`）—— P2-B
- **不**接 SSO / 不新增接缝 1 实现 / **不改** `LocalAuthProvider` 语义 —— P2-C
- **不**加 API（契约零 diff）、**不**做用户 CRUD / 登录端点（0 消费者）
- **不**加 `documents.uploaded_by` 外键、**不**做数据回填
- **不**动 ADR 原文（R5）；**不**做 RLS（P3）、License（P4）

---

## P2-B — DR-B9 RBAC 三粒度

> 🚧 **开工闸门（新增，2026-10-01）**：本批第一次在 `app/` 里引用 `User` 时，
> 必须先把它登记进 `test_guardrails.py::USERS_CONSUMER_MODULES` 并交代四件事（见 A3 / 日志 §1.4），
> 否则 `test_g18_users_consumers_are_registered` 会红。

- [ ] `roles` 表（全局字典表，**RLS 显式豁免**，须在 Code Review 显式确认）
- [ ] `user_roles` 表（含 `doc_scope` / `scene_scope` JSONB，`org_id` 打头索引）
- [ ] 路由层**强制校验入口**（依赖 / 中间件）—— 没有它，权限只是库里的一列装饰
- [ ] 出口：`test_g24_rbac_three_granularity_matrix` 转正

## P2-C — DR-D9 SSO / AD

- [ ] **`先`扩写 `docs/adr/0004-integration-seams.md` §2.1 接缝 1 登记行**，再改 `get_auth_provider()`
      （漏改任一侧 CI 必红）
- [ ] 外部身份字段（`issuer` / `subject`）进 `users` + 自带迁移
- [ ] 出口：`check_seams.py` 接缝 1 实现集合 == 登记集合；AD / OIDC 登录可用

---

## 待你决策 ✅ 已按建议处置（2026-10-01）

1. ✅ 字段范围 ⇒ 逐字照 spec §4.1 的 7 列（外部身份 / 席位关联字段各自随 P2-C / P4 来）
2. ✅ `documents.uploaded_by` ⇒ **本批不加** FK（演示库有真实数据，回填不可逆）
3. ✅ `local.py` 的 T10 陈旧注释 ⇒ 改为「T10 已被 DR-B13 推翻」，**不删历史**
4. ✅ 类型与 spec TEXT 的差异 ⇒ 照既有先例 A9：按本仓惯例收敛并**登记**（守 R5）
