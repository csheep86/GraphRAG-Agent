# P7-G 集成日志 · 交付链路三条遗留

> **日期**：2026-10-13 ～ 2026-10-14 ｜ **提案**：[`proposal.md`](./proposal.md)
> **一句话**：让图库恢复在现实部署形态下真的能跑通，并让安装验收带着身份跑得完。
> ⚠️ 本批是 **P7-H（升级 + 回滚演练）的硬前置**。

---

## 1. 起点核验（**先确认缺口还在，不照提案抄**）

| 缺陷 | 提案给的坐标 | 本次机械复核结果 |
|---|---|---|
| **F-P6X-7** | `restore.py::restore_neo4j`（`:203`）只在容器 running 时 `docker exec` | ✅ **仍在**：`restore.py:215-228` 正是 `docker exec` + `--from-path={宿主路径}`。而 `neo4j-admin database load` **要求停服** ⇒ 两条约束不可能同时满足。备份侧早有对称实现（`backup.py:153::`_neo4j_dump_command``：容器停 ⇒ `docker run --rm --volumes-from`），**恢复侧没有** |
| **F-P6X-8** | `install_acceptance.py`（`:836-864`）无认证入口 | ✅ **仍在**：`_tenant_headers`（`:163`）只有 `X-Org-Id` / `X-Actor-Id`，无 `Authorization`；argparse 无 `--token` / `--username` |
| **`ghost_version`** | PG active `20261012T064951Z-inc-569555ad` 在图库无镜像 | ✅ **仍在**：本次只读复测 —— PG active = `20261012T064951Z-inc-569555ad`，`GraphService.fetch_kg_version_status(...)` = **`None`** |

---

## 2. ① F-P6X-8：验收脚本接上真认证

**凭据来源不新造**：走 P7-N 已实装的 `POST /api/v1/auth/login`。
理由：后端登录早就存在（P2-C 签发 HS256 JWT），缺的只是**调用它的人**；新建凭据流会多一处
"需要被审计 / 被吊销"的东西，而"目标环境首账号从哪来"本身是独立议题（F-P7N-2，已挂 P7-H 之前）。

改动（`backend/scripts/install_acceptance.py`）：

- `Context` 加 `token` 字段；新增 `_login()`；argparse 加 `--username` / `--password` / `--token`；
- `_tenant_headers`：**有令牌时只发 `Authorization`**，不再叠 `X-Org-Id` / `X-Actor-Id`
  —— 登录态下身份由令牌决定（`core/auth.py:103`），再叠一层 dev 头就有了两个来源；
- **登录失败当场退出码 2**（区别于"有 FAIL 项"的 1）：不许"登录失败还照跑"，
  否则第 6/7 项会被写成 401 FAIL / SKIP，读起来像目标环境没备好，真相却是凭据没给对。

### 真机读数（`APP_ENV=production` 后端 `:8011`）

⚠️ **为什么必须起 production 形态**：本机默认 `development`，dev 兜底会让无认证请求也过
⇒ 在那里验证等于自欺。

| 形态 | 结果 |
|---|---|
| 无认证 `GET /api/v1/audit` | **401** |
| dev 头 `X-Org-Id` | **401**（P7-C 的 G-27 生产不可达，坐实） |
| 真 token | **200** |
| `install_acceptance` **无凭据** | 第 6 项 `FAIL HTTP 401`（detail: `dev_fallback_enabled: False`），退出码 **1** |
| `install_acceptance` **带凭据** | 第 6 项 `PASS 100 条 / 100 个 trace 可聚合`，退出码 **0** |

完整十项（带凭据）：`2/3/6/9 PASS`；`1/4/5/7/8/10 SKIP`，每条 SKIP 都有真实原因
（缺 compose 健康探测 / 样例文档 / 提问 / **第二个租户** / 备份集 / `.env` 与日志），
没有一条是靠"改判据"变绿的。

**顺带发现（不在本批范围，登记）**：`APP_ENV=production` 下后端**拒绝默认 `AUTH_JWT_SECRET`**
（"内置默认值签名 ⇒ 任何人都能伪造"）⇒ 本机一直在 development 才从没触发，坐实了
P7-C 遗留 F-P7C-1 所说的"默认密钥守卫在客户现场同样不生效"的反面：**守卫本身是好的**，
生效与否取决于 `APP_ENV`。

---

## 3. ② F-P6X-7：图库恢复跑通

**改法**（`restore.py`）：新增 `_neo4j_load_command()`，与备份侧对称 ——

| 容器状态 | 行为 |
|---|---|
| 在跑 | **不发命令**，返回原因（停一个正在服务的图库是人的决定，脚本不代劳） |
| 已停 | 一次性容器：`--volumes-from <原容器>` 挂数据卷 **+ `-v <dump 目录>:/graphrag-restore-source:ro`** |

第二个挂载是必需的：`--from-path` 认的是**容器内**路径，宿主的备份目录在容器里本就不可达
（这正是旧代码第二个错）。

### 端到端实验（**一次性容器，不动在跑的 drill 栈 / dev 库**）

| 步骤 | 读数 |
|---|---|
| 起源容器 `p7g-neo-src`（`:7690`）并写探针数据 | `MATCH (n) RETURN count(n)` = **2** |
| 停源容器后 dump（`backup.py::collect_neo4j`，走"容器已停"分支） | `neo4j.dump` = **13673 字节**，落宿主 |
| 起全新空目标容器 `p7g-neo-dst` → 确认为空 → 停掉 | `nodes_before` = **0** |
| `restore_neo4j(container='p7g-neo-dst')` | **"已恢复图库 neo4j（一次性容器 · 数据卷 --volumes-from）"** |
| 起目标容器核对 | `nodes` = **2**（与源库一致）、`rels` = **0** |

`rels = 0` 不是丢了关系 —— 源库本来就只有 2 个孤立 `:Probe` 节点、没有关系。

**拒绝分支也验了**：拿**在跑的** drill 图库（`graphrag-drill-neo4j-1`）调 `restore_neo4j`
⇒ 返回 `SKIP 容器 … 正在运行 ⇒ 不执行 load …`，且**一个字节都没动**它（命令根本没发出）。

**踩到的两个错（守史实）**：

1. 第一版把 `--from-path` 写成 `.../neo4j.dump`（文件）⇒ `neo4j-admin` 报
   `is not an existing directory`。它要的是**目录**。
2. 修完发现隐藏耦合：备份侧 `NEO4J_DUMP_FILE = "neo4j.dump"` 是**硬编码**，
   而库名 `neo4j_database` **可配** ⇒ 两者一旦不一致，恢复必然失败。
   已在恢复侧加显式校验（报"文件名与目标库不匹配"），**根因未修** ⇒ 登记 F-P7G-2。

---

## 4. ③ ghost_version：按裁决 A 显式登记（**先核到底，差点报错**）

**差点搞错的地方（记下来）**：两条测试注释（`test_kg_incremental_rebuild.py:383`、
`test_kg_build_executor.py:283`）都写着"这条路径只写 PG、从不写图库 ⇒ §6.2 **恒判**
ghost_version"。照字面读会得出"ghost 是持续发生的系统性缺口 ⇒ 选 A 意味着 P7-H 必然 FAIL"。

**核到底的结果是相反的**：`sync_kg_version_mirror` 已经在**两处**完成路径都接上了
（`app/tasks/registry.py:840` 建图、`app/services/kg/incremental.py:314` 增量），
且各有测试钉着调用（`test_kg_build_executor.py:289`、`test_kg_incremental_rebuild.py:390`）
⇒ 那两条注释是**修复前**记下的缺口原形。

**⇒ 幽灵版本只会来自修复之前的历史版本**（本机 active `20261012T…` 正是 10-12 产生的），
新版本会自动同步镜像。**裁决 A 站得住**。

按 A 把触发条件 / 客户可见后果 / 补偿办法写进 `app/services/backup.py` 的 ghost message
（保留测试断言的 `"不许静默启动"` 子串）：

- **触发条件**：该版本产生于镜像同步接线之前；此后新版本自动同步 ⇒ 幽灵只来自历史版本；
- **客户可见后果**：本项 FAIL ⇒ `restore` 退出码 2，系统拒绝启动（fail-closed，不是警告）；
- **补偿办法**：重跑一次建图 / 增量，让 PG active 迁到带镜像的新版本；想就地保留该历史版本
  则须补一次镜像同步 —— ⚠️ `scripts/migrate_kg_version_org.py` **只补 `org_id`，补不了缺失的镜像节点**。

---

## 5. 遗留（**4 条，都是真的，不粉饰**）

| 编号 | 内容 |
|---|---|
| **F-P7G-1** | 第 7 项「目标环境跨 org」仍 **SKIP**：需要**第二个真实租户**（`--org-b`），而 `seed_dev_rbac.py` 只播默认 org。这与 F-P7N-2（首账号）是同一个根 ⇒ 挂到 P7-H 之前一起解 |
| **F-P7G-2** | 备份侧 `NEO4J_DUMP_FILE` 硬编码 `"neo4j.dump"` vs 可配 `neo4j_database`（见 §3）。已加显式校验使报错可读，**根因未修** |
| **F-P7G-3** | ⚠️ **A 只是登记，不消除幽灵版本**。本机 PG active 仍是无镜像的历史版本 ⇒ 目标环境若带着它，P7-H 的 §6.2 **必 FAIL**。P7-H 之前须按 §4 的补偿办法处理（重跑建图/增量把 active 迁走），否则演练没意义 |
| **F-P7G-4** | 恢复要求**容器已停**（`--volumes-from` 的必然要求），运行中的库不会自动恢复 —— 刻意不代劳停库。恢复流程里"停图库"这一步仍是人做的，须写进演练文档 |

---

## 6. 门禁

| 项 | 读数 |
|---|---|
| 全量 pytest | **1272 passed / 46 skipped / 0 failed**（未降，与 P7-N 收工时一致） |
| ruff | `All checks passed!` ／ `299 files already formatted` |
| 契约零漂移 | `[OK] contracts/openapi.yaml 与后端模型一致`（ghost 文案改动**未进契约**） |
| 接缝纪律 | `[OK] 接缝纪律检查通过` |
| 受影响用例 | `tests/test_backup_restore.py + test_kg_version_mirror_sync.py + test_install_acceptance.py` = **49 passed / 3 skipped** |

---

## 7. CI 读数（**R-10：以 CI 为最终裁决**）

本批分两次提交（① 认证、②③ 恢复 + 登记），各触发一次 run：

| 项 | ① `6abcbec` | ②③ `afca49c` |
|---|---|---|
| CI run | **38490476742** | **38494943608** |
| 结论 | ✅ success（2m21s） | ✅ success（2m22s） |
| 四个 job | 后端 ✅ ／前端 ✅ ／契约校验 ✅ ／汇总 ✅ | 后端 ✅ 2m12s ／前端 ✅ 31s ／契约校验 ✅ 51s ／汇总 ✅ 3s |
| CI 后端 pytest | — | **1311 passed / 7 skipped / 0 failed**（`Ruff: All checks passed!`） |

核销：本批**没新增任何用例** ⇒ CI 计数应与上批（P7-N 收工时的 `1311`）**持平**。
实测正好 1311 ⇒ 没有用例被本次 `restore.py` / `backup.py` 的改动悄悄抹掉。

> ⚠️ **① 那次的推送过程**：连试两次都是 `Recv failure: Connection was reset`
> （本机到 `github.com:443`），与 P7-M 那次同症状；第三次（十余分钟后）才成功。
> 下面这批读数是**推成功后 CI 实跑**的，不是本地结果外推 —— 若没推成功，这里就该留空。
