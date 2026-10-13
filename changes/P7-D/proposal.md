# P7-D · 前端 Mock 静默回落 + 契约文案失真（B2 + B3 / X-5）

> **日期**：2026-10-13 ｜ **来源**：[`docs/release-readiness-audit-2026-10-13.md`](../../docs/release-readiness-audit-2026-10-13.md) §4 B2 / B3
> **一句话**：关掉 Mock 之后，页面要么拿到真数据，**要么报错**——不许第三条路「静默拿到假数据」；并把契约里还在说"恒返回 501"的文案改成实话。

## 1. 起点与坐标

| 项 | 坐标 |
|---|---|
| 静默回落点 | `frontend/src/api/client.ts:75-78`（`USE_MOCK=false` 时契约外端点仍返回 Mock）；机制说明 `:62-63` |
| 未登记的契约端点 | `/cost/dashboard`、`/auth/login`、`/ontology/{active,confirm,cold-start}`、`/graph/versions/{version}/activate` |
| Mock 白名单 | `frontend/src/api/client.ts:32-68` `CONTRACT_COVERED_PATTERNS` |
| Mock 默认值 | `frontend/src/api/client.ts:25`（默认 `true`）；`frontend/Dockerfile:18` 以 build-arg 注入 `false` |
| 契约文案失真（X-5） | `backend/app/core/openapi.py:83-84,99`、`backend/app/api/v1/routes/cost.py:55,62,76,83`、`routes/cost.py:7-14`（自陈属下一批） |
| 占位已清空的反证 | `backend/tests/test_ontology_placeholder_endpoints.py:47-56`（`PLACEHOLDERS` 列表已空） |
| 历史教训（勿重现） | `docs/dev-doc-status.md:100`「契约外端点 ⇒ `shouldMock()` 恒 true ⇒ 关了 Mock 屏幕还是假数据」 |

## 2. 做什么

1. **逐端点判定**：上表 4 组端点，每个给出「接真接口 / 显式登记豁免并给出 UI 表现」的裁决，**不许留默认静默**。
2. 把"契约新增端点必须同步 `CONTRACT_COVERED_PATTERNS`"升级为**机械检查**（契约路径集合 vs 白名单集合的差异可由脚本枚举）。
3. 改 `openapi.py` 的 cost / ontology tag 文案 + `cost.py` 的 summary/description，**同步** `contracts/openapi.yaml` + `npm run gen:api` 两个生成物一起交。
4. 明确 `/auth/login` 是否有真登录页；若无，登记为"已知 UI 缺口"而**不是**让它静静走 Mock。

## 3. Non-goals（**改一条都要先回来登记理由**）

1. **不做新页面**（不为 `/cost/dashboard` 新增仪表盘 UI；它要么接已有组件，要么登记缺口）。
2. **不改后端行为**（本批是契约文本 + 前端接线的对齐，不是功能新增）。
3. **不动 `set`/本体/成本判据的阈值或算法**。
4. **不顺手重构 `client.ts`**（最小改动，够拦住即可）。
5. **不删除 `types/mock.d.ts`**（它是过渡产物，清理需单独批次评估，见审计文档 §4）。

## 4. 出口判据

1. `USE_MOCK=false` 下，**不在白名单的端点不再静默返回 Mock**——要么真请求，要么显式错误/空态 UI，并有用例钉住。
2. 新增的 patterns 一致性检查可跑、贴出"差异条数 = 0"（或登记的显式豁免清单）。
3. `export_openapi.py --check` 零 diff 且 `git diff --exit-code frontend/src/types/api.d.ts` 干净。
4. `pytest` 不降、`check_seams.py` ERROR 0、CI 四 job 全绿。

## 5. 升级用户的四种情况

1. 某端点"接真接口"需要新增 UI 组件 ⇒ 停下报告，那是新功能不是修缺陷。
2. 契约 paths 数量会变化 ⇒ 说明是新增还是删除，**不得删路径**。
3. 发现更多契约文案失真 ⇒ 登记进 X-5 清单，逐条判定，不批量改。
4. CI 红且复核两遍仍红 ⇒ 带 job 名 + 失败行 + 归因。
