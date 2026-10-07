# P5-A 集成日志 · D4 解冻「出路 A 的裁决性验证」

> **本批未产生任何代码改动。** 开工自检后做了一轮针对决策依据的机械核查，
> 结论是**本批立项的四项依据全部已失效/不可执行**，按 §5 表头
> 「执行中若发现依据有误 ⇒ 停下升级，不要默默改道」与 §10 升级边界第 1 / 2 类，
> **停在这里等裁决**。下面是把投资者的证据固化成文档，**省得下一批把同样的 recon 再做一遍**。
>
> 日期：2026-10-07　花费：**¥0**（未跑任何 LLM 抽取 / MinerU）

---

## 0. 一句话结论

**A/B/C 这条路早在 2026-09-30 就已经走完了**：用户裁决 **A**（语料逐条写明施行日）⇒ 执行后
`valid_to` 2 → 48；随后 **B**（R4-b 文档级作用域继承）也经用户核准落地 ⇒ `inconsistent`
259 → **352**、两个时点选出的链也真的不一样了。

**⇒ 「裁决 A 成立与否」这个交付物已经不成立了——它是 09-30 之前的待办，09-30 当天已被事实回答。**
真正剩下的只有一件事：**J3 前端虚线（一行未写）** + **J5 受控题集回归**。

---

## 1. 阻断性事实：本地**没有图谱**，G1 / G2 / G3 一行都跑不出来

§9 的三条验收判据全部要读 Neo4j。实况：

| 项 | 实测 | 坐标 / 命令 |
|---|---|---|
| 本地 Neo4j 容器 | `graphrag-neo`（`neo4j:5.26-community`）**Up 2 hours** | `docker ps` |
| 该容器的口令 | `NEO4J_AUTH=neo4j/ci-graph-pw-2026` | `docker inspect graphrag-neo` |
| `backend/.env` 的口令 | sha256 前缀 `5e884898da28…`（= 明文 `password`） | 非空 8 字符 |
| 两者不一致 ⇒ | `AuthError ... authentication failure` | bolt://localhost:7687 握手成功、**认证失败** |
| 用容器口令连上后 | `MATCH (n:Entity) RETURN count` = **0**；`RELATION` 类型**不存在** | `MATCH ()-[r:RELATION]->()` ⇒ `count=0` + 服务器告警 `relationship type does not exist` |

**这不是"换个口令就通"的问题**——那个实例是**空的**。

⇒ §5 D1 的成本栏写的「两份文档各一次 MinerU + 抽取」，前提是**已有演示库**
（entity 2855 / relation 3729，见 `10-gate-report.md:14`）。那个库此刻**不存在于任何本地实例**。
要把它找回来 = 重建整条链路（`ingest_attendance_csv.py` + 6 份文档从头 MinerU + 真实 LLM 抽取），
**成本是 D1 估值的好几倍，且要从还清 execute 一遍 `2025` 版之前的所有入库**。

⚠️ 顺带更正 §8 基线里那句「本地 Neo4j 口令」缺口的说法：口令是可以从
`docker inspect` 读出来的，真缺口是**容器是空的**，不是口令。

---

## 2. 依据失效①：出路 **A** 已于 2026-09-30 裁决**并执行过**

`changes/Sprint10.5/11-derived-window-inheritance.md:9` 原文：

> 施行 forward 补的 2026 版语料后（**用户裁决 A：语料逐条写明施行日、重抽 4 份**），
> 带失效期的关系已从 **2 条 → 48 条**，2026 侧带 `valid_from` 的关系 **7 条 → 108 条**。

而且 §9 判据 1 要"改写"的那个东西**磁盘上已经是目标形式**——不必再改：

```
demo/attendance/policies/attendance-policy-2025.md:17
第一条 …本条自 2025 年 1 月 1 日起施行，有效期至 2025 年 12 月 31 日。
（第十三条为止，13 条**逐条**都带； fieldwork-attendance-rules-2025.md 8 条同）
```

文件头自带的说明也写明了这是对照实验的语料形式（`:7-11`），且 docx 产物
`corpus/attendance-policy-2025.docx` 已经在库里（同一次提交 `2536f1cd`）。

**⇒ 判据 1 的"写双文档 → 重生成"两步已经做完，只剩下要花 ¥ 的重抽——而它要证明的东西已被证明过了。**

---

## 3. 依据失效②：出路 **B** 已核准 + 落地，**G2 早就翻面了**

§5 D1 的前提是「B 是口径变更，还没裁」。实测 **已裁 + 已写进 spec / ADR + 已实现 + 已验收**：

| 落点 | 坐标 | 原文要点 |
|---|---|---|
| 核准状态 | `12-document-scope-inheritance.md:3` | 「**已核准（用户裁决 A，同刻起允许改代码）**」 |
| ADR | `docs/adr/ADR-0005-temporal-knowledge-model.md:153` | 「R4-b 文档级作用域继承（Sprint 10.5 增补，**用户 2026-09-30 裁决**）」 |
| spec | `specs/m2-extract-kg.md:240` + `:246` | R4-b 登记 + §4.6.4 实现边界 |
| 解析器 | `app/services/parsing/document_date.py:227` | `resolve_document_expiry` |
| 继承口径 | `backend/scripts/_bridge_window.py:87/127/164` | `document_window` / `record_document_scope` / `apply_clause_window` **fallback 分支** |
| 接线 | `backend/scripts/ingest_attendance_policies.py:627` | `fallback=doc_window` 已传入 |

**验收回填（`12` 号 §5，2026-09-30 真机）**：

| 项 | 基线 | 实测 | 判据 |
|---|---|---|---|
| `inconsistent` 链 | 259 | **352** | ⇒ §9 **判据 2 已达成**（10.4 报 0 的那个数） |
| `valid_to` 非空 | 60 | **69**（全部落在 2025 版实体上） | ⇒ §9 **判据 1 已达成** |
| 两时点获胜链末端 | 相同 | **不同** | ⇒ J4 as-of 也一并达成 |
| 主链缺日期边 | 191/226 | **26** | 降 86% |

⇒ §10 升级边界第 1 类担心的「转 B 必须先裁 R4 边界 + 改 `specs/m2` 与 `ADR-0005 §4`」
——**那一步在 09-30 已经做完了**，从档案里能逐字回查。

---

## 4. 依据**缺陷**：§9 判据 2 指定的那个探针，本身不可信

§9 判据 2 要求「`probe_l2_path_temporal.py` 重跑」。而 `probe_g2_inconsistent.py` 的 docstring
开宗明义说它为什么存在：

> 10.4 的 ``probe_l2_path_temporal.py`` 用 ``ORDER BY rels LIMIT 4000`` **随机抽样**，
> 但全库 2 跳链有 **19 万+** 条（真机实测 192180）——那 2 条跨版本冲突链被排到样本之外
> ⇒ 它报 ``inconsistent = 0`` 是**采样盲区**，不是数据不存在。

**⇒ 「inconsistent 仍为 0 ⇒ G2 未通过」这个结论，是被一个有缺陷的探针骗出来的。**
`proposal.md:10` 与 `10-gate-report.md:39-41` 的冻结理由，建立在它上面。

（同类教训 `13-as-of-evidence-rank.md:39-49` 又踩了一次：两版探针都因为**没有复用生产谓词**
而误报。作者已经把教训写进探针头了。）

---

## 5. D4 的真实剩余缺口：**只剩 J3（前端虚线）**——而不是裁决

这条最关键，因为它把"下一批该干什么"直接给出来了。

`13-as-of-evidence-rank.md:59-60` 验收原文：

> 2025 时点现在落到真正的 2025 版条款，且 `valid_to=2025-12-31` ——
> **这正是前端画虚线需要的那个字段，议题 ② 的渲染前提由此具备。**

后端侧已落的：

- `app/services/reasoning.py:505` `_TEMPORAL_RANK`（consistent/unknown/inconsistent 三级）
- `app/services/reasoning.py:221-224` as-of 视图谓词
- `frontend/src/types/api.d.ts:3290` 契约注释已写着：
  「非空 ⇒ 前端应画虚线表示这条事实已经过期」，`valid_to?: string | null` 已在契约里

**前端侧实测 = 零消费**：

```
git grep -ni "valid_to|dashed|strokeDasharray" -- frontend/src frontend/lib frontend/types
⇒ reasoning-path.tsx 里没有一处读 valid_to；
   命中的 dashed 全是空状态卡片的 border-dashed 类名（attribution-panel / evidence-panel /
   upload-dialog / placeholder-page），与失效边渲染无关。
```

**⇒ J3 一行未写。这才是 D4 真正剩下的活。**

---

## 6. 顺带查到的两笔债（本批**只登记，不修**，免得摊太大）

| # | 债 | 坐标 | 建议处置 |
|---|---|---|---|
| 1 | `_bridge_window.py:3` docstring 仍写「（**待核准记录**）」，而 12 号早已核准 ⇒ 注解漂移 | `_bridge_window.py:3` | 同 §6 表格最后一类，下一批顺手订正（不影响行为） |
| 2 | G3 受控题集回归（`eval_controlled_qset.py`）**仍欠一次** | `proposal.md:16-19` | 与 J3 批同批做——反正那批也要起一次真图 |
| 3 | `_cypher_paths()` 的 DB 侧 `ORDER BY … LIMIT 400` 与 Python 侧 7 维口径不一致；当前候选 165 行够不着 400 故未触发 | `13-as-of-evidence-rank.md:69-74` | 留给口径批，属丼 13 号自己登记的遗留 |

---

## 7. 本批实测过的读数（都不花钱 / 不需要图）

| 项 | 读数 | 命令 |
|---|---|---|
| 开工自检 | **`[OK]` 已生效 17 条 / `[~~]` 0 / `[--]` 0**，反向守卫 `test_g21_production_sqlite_guard_still_present` 在 `[SG]` 区， **[!!] 地雷 0 项** | `check_startup_readiness.py` |
| 接缝门禁 | **ERROR 0 / WARN 0 / OK 12** ✅ 与 §8 基线一致 | `check_seams.py` |
| 契约 | **zero diff** ✅ 与 §8 基线一致 | `export_openapi.py --check` |
| 本地图谱 | **空**（0 Entity / 0 RELATION） ⇒ pytest 那条 "real graph" 门槛在本地必红 | §1 |

---

## 8. 为什么没有默默改道（对照 §5 / §10）

| 诱惑 | 为什么没做 |
|---|---|
| 直接执行 B（既然它已核准） | B **已经在 HEAD 里**了，没有"执行的余地"；再跑一次入库 = 白烧 ¥ |
| 按 D3「停止 + 报告」走个形式 | D3 的前提是"A 被证伪"，而实况是 **A 早已成立且已被超越**，不是一回事 ⇒ 走 §5 表头的「依据有误」而非 D3 |
| 顺手把 J3 前端写了 | S5 会命中：它属于 **DR-D4 / J3**，但**不在本批 11 条 Non-goals 允许的范围内**（Non-goal 7 明写「不写 ②③ 的功能代码」）。写完等于违反自己刚登记的边界 ⇒ **留给下一批** |
| 改 `delivery-plan.md` / `requirements` 的陈旧口径 | Non-goal 11 明写「只登记、不修」⇒ 只在 §6 / 本报告里登记 |

---

## 9. 升级事项（须你裁决）

1. **方向**：本批要不要废？建议 **废**——它的交付物（裁决 A）已是历史，且唯一的实现路径
   （本地重烧全链路演示库）成本远超立项估算。
2. **下一批做什么**：建议 **`P5-B` = J3 前端虚线 + G3 受控题集回归 + D4 收口**。
   前置：**先把演示图谱起出来**（否则 J3 无法端到端验收、G3 也跑不了）。
   这条前置本身可能值得单独一批（`P5-A'`）。
3. **NUM 编号**：`DR-D4` 在 `delivery-requirements-and-guardrails.md:117` 仍记 🟡 在途，
   「编号须改指新阶段」的处置挂在 §6.4 —— 本批未动（Non-goal 11）。
