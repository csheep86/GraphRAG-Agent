# P7-M · 集成日志（过期文案收尾：注释层 + 会落契约的描述）

> 日期：2026-10-13 ｜ 起点 HEAD `78d475e`（CI run **38387764762** 全绿）
> 来源：`changes/P7-D/integration-log.md` §5 的遗留 **F-P7D-1**（注释层 4 处）与 **F-P7D-4**（落契约 2 处）。
> 用户裁决（2026-10-13）：同意单开本批，独立于登录批次先收。

## 0. 结论（先给事实，全部有机器读数）

| 项 | 读数 |
|---|---|
| 契约 paths | **29 → 29**（`Compare-Object`：PATHDIFF=0） |
| 契约里「**必须移除**」 | 0（P7-D 已清零，本批未回升） |
| 契约里「**Sprint 3 起由 … 提供/取代**」这类未兑现承诺 | **2 → 0** |
| 契约里剩余「Sprint 3」 | **1** 处，`AgentQueryResponse` 的历史沿革陈述，**逐条判定后保留** |
| 本地 pytest | **1272 passed / 46 skipped / 0 failed**（与 P7-D 收工同值，未降） |
| `ruff check` / `ruff format --check` | All checks passed / 299 files |
| `check_seams.py` | ERROR 0 / WARN 0 / OK 12 |
| `check_startup_readiness.py` | 🟢 16 ｜🟠 0 ｜🟡 0 |
| `export_openapi.py --check` | [OK]；`gen:api` **幂等**（暂存后再生成 `diff --exit-code` = 0） |

## 1. 开工自检

```
check_startup_readiness.py  → 🟢 16 / 🟠 0 / 🟡 0
git log origin/HEAD..HEAD   → 空      git status --short → 干净
export_openapi.py --check   → [OK]    gen:api → api.d.ts 无 diff
pytest tests/test_frontend_contract_coverage.py -q → 10 passed
```

## 2. 改了什么（M1~M7，坐标为**改前**行号）

| # | 坐标 | 改成了什么 | 依据（每条都能指到一个 commit） |
|---|---|---|---|
| M1 | `app/api/v1/router.py:18-21` | 「7 个端点全部占位」→ 逐条列出**已实装**及批次 | P5-C `e34060c`；P5-G `7124a46`；P5-I `8142ecc`；P6-V `cea94e3` |
| M2 | `app/api/v1/router.py:23` | `/auth/login` 不再是草案 | `routes/auth.py:53` + 注册行 `router.py:68` |
| M3 | `app/api/v1/router.py:59-60` | 删除「全部 501 占位骨架」，改为「注册当时的状态」并指向 M1 | 同上 |
| M4 | `app/schemas/cost.py:3-4` | 保留「本批只落契约」（陈述当时），补一句 P6-V 已实装 | `cea94e3` |
| M5 | `app/schemas/ontology.py:3-4` | 同上句式，补三条批次 commit | 同 M1 的 P5-C/G/I |
| M6 | `app/api/deps.py:24-27`（**落契约**） | 「Sprint 3 起由 JWT 取代」→ **两条并存**，并写明 dev token 受 G-27 约束 | `core/auth.py:49-103`；`config.py:429` |
| M7 | `app/api/deps.py:37`（**落契约**） | 「Sprint 3 起由认证态提供」→ 写明 JWT 路径下 actor 来自令牌 `sub`，本头只作用于 dev header | `core/auth.py:103` |

## 3. 一条自我纠偏（本批最值钱的部分）

**我第一版把 M7 写成了「认证态至今未提供 actor」——这是我自己制造的失真**，靠下面这条核实抓了回来：

```
app/core/auth.py:103  return Identity(org_id=claims.org_id, actor_id=claims.user_id, source="jwt")
```

⇒ JWT 路径**早就提供了 actor**（取 `claims.user_id`）。原文那句「Sprint 3 起由认证态提供」
其实**已经兑现了**，错的只是那个永远到期的时间戳。改成如实描述后，反而比原文更长但更准。

教训（登记给后面所有"改文案"的批次）：**改文案的人最容易制造新失真** ——
因为改的人已经在"我要修正它"的心态里，比写原文的人更容易跳过核实。
本批每条结论都要求**能指到一个 commit 或一行代码**，就是为了逼这一步。

第二处同类风险（及时发现）：改完 M6 后我曾想在文案里原样引用旧句做对照，
那样会让机械计数误报 ⇒ **判据改成只数「未兑现承诺」，不数历史沿革**。

## 4. 出口判据逐条核销（proposal §4）

| 判据 | 结果 |
|---|---|
| 1. 7 条全部改完且每条指得出依据 | ✅ 见 §2；`AgentQueryResponse` 那条保留并写明理由 |
| 2. `export_openapi.py --check` 零 diff + `gen:api` 幂等 | ✅ [OK] / `IDEMPOTENT=0` |
| 3. pytest ≥1272 且不降、ruff、seams ERROR 0、readiness 🟢16 | ✅ 全绿，数与 §0 一致 |
| 4. 未兑现承诺口径计数 = 0 | ✅ **2 → 0**（历史沿革 1 处保留，判据措辞已精确化） |
| 5. CI 四 job 全绿 | ✅ 见 §7 |

## 5. 遗留登记（**不在本批处置**）

- **F-P7M-1｜`AgentQueryResponse` 的历史沿革陈述仍在契约里**（"Sprint 4 阶段 10.0 批次 A 扩展
  （Sprint 3 缺口 1 偿还）"，真源 `app/schemas/agent.py`）：这是**已发生的事实**，不是承诺
  ⇒ 逐条判定后保留。**这条同时也是对判据的提醒**：机械计数不可写成"见 Sprint 3 就红"。
- **F-P7D-2（未动）｜`client.ts` 里 `/agent/query` 写了两次**：按用户裁决绑到 **P7-E**
  （P7-E 大概率要动同一个文件的 `API_BASE_URL` 读取，那时删一行零成本）。

## 6. 不许外推

- **本批零逻辑改动**：所有 diff 都在 docstring / 注释 / 装饰器描述里。pytest 数未变（1272）
  就是证据——没有一行代码分支被改动。
- **文案变长 ≠ 信息变多**：每句都必须能指到 commit 或代码行；做不到就别写。
- **这不能替代 X-5 那一批**：P7-D 收的是"契约自陈假话"，本批收的是"注释与描述里的过期话"，
  两者口径不同，别混成一个"文案批次"。

## 7. CI 读数回填（**R-10：以 CI 为最终裁决**）

> ⚠️ 推送当时本机网络不可达（`github.com:443` 连不上），两次推送失败；恢复后才推成功
> ⇒ 下面的 CI 读数是**推成功后实跑**的，不是本地结果外推的。

| 项 | 读数 |
|---|---|
| CI run | **38391401636**（本次 push 含 `9b430e8` 实现 + `56316d3` 立案两个 commit，一次 run 覆盖） |
| 四个 job | 后端（ruff + pytest）✅ 2m30s ｜前端（lint + gen:api）✅ 44s ｜契约校验（前后端漂移门禁）✅ 31s ｜流水线汇总 ✅ 3s |
| CI 后端 pytest | **1311 passed / 7 skipped / 0 failed**（`Ruff 静态检查 All checks passed!`） |

与预测的核销：本批**没新增任何用例** ⇒ CI 计数应与 P7-D 收工时的 `1311` 持平。
实测正好是 1311 ⇒ 既没有退化，也没有"多出来"的用例，符合 R-9 的期望。
