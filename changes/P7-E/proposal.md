# P7-E · 前端 Base URL 运行时可配 + 根 README 部署章节（B4 + B6）

> **日期**：2026-10-13 ｜ **来源**：[`docs/release-readiness-audit-2026-10-13.md`](../../docs/release-readiness-audit-2026-10-13.md) §4 B4 / B6
> **一句话**：客户把系统部署到自己的域名/IP 时，**不用重建镜像**；并且根 README 里有一条能照着做完的安装路径。

## 1. 起点与坐标

| 项 | 坐标 |
|---|---|
| Base URL 硬编码 | `frontend/Dockerfile:20`（`NEXT_PUBLIC_API_BASE_URL` 默认 `http://127.0.0.1:8000`） |
| 内联时机（`NEXT_PUBLIC_*` 构建期内联） | `frontend/Dockerfile:7` |
| CORS 写死 | `deploy/docker-compose.delivery.yml:126`（`http://127.0.0.1:3000` / `localhost:3000`） |
| 客户侧部署文档（现状唯一） | `deploy/README.md:14-23`（起停）、`:95-127`（离线交付）、`:129-168`（已知坑） |
| 版本事实 | backend 只绑回环 `127.0.0.1`；postgres 不映射端口（`deploy/README.md:53`） |
| 根 README 现状 | `README.md:7-24`（只有开发约定 + `uv sync` / `npm install`，**无部署章节**） |

## 2. 做什么

1. 让 Base URL 在**容器启动时**可注入（nginx 式 runtime env 注入 / `serverRuntimeConfig` / entrypoint 生成 `env.js` 三选一，**先做选型取舍并登记理由**）。
2. CORS 改为可配置（由交付 compose 的环境变量提供），默认值保持现有回环口径不放松。
3. 根 `README.md` 增「部署」章节：**只给一条路径**（照 `deploy/README.md`），写清前置条件与验收命令（`install_acceptance.py` 入口），不复制粘贴大段。

## 3. Non-goals（**改一条都要先回来登记理由**）

1. **不做反向代理 / HTTPS 证书 / 域名方案**（那是客户现场运维）。
2. **不放宽端口绑定纪律**（后端继续只绑回环）。
3. **不改 `docker-compose.delivery.yml` 的 `image:` 无 `build:` 纪律**（G-19 在盯，碰了必红）。
4. **不重写 `deploy/README.md`**（只做最小增量；它是客户侧唯一文档，重写风险高于收益）。
5. **不做多实例 / 集群编排**。

## 4. 出口判据

1. **机械判据**：改 `API base` 后，`docker compose restart`（**不是 rebuild**）即可生效——有用例/脚本能贴这一个动作的前后读数。
2. 既有 liên quan 用例（`test_g19_*`、`test_g26_7_deploy_compose_uses_restricted_db_role` 等）不降。
3. README 的部署章节里每一条命令都**在本机跑过**（贴出关键节点输出），不许写没执行过的步骤。
4. 门禁三件套 + CI 四 job 全绿。

## 5. 升级用户的四种情况

1. 三方案都不可行、必须重建镜像 ⇒ 停下报告，这需要你裁决（商业影响：现场改域名要重建 = 不可接受）。
2. 需要引入新的前端依赖 ⇒ 报告后等你批准（本项目前端依赖应克制）。
3. 发现 CORS 改动会影响既有演示 ⇒ 保守回退默认值，登记为已知限制。
4. CI 红且复核两遍仍红 ⇒ 带 job 名 + 失败行 + 归因。
