# P7-G · 交付链路三条遗留缺陷（A7 / F-P6X-7 · F-P6X-8 · ghost_version）

> **日期**：2026-10-13 ｜ **来源**：[`docs/release-readiness-audit-2026-10-13.md`](../../docs/release-readiness-audit-2026-10-13.md) §3 A7
> **一句话**：让**图库恢复在现实部署形态下真的能成功**，并让安装验收带着身份跑得完。
> ⚠️ **本批是 P7-H（升级+回滚演练）的硬前置**——不修，恢复后 §6.2 必然 FAIL，演练没意义。

## 1. 起点与坐标（沿用 P6-X2 已登记的事实）

| 缺陷 | 坐标 | 事实 |
|---|---|---|
| **F-P6X-7** | `changes/P6-X2/integration-log.md:151-154` | `restore.py::restore_neo4j` 只在容器 running 时 exec，而 `neo4j-admin load` 要求**停服** + `--from-path` 传宿主路径 ⇒ 「宿主编排 → 容器执行」下图库恢复**不可能成功**（备份侧已解、恢复侧没有） |
| **F-P6X-8** | `changes/P6-X2/integration-log.md:155-158`、`backend/scripts/install_acceptance.py:836-864` | 无认证入口（无 `--token`）⇒ 目标环境第 6 项必 401 FAIL、第 7 项 SKIP。**是工具缺口，不是数据不足**（演练栈 `audit_log` 862 条 ≥7） |
| **`ghost_version`** | `changes/P6-X2/integration-log.md:159-161` | PG active `20261012T064951Z-inc-569555ad` 在图库**无镜像节点** ⇒ 恢复后 §6.2 FAIL，且历史上此类版本不允许作为启动版本 |

## 2. 做什么

1. **F-P6X-7**：给出图库恢复的可行形态（`docker run` 一次性离线 load / 停容器再 load / `--from-path` 挂载三种里选一种并登记取舍），并把"成功 = 图库侧真读到节点数"做成可核验。
2. **F-P6X-8**：给 `install_acceptance.py` 加认证入口（token 或登录换取），**不许靠跳过该项来变绿**。
3. **`ghost_version`**：要么写历史镜像迁移脚本，要么**显式登记为已知限制**并写清触发条件与客户可见后果——二者必有其一，不许留空。

## 3. Non-goals（**改一条都要先回来登记理由**）

1. **不做多云 / S3 异地备份**（存储抽象层已在，接实现属新批次）。
2. **不改 `install_acceptance.py` 十项判据的解释口径**（只加能力，不改判据）。
3. **不顺手把 SKIP 项改成 PASS**（SKIP 变 PASS 必须有真证据）。
4. **不动交付 compose 的纪律**（不许为了让演练跑通而引入 `build:` 或放松角色限制）。
5. **不做示例数据 / 演示库修补**。

## 4. 出口判据

1. 图库恢复有一条**端到端跑通过**的路径，且读数可贴（恢复后节点/关系数 ≠ 0）。
2. `install_acceptance.py` 带认证能跑完十项，第 6/7 项不再是 401 FAIL / SKIP。
3. `ghost_version` 三种结局之一成立且有登记坐标。
4. `pytest` 不降、三件套干净、CI 四 job 全绿。

## 5. 升级用户的四种情况

1. 图库恢复必须改交付 compose 的容器编排 ⇒ 停下报告（那是部署形态变更）。
2. `ghost_version` 修复需要新写入口 ⇒ 停下报告是否越权（可能撞 P6-V3 的"不新建全量重建入口"裁决）。
3. 认证的凭据来源需要新建凭据流 ⇒ 报告，等裁决。
4. CI 红且复核两遍仍红 ⇒ 带 job 名 + 失败行 + 归因。
