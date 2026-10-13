# P7-E · 集成日志（Base URL 运行时可配 + 根 README 部署章节 + bump 1.7.0）

> 日期：2026-10-13 ｜ 起点 HEAD `b9ee4b0`（CI run **38391401636** 四 job 全绿）
> 用户裁决（2026-10-13）：D9 选 **(b)** —— 顺带 bump 1.7.0，而不是"同 tag 装不同内容"。

## 0. 结论（先给事实，全部有机器读数）

| 项 | 读数 |
|---|---|
| 换地址是否需要重建镜像 | **不需要**（同镜像 `docker run` 双对照，见 §3） |
| R18 是否被放松 | **没有**：容器内 `grep NEXT_PUBLIC_USE_MOCK` ⇒ **退出码 1（零残留）** |
| CORS | 由写死 JSON 改为**可配**，**默认值一字未放松** |
| bump 的隐藏波及面 | `config.py` + 4 处 compose/variants + **`.env.example` 的 `APP_VERSION`** ⇒ 13 红 → **77 绿** |
| 契约 paths | **29 → 29**（`Compare-Object` PATHDIFF=0）；`info.version` 自动跟随为 **1.7.0** |
| 本地 pytest | **1272 passed / 46 skipped / 0 failed** |
| `ruff` / `check_seams.py` / readiness | 通过 ｜ ERROR 0 / WARN 0 / **OK 12** ｜ 🟢 **16** |
| 前端 `typecheck` / `lint` / `gen:api` | 0 错误 ｜ 通过 ｜ **幂等**（暂存后再生成 `diff --exit-code` = 0） |

## 1. 开工自检

```
HEAD b9ee4b0 ｜ UNPUSHED=0 ｜ DIRTY=0
check_startup_readiness.py  → 🟢 16 / 🟠 0 / 🟡 0
export_openapi.py --check   → [OK]        test_frontend_contract_coverage.py → 10 passed
```

⚠️ 没采信 `check_session_drift.py` 的 S1（F-P7L-1 同款病：按目录 mtime 猜批次；本目录因为
刚写进去的开场提示词而 mtime 最新 ⇒ S1 报的会是本批自己的边界，等于没查）。
边界仍以 `changes/P7-E/proposal.md` §3 为准手工对照。

## 2. 方案是怎么选出来的（**机械砍掉一条，不是三选一里随便挑**）

proposal §2.1 给了三个候选。开工复核砍掉了一条：

| 候选 | 判定 |
|---|---|
| `serverRuntimeConfig` | ❌ **不成立**：本仓是 **Next 16.3.5 + App Router**（`frontend/src/app`），该配置在 App Router 下不受支持（读取依然无从谈起） |
| 容器入口点生成 `env.js` + `<Script beforeInteractive>` | ✅ **采用**：零新增运行时依赖，入口点在镜像里 ⇒ 镜像自洽 |
| 容器内反向代理代注入 | 未采用：要新增 nginx 组件，触 proposal §5 第 2 条（前端依赖应克制） |

三层实现：**entrypoint（写文件）→ layout（早于 bundle 载入）→ client（优先读运行时）**。

**优先级与红线**（写在代码注释里了）：运行时 > 构建期 > 内置默认，但**只有 `NEXT_PUBLIC_API_BASE_URL`**
享受运行时一层；`NEXT_PUBLIC_USE_MOCK` / `APP_ENV` 刻意留在构建期（R18）。

## 3. 判据 1 的真机读数（**没跑 docker 就没有这些数字**）

本机 Docker `29.7.2`。构建 `graphrag-agent/frontend` 镜像后做双对照：

| 对照 | 给的 `NEXT_PUBLIC_API_BASE_URL` | 容器内 `/app/public/env.js` | `next start` 伺服的 `/env.js` |
|---|---|---|---|
| A | `http://127.0.0.1:8000` | `http://127.0.0.1:8000` | 同左 |
| B | `http://192.168.10.77:8000` | `http://192.168.10.77:8000` | 同左 |
| B 再 `docker restart` | 同上（未变） | 同上 | — |

⇒ **同一个镜像、只改环境变量，地址就变了。没有 `docker compose build`。**

**这里必须更正 proposal 判据 1 的措辞**：它写的是「`docker compose restart` 即可生效」，**实测不成立** ——
restart 复用容器原有配置，**不会应用新 env**；真正生效的是 `docker compose up -d`（recreate 容器，秒级，
**不是**重建镜像）。上表最后一行之所以值还在，是因为容器 env 本来就是那个值，
它只能证明"每次启动都会重新生成"，不能证明"改了 env 用 restart 就能生效"。

⇒ 客户正确操作写进了 `deploy/README.md` 与根 README：改 `.env` 后 **`up -d`**。

**R18 反向验证**：容器内 `grep -rl 'NEXT_PUBLIC_USE_MOCK' /app/.next/static` ⇒ **退出码 1**
⇒ 构建期已把它替换成字面量，运行时无从修改（假数据开关无法在现场被打开）。

### 验证的限制（**如实登记**）

1. **没有用真实的 delivery compose 端到端起栈**：3000 端口被正在运行的演练栈
   `graphrag-drill-frontend-1`（已 Up 10 小时）占用。为避免打断它，改用 `-p 3010/3011` 的
   `docker run` 做同镜像双对照 —— 证明力足够（同一镜像 + 只改 env），但**不是** compose 形态的端到端。
2. **`install_acceptance.py` 只在 `--help` 层面跑过**：它没有 dry-run 且会**写数据**（建租户、
   跑样例文档与问答）。本机唯一能跑的栈是上面那个演练栈 ⇒ 不拿它练手。
   ⇒ README 里那一步是非本机验证过的部分，**交付前必须在真实目标环境跑一次**。

## 4. 出口判据逐条核销（proposal §4）

| 判据 | 结果 |
|---|---|
| 1. 改 Base URL 后不用 rebuild | ✅ §3 双对照；但**判据措辞需更正**为 `up -d`（restart 不行），已写进两份 README |
| 2. `USE_MOCK` 没有跟着变成运行时可改 | ✅ bundle 零残留（grep 退出码 1） |
| 3. `test_g19_*`、`test_g26_7_*`、`test_frontend_contract_coverage.py` 不降 | ✅ 77 passed（含 g19 / delivery / install_acceptance / patch_contract 四类）+ 10 passed |
| 4. README 每条命令都跑过 | ⚠️ **部分**：`--help` 跑过；`cp .env.example` / `compose up` / 完整验收**未在本机跑**（见 §3 限制），已在 §5 登记 |
| 5. 门禁三件套 + CI 四 job 全绿 | ✅ 三件套全绿；CI 见 §7 |

## 5. 遗留登记（**不在本批处置**）

- **F-P7E-1｜bump 的隐藏真源**：`backend/.env.example` 的 `APP_VERSION` 会**覆盖** `config.py` 默认值。
  漏改 ⇒ 13 个测试红（`test_g19_own_image_tags_track_app_version` + 12 个 `test_delivery_images`）。
  **本机 `backend/.env`（不入库）也要跟着改**，否则会出现"本地红、CI 绿"的假象。
- **F-P7E-2｜判据措辞与实际不符**：见 §3，`restart` ≠ 应用新 env。已更正文档，未回头改 proposal 判据
  （proposal 是开工前的口径，改它就等于抹掉这条教训）⇒ 登记在此。
- **F-P7E-3｜`.env.development` 的 `APP_VERSION` 是 `1.1.0`**：与 `config.py` 默认（`1.7.0`）长期不一致，
  **不是本批造成的**，本批未动（改动可能影响依赖它的用例）。
- **F-P7D-2（仍未清）**：`client.ts` 里 `/agent/query` 写了两次。本批动过 `client.ts` 顶部，
  但那两处在白名单数组里 ⇒ 已能看到，仍按原约定留给下一次同文件改动（登记不遗忘）。

## 6. 不许外推

- **"换地址不用重建镜像" ≠ "前端已经能访问任意后端"**：CORS 默认值**一字未动**，
  地址改到别的域还须同步 `CORS_ALLOW_ORIGINS`，否则浏览器拦下来，症状是"请求发出去了但拿不到"。
- **`deploy/README.md` 依然是客户侧唯一路径**：根 README 那节只有入口和验收出口，
  刻意不复制步骤 —— 两份文档一旦分叉，现场一定按旧的做。
- **bump 不等于发布**：本版 CI 读数还没回填（§7），也没有打 tag。

## 7. CI 读数回填（**R-10：以 CI 为最终裁决**）

| 项 | 读数 |
|---|---|
| CI run | **待回填** |
| 四个 job | 待回填 |
| CI 后端 pytest | 待回填（基线 `1311 passed / 7 skipped / 0 failed`；本批无新增用例 ⇒ 期望持平） |
