# P7-M · 过期文案收尾（注释层 + 会落契约的描述）

> **日期**：2026-10-13 ｜ **来源**：`changes/P7-D/integration-log.md` §5 遗留 F-P7D-1 / F-P7D-4
> **一句话**：把 P7-D 收 X-5 时**刻意留着没动**的那些过期话，按同样标准一次收干净——
> 区别只在于它们是否落进 `contracts/openapi.yaml`。
> **用户裁决**（2026-10-13）：同意单开本批、独立于登录批次先收。

## 1. 起点与坐标（**每行都有实装配对的 commit**）

| # | 坐标 | 原文的话 | 事实 | 依据 |
|---|---|---|---|---|
| **M1** | `backend/app/api/v1/router.py:18-21` | 「M6 契约先行批次，**7 个端点全部 501 占位**，实现归 P5-M6 / Sprint 12」 | **7 个全部已实装** | `cold-start`/`confirm`/`active` ← `e34060c`（P5-C）；`merge`/`split`/`rename` ← `7124a46`（P5-G）；`candidates` ← `8142ecc`（P5-I）；`cost/dashboard` ← `cea94e3`（P6-V） |
| **M2** | `backend/app/api/v1/router.py:23` | 「其余端点草案（`/auth/login`、`/internal/*` 等）留在草案态」 | `/auth/login` **已实装并已注册**（同文件 `:68`） | `backend/app/api/v1/routes/auth.py:53`；注册行 `router.py:68` |
| **M3** | `backend/app/api/v1/router.py:59-60` | 「6 个 ontology 端点 + `GET /cost/dashboard`，**全部 501 占位骨架**」 | 同 M1，无一占位 | 同 M1 |
| **M4** | `backend/app/schemas/cost.py:3-4` | 「本批只落契约与 501 占位骨架…计算实现归 P5-M6 批次」 | 已实装（P6-V） | `cea94e3` |
| **M5** | `backend/app/schemas/ontology.py:3-4` | 同 M4 句式 | 已实装（P5-C / P5-G / P5-I） | 同 M1 三条 commit |
| **M6** | `backend/app/api/deps.py:24-27`（**会落契约**） | 「Sprint 1 支持 `Bearer dev.<org>.<actor>`；**Sprint 3 起**由 M5 `POST /auth/login` 签发的 JWT 取代」 | `/auth/login` 现在**真能签发 JWT**（P2-C），但 dev token 路径**仍在**（受 `dev_identity_enabled` 开关约束） | `routes/auth.py:68` `issue_access_token`；`config.py:429`；G-27 |
| **M7** | `backend/app/api/deps.py:37`（**会落契约**） | 「缺省取 `DEFAULT_ACTOR_ID`；**Sprint 3 起由认证态提供**」 | 认证态**至今未提供** actor（`X-Actor-Id` 仍是唯一注入途径） | `deps.py:36-38`；全仓无别处写 actor |

⚠️ **M1~M5 不落契约**（模块/docstring 层），**M6~M7 落契约** ⇒ 只有改 M6/M7 才需要重生成双生成物。
但本批一次性全改，生成物仍然要重跑一次。

## 2. 做什么

1. 按上表逐条把话改成实话，**每句写明依据 commit 或真源行**（不许出现没有出处的批次名）。
2. 「本批」这类指代保持不变指的是历史批次（P0-m6-finalization），但要补一句当前状态，
   免得读者以为仍是占位。
3. `/auth/login` 相关的口径统一为**现在时**：它可用、已注册、且 dev token 仍并存（不删除）。

## 3. Non-goals（**改一条都要先回来登记理由**）

1. **不改任何代码逻辑 / 行为**：本批只动注释、docstring、路由装饰器的描述文本。
2. **不改 `summary` / responses 结构 / paths**（P7-D 已动过的 cost summary 不在本批二次修改）。
3. **不顺手去重排、不重构、不顺手修别的过期话**（新发现的一律登记，不批量改）。
4. **不动 `frontend/`**：本批与前端无关（`client.ts` 那两条遗留 F-P7D-2 绑到 P7-E）。
5. **不给 `/auth/login` 加 UI**（那是 P7-N 登录批次的活）。

## 4. 出口判据

1. 上表 7 条全部改完，且每条能在 diff 里指到依据。
2. `uv run python scripts/export_openapi.py --check` 零 diff；
   `npm run gen:api` 后 `git diff --exit-code frontend/src/types/api.d.ts` 干净（幂等）。
3. 本地 `pytest` ≥ 1272 passed 且 0 failed；`ruff check` / `ruff format --check` 通过；
   `check_seams.py` ERROR 0；`check_startup_readiness.py` 保持 🟢 16。
4. 契约里不再出现「**Sprint 3 起由 … 提供 / 取代**」这类**未兑现承诺**口径（机械计数 = 0）。
   ⚠️ `AgentQueryResponse` 的「Sprint 4 阶段 10.0 批次 A 扩展（Sprint 3 缺口 1 偿还）」
   是**已发生的历史沿革陈述**，不是承诺 ⇒ **保留不改**（本批逐条判定的结论之一，
   判据若写成「出现 Sprint 3 就算」会误伤它）。
5. push 后 **CI 四 job 全绿**（R-10）。

## 5. 升级用户的四种情况

1. 改某条时发现**事实与本文登记的相反**（例如某端点其实还有 501 路径）⇒ 停下报告，不改。
2. 需要改 `summary` 才能说真话 ⇒ 停下（那是 P7-D 的地界，要登记后再动）。
3. 新发现别的过期话 ⇒ 登记进本文 §6，**不批量改**。
4. CI 红且复核两遍仍红 ⇒ 带 job 名 + 失败行 + 归因。
