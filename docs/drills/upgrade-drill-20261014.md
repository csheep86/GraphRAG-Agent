# 升级 + 回滚演练留证（P7-H / A5）

> ⚠️ **内部演练，非客户现场验收**。
> 本文件记录的是**在开发者本机（Windows + Docker Desktop）用交付镜像**完成的一次升级与回滚，
> 目的是验证升级/回滚这条**路径本身**是否走得通；它**不代表**任何客户环境已验收、
> 也不代表客户现场会得到同样读数（尤其 License 指纹一节，见 §5 F-P7H-2）。

| 项 | 内容 |
|---|---|
| 日期 | 2026-10-14 |
| 批次 | P7-H（[`changes/P7-H/proposal.md`](../../changes/P7-H/proposal.md)） |
| 环境性质 | **独立**：独立 compose 项目 / 独立数据卷 / 独立端口 / 独立 `.env`，**由固定 tag 镜像起**（无 `build:`） |
| 执行者 | AI（本机执行，读数见下） |
| 见证者 | **（待签真名——本栏不得由执行者代填）** |

---

## 1. 环境

| 项 | 值 |
|---|---|
| compose 项目名 | `graphrag-upgrade-drill`（卷名随之隔离，未触碰既有的 `graphrag-drill` 恢复演练栈与 dev 库） |
| 基础编排 | `deploy/docker-compose.delivery.yml` 的**副本**（仅把四组端口改到 8001/3001/7476/7689，避开在跑的栈） |
| 镜像 | 旧 = `graphrag-agent/{backend,frontend}:1.6.0`；新 = `1.7.0`（本批用 `build_delivery_images.py` 现构建） |
| License | 本机 `deploy/license/app.lic`，只读挂进容器 |
| 备份 | 升级前 `pg_dump` → **52,800 B**（§7.2 第 1 步「不备份不升级」） |

> 演练用的 `.env` / override / 备份都放在**系统临时目录**，**未入库**（`.env` 含口令，按纪律禁止入库）。

---

## 2. 读数（**判据要的"前后版本读数"**）

| 阶段 | 镜像 tag | `GET /api/v1/health` 的 `version` | 前端 SSR | 受保护端点 |
|---|---|---|---|---|
| **升级前** | `1.6.0` | **1.6.0** | 200 / 45313 B | 401（未认证） |
| **升级后** | `1.7.0` | **1.7.0** ✅ | 200 / **10483 B** | 登录 `token_len=279` ⇒ `/documents` **200**、`/audit` **200** |
| **回滚后** | `1.6.0` | **1.6.0** ✅ | 200 / 45313 B（复原） | 登录 279 ⇒ `/documents` **200**、`/audit` **200** |

**升级**：停服 → 切 1.7.0 tag → 起服务 → `version` 由 `1.6.0` 变 `1.7.0`。
**回滚**：仅把 tag 改回 `1.6.0` 并 `up -d`（§7.3「回滚优先改 tag」）⇒ `version` 回到 `1.6.0`，功能可用。

两个交叉验证（不在计划内，但同样有说服力）：

- 前端字节数 **45313 → 10483 → 45313**：降下去是因为 1.7.0 带了 P7-N 的**登录门**（未登录只渲染登录卡片），回滚后复原 ⇒ 登录门在**交付镜像**里真生效；
- 升级后 `scripts/provision_admin.py` 可在容器内直跑并开户成功（1.6.0 镜像里没有它）⇒ 实证 **P7-P 的开户命令随交付镜像一起交付**，且交点在镜像内的 `scripts/`（`Dockerfile` 的 `COPY backend/scripts`）。

---

## 3. §6.2 版本一致性

```
ACTIVE_VERSION = None
code = no_active_version   ok = True
MSG  = PG 中无 active kg_version ⇒ 无版本可错位；本条**未做任何一致性验证**
       （新环境属正常，但不等于已验证）
```

⚠️ **这条不算"§6.2 已过"**。演练环境是全新库，压根没有 `kg_version` 可比对，
判定函数自己就把话说清楚了（"未做任何一致性验证"）。要真正验证 §6.2，
得用**带 active 版本的备份集**恢复后再判（P6-X2 那次恢复演练的环境具备该条件）。
按 Non-goal 2「不把 SKIP 写成 PASS」，这里照实记为**未构成有效验证**。

---

## 4. 遗留（**不在演练现场修**，只登记坐标）

### F-P7H-1｜升级时数据库迁移跑不了（**阻断客户升级**）

```
$ alembic upgrade head
Running upgrade  -> 00f44b912817, baseline sprint1-9.5 tables
DuplicateTable: relation "affiliation_suspicions" already exists
```

**根因比表面深一层**：首次部署由 `db-init --create-tables`（SQLAlchemy `create_all`）
按模型建表；而后补的 Alembic 迁移又要创建**同样的**表/列 ⇒
把 `alembic_version` 拨到哪一段都会撞 `DuplicateTable`
（实测：stamp 基线 ⇒ 撞 `document_date` 列；stamp 到 v1.6.0 的 head `b3e5a1c70d42` ⇒ 撞 `users` 表）。

⇒ 也就是说：**`create_all` 与 Alembic 是两套并行的建表机制，混用时升级路径必断**。
v1.6.0 → 1.7.0 之间新增 **9 个迁移 / 761 行**，客户按 §7.2 第 4 步执行时会在第一个迁移就失败，
而 §7.3 检查清单里并没有任何一条能提前发现它。

**本次的处置（仅为让演练继续，不是修复）**：手工把 `alembic_version` 置为 head
（`a1f7c2b93d04`），承认库结构已由 `create_all` 建立 ⇒ **9 个迁移一个都没真正执行**。
后果：库结构来自模型而非迁移，与迁移历史**不再有任何对应关系**。

**为什么本次没修**：Non-goal 1（不在演练现场顺手修产品缺陷）。建议另立批次，
方向是明确"首次部署的唯一建表途径"（要么一律走 `alembic upgrade head`，
要么 `create_tables` 之后强制 `alembic stamp head` 并把这条写进 §4.2 安装步骤）。

### F-P7H-2｜Windows 宿主做交付演练必然踩 License 指纹不匹配

| | machine-id | 指纹 |
|---|---|---|
| 宿主 | `5f1bd63f-…` | `0d531a1f…` |
| 容器（默认） | `208c9ebe…` | `4d0e04e0…` |

Windows 没有 `/etc/machine-id` ⇒ Docker Desktop 建出**空目录**（compose 注释本就写明这种情况会回落 MAC）
⇒ 容器用自己的 machine-id ⇒ `LICENSE_FINGERPRINT_MISMATCH`，业务端点 **403**。

**本次处置**：给容器挂一份写着宿主 machine-id 的文件，模拟 **Linux 客户现场的真实形态**
（客户机器有 `/etc/machine-id`，指纹锚定宿主）⇒ License 转 `active`、业务面恢复。
⇒ 这不是产品缺陷，但它是**在 Windows 上做交付演练的固有约束**，后续演练需照此处理或改用 Linux 宿主。

### F-P7H-3｜回滚不回滚迁移，本次未暴露冲突

按 §7.3 明写"迁移无 down 脚本时不承诺回滚迁移"，本次回滚只改 tag。
实测 **1.6.0 旧代码读被新迁移影响过的库没有报错**（登录 / 列表 / 审计均 200）。
⚠️ 但本次的库结构其实是 `create_all` 建的（见 F-P7H-1），
所以"回滚后旧代码能否读新结构"这件事**没有被真正加压** —— 结论只在本次条件下成立。

---

## 5. 清理

演练环境已 `down -v`（卷随之删除）；本机在跑的 `graphrag-drill` 恢复演练栈与 dev 库**全程未动**。
临时文件（`.env` / override / 备份 SQL / machine-id）留在系统临时目录，未入库。
