# P7-Q · 修 F-P7H-1：首次部署的建表路径（**升级阻断点**）

> **日期**：2026-10-14 ｜ **来源**：P7-H 升级+回滚演练挖出，留证见
> [`docs/drills/upgrade-drill-20261014.md`](../../docs/drills/upgrade-drill-20261014.md) §4 F-P7H-1
> **一句话**：客户按 §7.2 升级时 `alembic upgrade head` **一步都跑不动** ⇒ 必须把"首次部署怎么建表"定成唯一一条路。

## 1. 缺陷（P7-H 实测读数）

```
$ alembic upgrade head
Running upgrade  -> 00f44b912817, baseline sprint1-9.5 tables
psycopg.errors.DuplicateTable: relation "affiliation_suspicions" already exists
```

**不是"某一个迁移写错了"，是版本号无处可放**：把 `alembic_version` 拨到哪一段都会撞——

| 拨到 | 撞什么 |
|---|---|
| 基线 `00f44b912817`（默认，因为库里**根本没有** `alembic_version`） | `DuplicateTable: affiliation_suspicions` |
| 手工改到 `4e7759c33526` 附近 | `DuplicateColumn: documents.document_date already exists` |
| 手工改到 v1.6.0 的 head `b3e5a1c70d42` | `DuplicateTable: users already exists` |

⇒ 结论：**`create_all` 与 Alembic 是两套并行的建表机制，混用时升级路径必断。**
v1.6.0 → 1.7.0 之间新增 **9 个迁移 / 761 行**，客户会在第一个迁移就卡死，
而 §7.3 升级检查清单**没有任何一条**能提前发现它。

## 2. 根因坐标

| 坐标 | 内容 |
|---|---|
| `backend/scripts/init_rls_roles.py:174-175` | `if args.create_tables or not existing: Base.metadata.create_all(bind=connection)` —— **建了表，从不 stamp** |
| `deploy/docker-compose.delivery.yml` `db-init.command` | 交付编排显式带 `--create-tables` ⇒ 每个客户首次部署都走这条路 |
| `docs/deployment-spec.md` §7.2 第 4 步 | 升级时"执行数据库迁移（`alembic upgrade head`）" ⇒ 与上面那条路**撞车** |

## 3. 两条决定性证据（**决定了修法**）

1. **`create_all` 与 `alembic upgrade head` 的产物已被机械钉死等价**
   —— `backend/tests/test_migrations_baseline.py`：在 PostgreSQL 临时库跑迁移，
   再与 `Base.metadata`（`create_all` 的真源）比对**表集合与列集合**。
   ⇒ **改成用迁移建表，不会丢表、不会丢列**，等价性有现成的机械保障。

2. **这个坑项目里已经踩过一次**
   —— `backend/scripts/probe_temporal_state.py:94-98` 明写：
   "库未 stamp（head=…）⇒ 库是 `create_all` 建的，模型与库已漂移"。
   起因是 dev 库靠 `create_all` 演进、迁移从未应用 ⇒ `documents` 表**根本没有** `document_date` 列。
   ⇒ F-P7H-1 是同一个根因在**交付路径**上的复现，不是新问题。

## 4. 方案（两个候选，**推荐 A**）

### 方案 A（推荐）：首次部署也走 `alembic upgrade head` —— 迁移是**唯一**建表途径

- `db-init` 不再 `create_all`；改为**先跑迁移建表**（owner 串，脚本已有 `--admin-url`），
  再建角色 / 落 RLS 策略。
- 交付 compose 去掉 `--create-tables`。
- ⚠️ **要处理的重叠**：迁移 `8210590e76a5` 本身也落 RLS 策略，而 `db-init` 也落。
  实现时必须定清**谁落策略**（两边都落 ⇒ `CREATE POLICY` 不幂等会报错），
  建议：策略统一由**迁移**落，`db-init` 只负责**建角色**（角色必须由超级用户建一次，迁移做不到）。
- 优点：迁移历史与库结构**始终对应**，从此不再有"stamp 到哪"的问题。

### 方案 B（保守）：`create_all` 之后强制 `alembic stamp head`

- 改动最小：`db-init` 建表后补一次 stamp（承认结构已由 `create_all` 建立，靠证据 1 的等价性兜底）。
- 之后新增迁移会正常执行（版本号已在 head）。
- 缺点：库结构**仍来自模型而非迁移**，历史与结构依旧脱钩；将来若有人手工改库，仍然查不出来。

> **推荐 A**：既然证据 1 已经把等价性钉死，换成迁移建表**没有额外风险**，
> 而且它一次性根除"两套建表机制"这个根因。B 只是把症状推后。

### 不选：给迁移加 `IF NOT EXISTS`（`checkfirst`）

治标：迁移语义被破坏（`CREATE TABLE` 变成"能建就建"），
后续迁移若真要建同名对象会被静默跳过 ⇒ **更隐蔽的错**。不做。

## 5. Non-goals（改一条都要先回来登记理由）

1. **不动 dev / 测试路径** —— `main.py:38` 的 lifespan `create_all` 兜底、
   `conftest.py` 的建表夹具一律不动（它们本来就不跑迁移，且有证据 1 的等价性测试兜住）。
2. **不改既有迁移脚本的内容**（`migrations/versions/*` 一个字节都不改）。
3. **不顺手改 RLS 策略的内容**，只定清"由谁落"。
4. **不在本批重做 §6.2 或备份/恢复**。

## 6. 出口判据（**四条全过**）

1. **空库首次部署**：按新的 `db-init` 流程在**空库**上跑一遍 ⇒ 库 schema 与
   `Base.metadata` **完全一致**（直接复用 `test_migrations_baseline.py` 的比对逻辑，
   或把它抽成可复用函数后调用）。
2. **升级真的能跑**：在该库上再跑一次 `alembic upgrade head` ⇒ **不再撞 `DuplicateTable`**，
   且 `alembic current` 等于 head `a1f7c2b93d04`。
3. **重跑 P7-H 演练**（本批真正的验收）：重做一次
   `v1.6.0 → 1.7.0 → 回滚 v1.6.0`，本次**迁移必须真跑通**，
   且留证 `docs/drills/upgrade-drill-<日期>.md` 里 F-P7H-1 一条**关闭**。
   ⚠️ 演练仍是**双人批次**：执行者 ≠ 见证者，见证者一栏须人工签真名。
4. `pytest` 不降、CI 绿。

## 7. 验证步骤（给执行者）

```bash
# ① 空库建表（用独立 PG，别碰 dev 库）
docker compose -f deploy/docker-compose.delivery.yml -f <override> up -d postgres db-init
# ② 比对 schema 与 Base.metadata（判据 1）
# ③ 再跑一次 upgrade head（判据 2，应 no-op 或真跑新迁移，不报错）
# ④ 重跑 P7-H 演练（判据 3）
```

## 8. 风险与回滚

- **改交付编排** ⇒ 必须同步改 `docs/deployment-spec.md` §4.2（首次部署）与 §7.2（升级），
  两处不一致又会造出下一个 F-P7H-1。
- 若方案 A 在空库上发现"迁移建不全"（证据 1 的等价性测试若红）⇒
  **立刻停下**，那是比 F-P7H-1 更严重的问题（说明有表只在 `create_all` 里、没有迁移），
  按 §5 第 2 条另立批次补迁移，不要在现场改迁移内容。

## 9. 遗留（本批**不**处理，登记）

| 编号 | 内容 |
|---|---|
| F-P7H-2 | Windows 无 `/etc/machine-id` ⇒ 容器指纹回落 MAC ⇒ License mismatch。演练用"挂宿主 machine-id"绕过；**非产品缺陷，但每次演练都要照此处理** |
| F-P7H-3 | 回滚只改 tag（§7.3 不承诺回滚迁移）；"旧代码读新结构"上次未被真正加压（因库是 `create_all` 建的）⇒ **本批修完 A 之后，这条要重新验一次** |
| F-P7O-1 | dev 图库 248 个脏 `:KgVersion`（评测跑批写入），未清理 |
