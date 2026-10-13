# P7-D · 集成日志（前端 Mock 静默回落收口 + 契约文案失真 X-5）

> 日期：2026-10-13 ｜ 起点 HEAD `d21a21d`（CI run **38383108649** 四 job 全绿）
> 用户裁决（开工前拿到的两条）：① 一致性检查落 `backend/tests`；② 8 条未覆盖端点**全部纳管**，豁免清单为空。

## 0. 结论（先给事实，全部有机器读数）

| 项 | 读数 |
|---|---|
| 契约 paths 数 | **29 → 29**（`Compare-Object` 逐行比对：PATHDIFF=0，未增未删） |
| 契约 paths − 白名单 pattern 的差集 | **0**（此前为 **8**） |
| 孤儿 pattern | **0**（白名单里没有对不上契约的模式） |
| 新增一致性用例 | `tests/test_frontend_contract_coverage.py` **10 passed** |
| 契约里「必须移除」出现次数 | **26 → 0**（同一句 `DEV_ORG_HEADER_DESCRIPTION` 在 26 个端点参数上重复展开，改 1 处源码全清） |
| 生成物 `api.d.ts` 残留的占位期自陈 | 仅剩 **1** 处，内容是「2026-10-13 更正」说明，不再是自陈 |
| 本地 pytest | 1262 passed → **1272 passed / 46 skipped / 0 failed** |
| `ruff check` / `ruff format --check` | All checks passed / **299 files** already formatted |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 12 |
| `check_startup_readiness.py` | 🟢 16 ｜🟠 0 ｜🟡 0（与开工前一致，未退化） |
| `export_openapi.py --check` | [OK] 零漂移 ｜`gen:api` **幂等**（暂存后再生成，`diff --exit-code` = 0） |

## 1. 开工自检（动手前跑的，结论只来自脚本）

```
check_startup_readiness.py  → 🟢 16 / 🟠 0 / 🟡 0
git log origin/HEAD..HEAD   → 空      git status --short → 干净
export_openapi.py --check   → [OK]    gen:api → api.d.ts 无 diff
```

⚠️ 本批**没有**采信 `check_session_drift.py` 的 S1：如 F-P7L-1 所记，它按目录 mtime 猜批次，
`changes/P7-L/` 因提交提示词而 mtime 最新 ⇒ S1 报的会是 P7-L 的 5 条边界。边界以 `proposal.md` §3 为准手工对照。

§4 的 D2 差分**重算过**，没有抄 `1dfa179` 上那张表（提示词 §2 明令）。
在 `d21a21d` 上实测得到同一结论：契约 29 / 白名单 22 / 未覆盖 8。

## 2. 改了什么（坐标为**改前**行号）

**前端（1 个文件）**

- `frontend/src/api/client.ts:68` 之后新增 **8 条** pattern：`auth/login`、`cost/dashboard`、
  `graph/versions/[^/]+/activate`、`health`、`license/status`、`ontology/active`、
  `ontology/cold-start`、`ontology/confirm`。
  注释里写死了两件事：**这是收口机制、不是修页面**（这 8 条当时 UI 侧无调用点），
  以及**清单从此不许手工维护**（漏/多一条都会让新测试变红）。

**后端·新增护栏（1 个新文件）**

- `backend/tests/test_frontend_contract_coverage.py`（10 用例）：用 PyYAML 读
  `contracts/openapi.yaml` 的 `paths`，正则抠出 `CONTRACT_COVERED_PATTERNS` 里的 TS 正则字面量，
  双向求差；另含解析下限、3 条合成反向用例、3 条「路径参数不展开」参数化用例。

**后端·契约文案真源（5 处，改完了必须重生成双生成物）**

| # | 坐标（改前） | 原文的话 | 改成的话 | 依据 |
|---|---|---|---|---|
| 1 | `app/core/openapi.py:29` | dev 兜底「**Sprint 3 必须移除**」 | 兜底**至今仍在**：开关默认 false、非生产才生效、生产不可达由护栏 **G-27** 钉住 | `config.py:151,429`；G-27 五条用例 |
| 2 | `app/core/openapi.py:83-84` | ontology `active`/`confirm`/`cold-start`「**仍是占位**」 | **已实装（P5-C）**，构成「建议 → 人确认 → 读 active」闭环 | commit `e34060c`；函数体核实 `suggest_ontology_types` / 写 `ontology_schemas` / `load_active_ontology` |
| 3 | `app/core/openapi.py:99` | cost tag「**当前为占位骨架，恒返回 501**」 | **已实装（P6-V）**；501 保留但语义是「基础设施故障」，非日常返回值 | commit `cea94e3`；`routes/cost.py` 真调 `build_dashboard` |
| 4 | `app/api/v1/routes/cost.py:55,62-63` | summary 带「占位骨架」；description 自陈恒 501 | summary 去占位字样；description 改为「已实装（P6-V），501 已不是日常返回值」 | 同上（D5：**改文案 ≠ 删 501**，501 那条响应保留） |
| 5 | `app/api/deps.py:31-33`、`app/api/v1/responses.py:157-159` | X-Org-Id「Sprint 3 接入 M5 登录后必须移除」；501 描述自陈占位 | 改双重条件 + G-27；501 描述改为「基础设施不可用」并注明**唯一挂载点**是已实装的 cost 端点 | `PLACEHOLDER_NOT_IMPLEMENTED` 全仓只有 `cost.py:66` 一个使用者 ⇒ 改它伤不到别人 |

配套：更新了 `cost.py` 模块/函数 docstring 与 `responses.py` 上方的登记注释，
否则「占位 record」改完了会留下新的过期说明。

## 3. 反向验证（**证明新断言仍能被打红**，否则等于恒绿）

1. **真实改动一次**：把 `client.ts` 里 `/^\/api\/v1\/license\/status$/` 整行删掉 ⇒
   `test_every_contract_path_is_covered` **FAIL**，报错直接点名
   `Left contains one more item: '/api/v1/license/status'`；加回来 ⇒ `10 passed`。
2. **测试内自带 3 条合成反向用例**：抽 `health` 的 pattern ⇒ 必须报 missing；
   塞一条凭空的契约 path ⇒ 必须报 missing；塞一条凭空的 pattern ⇒ 必须报 orphan。
3. **解析下限**：path < 20 / pattern < 20 直接 FAIL —— 挡的是「文件挪走了、正则没匹配上、测试依旧绿」（R-9）。

## 4. 出口判据逐条核销（proposal §4）

| 判据 | 结果 |
|---|---|
| 1. 不在白名单的端点不再静默返回 Mock | ✅ 差集 = 0，且由 pytest 钉住（§3 已证能红） |
| 2. 一致性检查可跑、差异条数 = 0（或显式豁免） | ✅ `10 passed`；豁免清单为空（用户裁决②） |
| 3. `export_openapi.py --check` 零 diff 且 `api.d.ts` 干净 | ✅ [OK]；生成物幂等 `diff --exit-code` = 0 |
| 4. pytest 不降、`check_seams.py` ERROR 0、CI 四 job 全绿 | ✅ 1272 passed / seams ERROR 0；**CI 读数见文末回填** |

## 5. 遗留登记（**不在本批处置**）

- **F-P7D-1｜注释层仍有 4 处占位期口径**：`app/api/v1/router.py:19,60`、`app/schemas/cost.py:3`、
  `app/schemas/ontology.py:3-4`。它们**不进契约**（已在重生成后确认生成物不含），
  按 proposal §5.3「不批量改」登记，不动。
- **F-P7D-2｜白名单里 `/agent/query` 写了两次**（`client.ts` 改前 `:33` 与 `:60`）：
  未清理 —— Non-goals 第 4 条是「不顺手重构 `client.ts`」。去重属另一批。
- **F-P7D-3｜`/auth/login` 与 `/cost/dashboard` 仍无 UI 消费方**：`frontend/src/app` 下 **14** 个
  `page.tsx` 里没有 login / cost 页 ⇒ 登记为**已知 UI 缺口**。
  本批纳管白名单只是取消静默 Mock 这条路，**不等于有了页面**。
- **F-P7D-4｜另两处带「Sprint 3」口径且会落进契约**：`deps.py:24-27`（bearer 描述）
  与 `:37`（X-Actor-Id 描述）。语气温和但仍过期；不在 X-5 原登记清单内，登记不改。

## 6. 不许外推

- **这 8 条是「机制缺口」，不是 8 处线上假数据**：UI 侧实测无调用点（全仓只命中生成物与
  `mock/audit.ts` 里的字符串）⇒ 别写成「修复了现网事故」。
- **改文案 ≠ 改实现**：`/cost/dashboard` 的实现早就真的（P6-V），
  本批只是让契约说实话。C1 / 多跳 / 86 题判分**一个数字都没动**。
- **差集 = 0 ≠ 从此不再复发**：只是此刻对齐。今后新增契约端点若不同步白名单，
  `test_frontend_contract_coverage.py` 会在 **CI 后端 job** 红——注意它归后端 job 跑，
  不归前端 job（这是「落在 backend/tests」那条裁决的代价）。
- **契约文案本身没有守卫**：新测试只盯 Mock 白名单，文案改完必须自己跑

  `export_openapi.py` + `npm run gen:api`（`cost.py` 函数 docstring 里已写入这句提醒）。

## 7. CI 读数回填（**R-10：以 CI 为最终裁决**）

| 项 | 读数 |
|---|---|
| CI run | **38386715267**（commit `0c2b0d9`） |
| 四个 job | 后端（ruff + pytest）✅ 2m58s ｜前端（lint + gen:api）✅ 38s ｜契约校验（前后端漂移门禁）✅ 34s ｜流水线汇总 ✅ 2s |
| CI 后端 pytest | **1311 passed / 7 skipped / 0 failed**（`Ruff 静态检查 All checks passed!`） |

⚠️ **本地 1272 / CI 1311 的量差是环境差异，不是提交差异**：本地没有 Neo4j / PG 服务
⇒ 依赖真服务的用例在本地 skip（46 skipped），在 CI 里真跑（7 skipped）。
判断退化的正确比法是 **同一环境下的前后值**：CI 上一条基线 `1301 passed` ⇒ 本批净增 10 条
（= 新测试文件的 10 个用例），**无其他用例被抹掉**。
