# Integration Log —— Sprint 8.3 批次 D（A16：settings 页「演示环境」标注）

> **执行日期**：2026-09-24 ｜ **分支**：`feature/sprint-8` ｜ **花费**：**¥0**（纯前端静态页，零接口调用，不触 LLM / 不触解析）
> **原则**：勾选 ≠ 通过——下面每一条都是命令输出，不是推断。

## 1. 交付（3 个前端文件，零后端 / 零契约改动）

| 文件 | 改动 | 判据来源 |
|---|---|---|
| `frontend/src/components/common/placeholder-page.tsx` | 新增 `badge`（标题右侧标签位）与 `notice`（占位卡上方说明卡）两个插槽 | A16（proposal.md:73） |
| `frontend/src/app/settings/page.tsx` | 标题右侧「演示环境」`Badge`（`variant="muted"` + `Info` 图标）+ `DemoEnvironmentNotice` 说明卡（四条可核事实） | 同上 |
| `frontend/src/lib/nav.ts` | `/audit` 去掉 `placeholder: true`——批次 A 后已是真实页，留着是**假声明** | 与 A16「诚实可核」同源 |

**说明卡四条事实**（每条都能回到契约 / 目录复核，不写推测内容）：

1. 契约 `openapi.yaml` **无** `/settings*` 路径 ⇒ 本页**无配置项、也无 Mock 数据**（按「功能预留原则」只留导航入口，不伪造配置）；
2. 演示语料 = `docs/annualreport/` 招商局系 2025 年度报告 **10 份 PDF**（已列目录核实）；
3. 文档管理 / 知识图谱 / 知识问答 / 疑点清单 / 权限审计走真实接口（`NEXT_PUBLIC_USE_MOCK=false`），**知识问答的多轮会话列表仍为 Mock —— 如实写明为已知豁免**（plan §5.3 同源口径）；
4. 身份与租户走开发态请求头 `X-Org-Id` / `X-Actor-Id`（`LocalAuthProvider`），**非生产认证**；限流 60 次 / 分钟 / 接口，超限 429 `RATE_LIMITED`（批次 B 产物）。

**为什么不是隐藏路由**（A16 原文理由）：隐藏后验收者分不清「没有这个页面」还是「页面有假数据」，plan §7.2「演示剧本 6 步零假数据」硬门槛将**失去可核性**；标注既诚实又可核。

## 2. 门禁（命令 → 真实输出）

| 命令 | 输出 |
|---|---|
| `npx tsc --noEmit`（frontend） | 无输出，**exit 0** |
| `npm run lint`（ESLint） | `eslint` 无告警，**exit 0** |
| `npm run gen:api` | `openapi-typescript 7.13.0` → `src/types/api.d.ts`（68.1ms） |
| `git --no-pager diff --stat frontend/src/types/api.d.ts contracts/openapi.yaml` | **无输出** ⇒ 契约与 TS 类型**零漂移** |
| `uv run pytest -q`（backend） | **387 passed, 1 warning in 5.92s**（与批次 B 后基线一致，本批次未动后端） |
| `uv run python scripts/check_seams.py` | **ERROR 0 / WARN 2 / OK 8**（2 条 WARN = 未到期接缝 6，与基线一致） |
| `uv run python scripts/export_openapi.py --check` | `[OK] contracts/openapi.yaml 与代码模型一致` |

## 3. 真机点验（两条路径都跑，¥0）

**路径 ①：关 Mock**（`cmd /c set NEXT_PUBLIC_USE_MOCK=false && npm run dev`）

```text
GET http://localhost:3000/settings  → HTTP 200（29,322 B）
HTML 逐字核对（PowerShell .Contains）：
  演示环境          -> True
  功能预留          -> True
  系统设置          -> True
  docs/annualreport -> True
  LocalAuthProvider -> True
  RATE_LIMITED      -> True
  多轮会话          -> True
  href="/settings"  -> True   ← 侧栏入口仍在，未隐藏路由（A16 判据）
  <title> = GraphRAG Studio · 企业知识库工作台
```

**路径 ②：默认 Mock 态**（`npm run dev`，不带环境变量）

```text
GET /settings → HTTP 200；演示环境 -> True；功能预留 -> True
（本页是服务端渲染的静态页、零接口调用 ⇒ 与 Mock 开关无关，两条路径同结果）
```

两个 dev 进程点验后均已 `Stop-Process` 关闭；抓取的 HTML / dev 日志为过程产物，不入库（已删）。

## 4. 未擅自处置（如实登记）

- **批次 D 另两项未做**：种子数据集固化、演示彩排脚本（plan §7.1 批次 D 共三项，本轮只做 settings 页处置），**待用户裁决**；
- **未动**：`contracts/openapi.yaml`、后端任何文件、接缝、`app_version`（仍 1.3.0）；
- **观察项未动**：受控问题集 11 问与现语料不同源（A15）、`graph/overview` 的 `entity_count=0`。
