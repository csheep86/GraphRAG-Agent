# 升级 + 回滚演练留证（P7-Q · 重跑 P7-H，关闭 F-P7H-1）

> ⚠️ **内部演练，非客户现场验收**。本文件记录的是**在开发者本机（Windows + Docker Desktop）
> 用交付镜像**完成的一次「1.6.0 → 1.7.0 → 回滚 1.6.0」，目的是验证 P7-Q 的出口判据
> （`changes/P7-Q/proposal.md` §6）。它**不代表**任何客户环境已验收。

| 项 | 内容 |
|---|---|
| 日期 | 2026-10-14 |
| 批次 | P7-Q（[`changes/P7-Q/proposal.md`](../../changes/P7-Q/proposal.md)） |
| 被复现的缺陷 | **F-P7H-1**（首次部署的建表路径 = 升级阻断点），原始留证见 [`upgrade-drill-20261014.md`](./upgrade-drill-20261014.md) §4 |
| 环境性质 | **独立**：compose 项目 `graphrag-p7q-drill` / 独立数据卷 / 独立端口（8011 / 3011 / 7477 / 7691）/ 独立 `.env`，**由固定 tag 镜像起**（无 `build:`） |
| 执行者 | AI（本机执行，读数见下） |
| 见证者 | **（待签真名——本栏不得由执行者代填）** |

---

## 1. 环境

| 项 | 值 |
|---|---|
| compose 项目名 | `graphrag-p7q-drill`（卷名随之隔离；`graphrag-drill` 恢复演练栈与 dev 库**全程未动**） |
| 基础编排 | `deploy/docker-compose.delivery.yml` 的**副本**，只改四组端口 + 两个挂载（见下） |
| 镜像 | 旧 = `graphrag-agent/backend:1.6.0`（`2fcd0ed1389e`）/ `frontend:1.6.0`（`6e0c62a6a2f6`）；<br>新 = `backend:1.7.0`（`ea8042213985`）/ `frontend:1.7.0`（`c94567ce41f9`），**本批用 `build_delivery_images.py` 现构建**（旧镜像里的 `init_rls_roles.py` 还是修之前的） |
| License | 本机 `deploy/license/app.lic` 只读挂到 `/app/deploy/license/app.lic` |
| Windows → machine-id | 宿主 `MachineGuid` 写入临时文件后挂到 `/etc/machine-id`（F-P7H-2 的同款处置） |
| 备份 | 升级前 `pg_dump` → **52,564 B** |

> 演练用的 `.env` / 编排副本 / 比对脚本 / 备份 SQL / machine-id 全部放在**系统临时目录**
> （`%TEMP%\graphrag-p7q-drill`），**未入库**（`.env` 含口令，按纪律禁止入库）。

---

## 2. 判据 1 / 2：**空库**首次部署由迁移建表

`docker compose up -d postgres db-init`（1.7.0，空库）⇒ db-init 日志：

```
[INFO] 空库 ⇒ 由迁移建表（首次部署；建表只此一条路）
INFO  [alembic.runtime.migration] Running upgrade  -> 00f44b912817, baseline sprint1-9.5 tables
...
INFO  [alembic.runtime.migration] Running upgrade df5ec5c9e1b1 -> a1f7c2b93d04, add cost_metrics stage column (X-6)
[INFO] 建表 / 升级：空库：由迁移建表（14 个迁移真跑）
[OK] 16 张租户表的 tenant_isolation 策略已就位（ENABLE+FORCE）
```

**判据 1（schema == `Base.metadata`）**——在 backend 容器内以 owner 串比对：

```
alembic_version: a1f7c2b93d04
missing_tables: []
extra_tables: []
column_diff: {}
RESULT: EQUAL
```

**判据 2（再跑一次 `alembic upgrade head`）**：

```
upgrade_exit=0
（Running upgrade 条数）0
alembic current → a1f7c2b93d04 (head)
```

⇒ 不撞 `DuplicateTable`、不重复执行，`current` 等于 head `a1f7c2b93d04`。**判据 1 / 2 过**。

---

## 3. 判据 3：重跑 `1.6.0 → 1.7.0 → 回滚 1.6.0`

### 3.1 读数

| 阶段 | 镜像 tag | `GET /api/v1/health` 的 `version` | 前端 SSR | 受保护端点 | 库里的 `alembic_version` |
|---|---|---|---|---|---|
| **升级前** | `1.6.0` | **1.6.0** | 200 / 45313 B | `/documents` **401**（未认证） | **无此表**（`create_all` 建的库，`information_schema` 计数 = 0） |
| **升级后** | `1.7.0` | **1.7.0** ✅ | 200 / **10483 B** | 开户 + 登录 `token_len=279` ⇒ `/documents` **200**、`/audit` **200** | `a1f7c2b93d04 (head)` |
| **回滚后** | `1.6.0` | **1.6.0** ✅ | 200 / 45313 B（复原） | 登录 `279` ⇒ `/documents` **200**、`/audit` **200** | `a1f7c2b93d04`（stamp 保留；1.6.0 不读它） |

### 3.2 升级那一步的 db-init 日志（**本批的核心读数**）

```
INFO  [alembic.runtime.migration] Running stamp_revision  -> a1f7c2b93d04
[INFO] 建表 / 升级：遗留库：比对通过 ⇒ stamp head（未真跑迁移，原因见上）
[OK] 16 张租户表的 tenant_isolation 策略已就位（ENABLE+FORCE）
```

⇒ **升级不再被阻断**（db-init 退出 0 ⇒ backend 正常起）。这是与 P7-H 那次的**唯一**实质差别：
那次是"手工把版本号拨到 head 才继续"，这次是**脚本自己按判据决定**，且决定之前先做了机械比对。

### 3.3 ⚠️ 与判据 3 原文的偏差（**如实登记，请用户裁决**）

> 判据 3 原文：「本次**迁移必须真跑通**」。

在 **1.6.0 遗留库**上这一条**不可能成立**，且不是实现偷懒：

- 那 9 个迁移（v1.6.0 → 1.7.0 新增）是**追平模型**的迁移——它们要建的表 / 列，`create_all`
  早就建好了。机械证据：本次遗留库的比对结果 `missing_tables=[]` 且**无列缺口**
  （若有一处缺，脚本会**报错退出**而不是 stamp）；
- P7-H 那次已实测"把版本号拨到哪一段都会撞"（基线 ⇒ `DuplicateTable: affiliation_suspicions`；
  `b3e5a1c70d42` ⇒ `DuplicateTable: users already exists`）。

⇒ 本批实际证明的是两件事：

1. **升级路径不再断**（db-init 退出 0、`current` = head、服务可用）——这才是 F-P7H-1 的缺陷本体；
2. **首次部署的 14 个迁移真跑**（§2 的判据 1 / 2，同一批实测）。

"9 个迁移真跑"只在**库结构落后于模型**时才有意义；1.6.0 的库并不落后。该偏差按
Non-goal 2「不把 SKIP 写成 PASS」的口径照实登记，**不**宣称为已满足。

---

## 4. F-P7H-1：**关闭**

| | P7-H 那次 | P7-Q 本次 |
|---|---|---|
| 首次部署怎么建表 | `db-init --create-tables`（`create_all`），**从不 stamp** | `db-init --run-migrations`（`alembic upgrade head`） |
| 客户升级时 | `alembic upgrade head` 第一个迁移就撞 `DuplicateTable` | 空库/已 stamp ⇒ 真跑；旧库 ⇒ 比对后 stamp，退出 0 |
| 谁决定版本号 | 人（演练现场手工拨） | 脚本按三种初始状态自己决定，且有机械比对兜底 |

配套落点（防回退）：

- `deploy/docker-compose.delivery.yml` 的 `db-init`：`--create-tables` → `--run-migrations`；
- `scripts/init_rls_roles.py`：新增 `--run-migrations`，**删掉「空库就自动 `create_all`」的隐式分支**；
  `--create-tables` 与 `--run-migrations` **互斥**（它们正是那两套并行机制）；
- `tests/test_migrations_baseline.py`：新增 3 条机械判据（空库迁移建表 == 元数据 / 二次 upgrade 不撞 /
  交付编排不许退回 `--create-tables`）；
- `docs/deployment-spec.md` §4.2 / §7.2 / §7.3 同步。

---

## 5. 其余两条遗留

### F-P7H-2｜Windows 宿主做交付演练必然踩 License 指纹不匹配

本次**照旧处理**（挂宿主 `MachineGuid` 写成的 `/etc/machine-id`）⇒ License `active`、
登录 `token_len=279`、`/documents` 与 `/audit` 均 200。**仍是非产品缺陷的固有约束，未变**。

### F-P7H-3｜回滚不回滚迁移 —— 本次**重新加压**，结论：旧代码读新结构无报错

加压条件比上次**更真实**：这次的库已 stamp 到 head、结构与 1.7.0 元数据**等价**
（上次库是 `create_all` 建的、迁移一个没跑）。回滚只改 tag 回 1.6.0 后：
`version` 回 `1.6.0`、前端字节数复原、**登录 + `/documents` + `/audit` 全部 200**，无报错。

⚠️ **仍未真正加压的部分**：那 9 个迁移**没有新增任何表 / 列**（见 §3.3），所以
"旧代码读被新迁移改过的结构"这件事**还是没被真正压到**。真正加压要等出现一个
**确实加表 / 加列**的迁移；该限制与上次同源，照实登记。

---

## 6. 清理

演练栈已 `down -v`（卷随之删除）；本机 `graphrag-drill` 恢复演练栈、`graphrag-pg`、
`graphrag-neo` **全程未动**；宿主 PG 上的冒烟库 `graphrag_p7q_smoke` 已 `DROP`。
临时文件留在系统临时目录，**未入库**。
