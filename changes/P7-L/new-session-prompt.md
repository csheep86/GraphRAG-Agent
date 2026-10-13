# 下一批开工提示词：P7-D（前端 Mock 静默回落 + 契约文案失真）

> 本文件是 **P7-L 批次目录下、写给下一批（P7-D）** 的开场提示词（2026-10-13 立）。
> 落地原因：对话上下文会丢，仓库不会。开工前**先读本文件**，再读 `changes/P7-D/proposal.md`。

---

## 1. 确认起点：从 `P7-D` 开始

**执行模式**：AI 主体（改代码 + 跑命令 + 回登），**不需要**第二自然人。
但见 §5：**两项决策尚未裁决**，动手前必须先在 §10-① 拿到用户选择。

**为什么是它——三条机械理由**：

1. **它是执行队列的下一个未开工项，且卡着别人**：`docs/release-readiness-audit-2026-10-13.md` §7 的序 2，
   依赖列写「无」；而序 5 的 **P7-G 的依赖是「P7-C/D/E 已完成」** ⇒ P7-D 不完成，P7-G 动不了。
2. **它背负着两笔已登记的债**：F-P7C-3（三处「Sprint 3 必须移除」过期文案）+ X-5（cost 的契约文案自称「恒返回 501」，
   而它在 P6-V 早已是真实现）。**契约现在在自陈假话**——这是"交付物说谎"那一类，不是打磨项。
3. **现在是唯一干净的窗口**：CI 四 job 全绿（`38381628647`）⇒ 动契约 + TS 双生成物时，
   任何红都能归因到本批，不会和别人的红混在一起。

---

## 2. 开工自检（**动手前先跑，结论只能来自脚本**）

```bash
cd backend && uv run python scripts/check_startup_readiness.py   # 必须 🟢 16 条 / 🟠 0 / 🟡 0
git fetch -q && git log --oneline origin/HEAD..HEAD               # 必须空（无未推送提交）
git status --short                                                # 必须干净
cd backend && uv run python scripts/export_openapi.py --check     # 必须零 diff
cd frontend && npm run gen:api && git -C .. diff --exit-code -- frontend/src/types/api.d.ts   # 必须无 diff
```

⚠️ **别信 `check_session_drift.py` 的 S1**（见 F-P7L-1，P7-L 新登记）：它**按目录 mtime 猜当前批次**。
本文件一提交，`changes/P7-L/` 的 mtime 就变成最新 ⇒ S1 会报 **P7-L 的 5 条边界**——
而正确的边界是 P7-D 的。请以 `changes/P7-D/proposal.md` §3 为准手动对照。

然后**重跑 §4 D2 的那条差分命令**——下面的 8 条未覆盖清单是我在 `1dfa179` 上实测的，
换一行代码就得重新数，不许直接抄表。

---

## 3. 边界纪律（**Non-goals 5 条**，原样照搬 `changes/P7-D/proposal.md` §3）

1. **不做新页面**（不为 `/cost/dashboard` 新增仪表盘 UI：要么接已有组件，要么登记缺口）。
2. **不改后端行为**（本批是契约文本 + 前端接线的对齐，不是功能新增）。
3. **不动 `set` / 本体 / 成本判据的阈值或算法**。
4. **不顺手重构 `client.ts`**（最小改动，够拦住即可）。
5. **不删除 `types/mock.d.ts`**（过渡产物，清理需单独批次评估，见审计 §4）。

---

## 4. 已查证坐标表（2026-10-13 在 `1dfa179` 上机械核实，**不要再查第二遍**）

| # | 坐标 | 事实 |
|---|---|---|
| **D1** | `frontend/src/api/client.ts:75-78` | `shouldMock` 原文仍在：`if (USE_MOCK) return true; return !CONTRACT_COVERED_PATTERNS.some(re => re.test(path))` ⇒ **契约外端点静默走 Mock**，机制丝毫未改。开关默认值在 `:25`，注入在 `frontend/Dockerfile:18` |
| **D2** | `contracts/openapi.yaml` paths vs `client.ts:32-68` 白名单 | **实测**：契约 **29** 条路径，白名单 **22** 个模式（其中 `/agent/query` **重复 2 次**：`:33` 与 `:60`）⇒ **未覆盖 8 条**（比 proposal §1 列的 4 组多）：`/auth/login`、`/cost/dashboard`、`/graph/versions/{version}/activate`、`/health`、`/license/status`、`/ontology/active`、`/ontology/cold-start`、`/ontology/confirm`。**`/health` 与 `/license/status` 是 proposal 没登记的两条** |
| **D3** | 这 8 条 UI 侧是否真被调用 | **实测没有被调用**：全仓 `frontend/src` 搜这些路径，命中只有生成物 `types/api.d.ts`、mock 数据 `api/mock/audit.ts:54,57`（纯字符串），以及 `app/ontology/page.tsx:30` 的一句注释。**没有 login / cost 页**（现有 14 个 `page.tsx` 里没有它们）⇒ 今天没有「屏幕显示假数据」的活症状，本批修的是**机制**不是现网事故——写日志时别把它说成"修复线上问题" |
| **D4** | "过期文案"的真实分布 | `contracts/openapi.yaml` **58 处**、生成物 `frontend/src/types/api.d.ts` **29 处**匹配「必须移除 / 占位骨架 / 恒返回 501」。后端真源侧只有 4 处会落进契约：`app/core/openapi.py:29`（Sprint 3 必须移除）、`:74`、`:99`（cost tag 恒 501）；`app/api/v1/routes/cost.py:55,62-63`（summary/description）；`app/api/deps.py:31-33`（X-Org-Id 描述）；`app/api/v1/responses.py:157-159`（501 响应描述）。**另有 3 处不会落进契约**（模块 docstring / 注释，改不改都不影响契约）：`app/schemas/cost.py:3`、`app/schemas/ontology.py:3`、`app/api/v1/router.py:59-60` ⇒ 别把工量算重 |
| **D5** | `/cost/dashboard` 到底是真是假 | **实现是真的**（P6-V）：`routes/cost.py:87-112` 真调 `app.services.cost_metrics.build_dashboard`。但 501 响应仍挂在 `:66`（`PLACEHOLDER_NOT_IMPLEMENTED`），且 docstring `:24-25` 保留了"501 = 基础设施故障"的语义 ⇒ **改文案 ≠ 删 501**：只许把"占位骨架，恒返回 501"改成实话，501 那条响应本身保留 |
| **D6** | 一致性检查能落在哪 | `frontend/package.json` **没有任何测试框架**（scripts 只有 dev/build/start/lint/typecheck/gen:api）⇒ proposal 出口判据 2 若做成前端单测，就得装 vitest/jest = **新增依赖 = 范围蔓延**。**先例存在**：`backend/tests/test_delivery_images.py`、`backend/scripts/build_delivery_images.py` 已在读 frontend 侧文件 |
| **D7** | CI 现有闸门 | `.github/workflows/ci.yml:306-355`（前端 job：lint / typecheck / gen:api 冒烟，**不**校验零 diff）；`:358-438`（契约 job：backend `export_openapi.py --check` + frontend `gen:api` 后 `git diff --exit-code frontend/src/types/api.d.ts`）。**契约 job 已经替本批把门了一半** |

---

## 5. 决策表（**只有第 1 条已裁决，其余不要替用户决定**）

| 决策 | 结论 |
|---|---|
| 边界 | Non-goals 5 条见 §3，**改一条都要先回来登记理由** |
| 「差异条数 = 0」那个一致性检查**落在哪** | 🟥 **未裁决** —— 推荐：`backend/tests/` 或 `backend/scripts/` 里用 Python 读 `contracts/openapi.yaml` + `frontend/src/api/client.ts`（仓库已有"后端读前端文件"的先例，D6），**不给 frontend 新增测试框架**。 ⇒ 走 §10-① 让用户点 |
| 8 条未覆盖端点**逐个怎么处置**（接真接口 / 显式登记豁免） | 🟥 **未裁决** —— proposal §2.1 要求逐个裁决；D3 已查实当前 UI 无调用点，所以**实测影响为 0**，但机制必须收口。 ⇒ 走 §10-① |
| 双生成物怎么交 | `contracts/openapi.yaml` 与 `frontend/src/types/api.d.ts` **禁止手改**，必须 `export_openapi.py` → `gen:api` 重新生成；CI 契约 job 已在拦 |
| 保持忽略 ≠ 批准 | `/health` 不用依赖注入这一事实，不等于它可以继续裸奔；本批要么登记豁免要么纳管，**不许因为"没出事"就留着不动** |

---

## 6. 已完成项（不要重做）

- **P6-T**：86/86 判分，`C1=0.142857` / 多跳 `0.833333`，F1/F2 未触发。
- **P7-C**：dev 兜底收口 + 护栏 **G-27**（G 计数 15 → 16）。
- **P7-L**：P6-T 后坐力 3 条断言收口（`409dc36`），CI 已绿。
- **P7-K**：修法 **③ 独立评测环境** 已裁决，**未开工**（本批不碰）。
- 继承性遗留：F-P7C-1（交付栈仍 `development`）、F-P7C-2（dev 兜底未删除）、**F-P7C-3 → 就是本批的活**、F-P7C-4（文档口径过期）、F-P7L-1（S1 猜错批次）。

---

## 7. 基线（**只能往好不能往坏**）

| 项 | 读数 |
|---|---|
| HEAD | **`1dfa179`**（✅ 已推送，`origin/HEAD` 同步；工作区干净） |
| CI | run **`38381628647`**（commit `1dfa179`）：前端 ✅ / 契约 ✅ / 后端 ✅ / 汇总 ✅；后端 Pytest **`1301 passed, 7 skipped, 0 failed`** |
| 本地 `uv run pytest -q` | `1262 passed / 46 skipped / 0 failed` |
| `check_startup_readiness.py` | 🟢 **16 条** ｜🟠 0 ｜🟡 0 |
| `ruff check` / `ruff format --check` | All checks passed / 298 files formatted |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 12 |
| `export_openapi.py --check` | 零 diff ｜契约 job `api.d.ts` 零 diff |

---

## 8. 验收判据（**每条都要能贴机器输出**）

1. **差异可枚举**：§4 D2 那条差分命令跑得出来，贴出「未覆盖 = N」；N 要么为 0，要么等于显式登记的豁免清单长度（**每条豁免要在 proposal/integration-log 里写明理由与 UI 表现**）。
2. **有守卫钉住**：新增的一致性检查真能红——临时往白名单删一条模式 ⇒ 它报错；加回来 ⇒ 绿（**反向验证，否则等于恒绿**）。
3. **双生成物一致**：`export_openapi.py --check` 零 diff，且 `git diff --exit-code frontend/src/types/api.d.ts` 干净。
4. **不退化**：本地 `pytest` ≥ 1262 passed 且 0 failed；`ruff check/format`、`check_seams.py` ERROR 0；push 后 **CI 四 job 全绿**（R-10）。

---

## 9. 提交推送纪律

- 一个批次一个 `proposal.md` + 一个 `integration-log.md`；**不得跨批次扩范围**。
- **本批同时跨 `frontend/` 与 `backend/`**：按角色隔离（改 frontend 时只动 frontend，改 backend 时只动 backend），
  但**两侧必须落在同一次提交**——契约 job 要求 `openapi.yaml` 与 `api.d.ts` 同时到位，分两次提交会让中间那个 commit 必红。
- 提交前本地三件套 + `pytest` + 前端 `lint` / `typecheck` / `gen:api`；**推送后以 CI 为最终裁决**（R-10）。
- 本批收尾：更新 `docs/release-readiness-audit-2026-10-13.md` §7 的 P7-D 行状态，**并顺带解锁提示**（P7-G 依赖 P7-C/D/E）。

---

## 10. 升级用户的四种情况

1. **要做判定动作却没有授权**：一致性检查落在哪（要不要给前端装测试框架）、8 条端点的逐条处置 ⇒
   **先让用户点 §5 的两条未裁决项再动手**，别自己挑。
2. **契约 paths 数量发生变化** ⇒ 停下说明是新增还是删除，**不得删路径**。
3. **发现更多契约文案失真** ⇒ 登记进 X-5 清单，逐条判定，**不批量改**。
4. **CI 红且复核两遍仍红** ⇒ 带 job 名 + 失败行 + 归因。

---

## 11. 不许外推

- **8 条未覆盖 ≠ 8 处线上假数据**（D3 已查实 UI 无调用点）；本批收的是**机制**，别写成"修复了现网事故"。
- **改文案 ≠ 改实现**：`/cost/dashboard` 的实现早就真的（P6-V），本批只是让契约说实话；
  C1 / 多跳 / 86 题判分**一个数字都不动**。
- **差异条数 = 0 ≠ 从此不再出现**：只是此刻对齐；后续新人加契约端点若不同步白名单，仍会复发——
  **除非**把判据做成 CI 门禁（那是「落在哪」那个决策要顺带定的）。
- 本批**不交付任何页面**；`/auth/login` 若无真登录页，登记为"已知 UI 缺口"，**不是**让它继续静静走 Mock。

---

## 12. 下一批指针

**P7-D 完成后**：按审计 §7 队列，剩 `P7-E`（B4+B6，序 3）、`P7-F`（A3 阈值回填，**用户先裁决阈值**，序 4）、
`P7-G`（A7 三条遗留，依赖 **P7-C/D/E** ⇒ 本批完成后离解锁只差 P7-E）、`P7-H`（A5 升级+回滚演练，
**需先 bump 1.7.0 + 第二见证者**）、`P7-I`（A4 L2 端到端）、`P7-J`（B5 私钥处置，**纯人工**）、
`P7-K`（A8，修法 ③ 已裁决）、`P8-Release`（A6 终审，需 0~10 全完成）。
⚠️ 开工前**重跑** §2 的自检与 §4 D2 的差分——文档会过期，脚本不会。
