# P5-B · 集成日志（J3 前端虚线 + 演示图谱恢复 + G3 回归 + D4 收口）

> **日期**：2026-10-07　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../archive/2026-10-07-P5-A/integration-log.md`](../archive/2026-10-07-P5-A/integration-log.md)
> **边界**：[`proposal.md`](./proposal.md)（10 条 Non-goals）｜**花销**：有（图谱恢复 MinerU+LLM、G3 两侧 live 评估）

---

## 0. 一句话结论

**J3 落了（¥0），演示图谱恢复起来了（Entity 2855 / Relation 3643，谱同原库），G3 跑出 C1 = 0.1765。**

三个必须说清的点（都不许被读成"完美收官"）：

1. **C1 从 P6-H 的 0.0294 变成 0.1765，不是本批改出来的** —— 差异全在 graph 侧：报告里
   `graph_spec.retriever = graph_mentions+lexical_rerank`，那是 **P6-J 已落地的检索换代**；
   本次两侧的 corpus_layer / kg_version / pool_size 与 P6-H **逐项一致**。
2. **D4 指定的比对前提已不成立** —— 磁盘上 `p6h-judge-graph.json` 已被 **P6-I 重判**
   （P6-H 的 35/40 → rubric-v2 的 37/40），当初产生 0.0294 的那张判分表**不存在了**。
   详见 §5.3，这是本批**唯一需要你裁决**的事。
3. **J3 的真机 DOM 断言是降级的** —— 仓库禁止引入前端测试框架（Non-goal 4）⇒ 没有
   浏览器可 drive。降级到「真实 API 数据 + 前端真实判定函数」断言，见 §3.3。

---

## 1. 开工自检（**结论来自脚本，不来自文档**）

| 项 | 读数 | 与 §8 基线 |
|---|---|---|
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0**，反向守卫 `test_g21_production_sqlite_guard_still_present` 在 `[SG]` 区，**地雷 0 项** | ✅ 一致 |
| `export_openapi.py --check` | `[OK] contracts/openapi.yaml 与模型一致` | ✅ 零漂移 |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12** | ✅ 一致 |

开工前一度以为要以 `.env` 的 Neo4j 口令为缺口（抄自 §6.3），实测确认：容器口令确为
`ci-graph-pw-2026`，`.env` 写着 `password` ⇒ **按 D5 改正**（`.env` 在 `.gitignore`，不进提交）。

---

## 2. T1–T2 · J3 前端虚线（角色 A，¥0）

### 2.1 改动（**两个文件，73 行**）

| 文件 | 内容 |
|---|---|
| `frontend/src/lib/reasoning.ts` | 新增 `todayISO()` + `isHopExpired(validTo, today)`；**判定单点持有** |
| `frontend/src/components/qa/reasoning-path.tsx` | 过期跳 ⇒ 卡片 `border-dashed` + 名字置灰 + 「已于 YYYY-MM-DD 失效」标签 + `data-expired` 属性 |

判定口径逐字对齐后端 `reasoning.py:545-546`（`valid_to is not None and str(valid_to) <= as_of`
⇒ unconfirmed）。**没有**为前端重写一套过滤条件——13 号记录「本次踩到的坑」正是死在
「探针自己重写过滤条件」上，此处照抄同一条纪律。

### 2.2 静态门禁（**真跑**）

| 命令 | 结果 |
|---|---|
| `npm run typecheck`（=`tsc --noEmit`） | exit **0** |
| `npm run build`（=`next build`，**真实门禁**：完整类型检查 + lint） | exit **0**，16 条路由全部 prerender 成功 |
| `npm run lint`（=`eslint`） | exit **0** |
| `npm run gen:api` 后 `git diff --stat` | **为空** ⇒ 契约零漂移（Non-goal 1 达成） |

### 2.3 行为断言（**真数据 + 真函数，见降级说明**）

真机取样（`POST /api/v1/agent/query`，`as_of=2025-06-01`，问「李静适用哪种工时制？」）：

```
hop0  李静        -[HAS_POSITION     from=null         to=null       ]-> 产线操作工
hop1  产线操作工  -[APPLIES_WORK_TIME from=null        to=null       ]-> 综合计算工时制
hop2  综合计算工时制 -[GOVERNED_BY   from=2025-01-01  to=2025-12-31 ]-> 第七条
```

⇒ 一条链上**同时存在**「应画虚线」与「不应画虚线」的两种跳，正是 §9 判据 3 要求的对照组。

把这三个 hop 喂给**前端真实的** `isHopExpired`（`--experimental-strip-types` 直接加载
`frontend/src/lib/reasoning.ts`，**不是照抄重写**）：

```
today = 2026-10-07
hop0 valid_to=null         => expired=false
hop1 valid_to=null         => expired=false
hop2 valid_to=2025-12-31   => expired=true
ASSERT_OK      # 另含 null / undefined / 未来日期 / 当天边界四条，全部符合后端口径
```

⚠️ **降级登记**：仓库无前端测试框架，Non-goal 4 明令不许引入 ⇒ **没有浏览器驱动的真机
DOM 断言**。上面这条断言覆盖的是「判定」，不是「渲染」；渲染侧只有 `build` 通过 + 代码
单点保证。如实登记，**不宣称 DOM 已验证**。

### 2.4 D1 措辞差异（**登记，未改契约**）

契约注释 `api.d.ts:3290` 写「非空 ⇒ 前端应画虚线」，省了「在今天已过期」这个前提。
当前语料上两者等价（`valid_to` 只有 `2025-12-31`），**严格口径以后端为准**，
代码里写了注释说明；按 Non-goal 1 **不改契约文本**。

---

## 3. T3 · 演示图谱恢复（角色 B，有花费）

### 3.1 路径（**D6 的脚本直连，没走 HTTP 上传那条路**）

```
docker exec graphrag-pg → CREATE DATABASE graphrag
GRANT ALL ON SCHEMA public TO app_owner / GRANT USAGE TO app_rls   ← 踩坑①
uv run alembic upgrade head                                        ← 踩坑②（顺序）
uv run python scripts/init_rls_roles.py --admin-url <superuser>
uv run python scripts/seed_attendance_ontology.py
uv run python scripts/ingest_attendance_csv.py
uv run python scripts/ingest_attendance_policies.py
```

两条踩坑都按 `changes/P7-A/integration-log.md:26-27` 的既有教训预先避开了：

- **踩坑①**：PG 15+ 起 `public` schema 不默认授予 CREATE ⇒ 先授权再迁移，否则
  `permission denied for schema public`；
- **踩坑②**：顺序必须是「建库 → 授权 → alembic → init_rls_roles」，反了会
  `DuplicateTable`。**没有**用 `alembic stamp head` 之类的掩盖手法——那会让 G-26 的
  迁移判据变成空跑。

实测：11 个迁移全部跑到 head（含 `8210590e76a5` RLS 策略 / `b7c4e1f9a2d3` nullif 谓词 /
`f3a91c2d6b70` licenses）；`init_rls_roles.py` 落 **14 张租户表** ENABLE + FORCE + 策略。

### 3.2 实读结果（**Neo4j 真数，不是脚本打印**）

| 项 | 本次重建 | 原库（§6.4 对照值） |
|---|---|---|
| `Entity` | **2855** | 2855（**逐位相同**） |
| `Relation` | **3643** | 3729（**-86**） |
| `POLICY_CLAUSE` 节点 | 107（抽取侧 107，一致） | — |
| `GOVERNED_BY` 边 | 99（规则桥接 **26/26** + 模型抽取 73） | — |
| `kg_versions` | `attendance-demo-v1` = **ready**，计数按全版本真实重算 | — |

`ingest_attendance_policies.py` 自带的 `verify_and_close` **四项全 `[OK]`**（§9 判据 5 达成）：

```
[OK] 关系无静默丢失（147/147 按 id 逐个核对）
[OK] 条款数一致（防止静默丢失）
[OK] 汇合边数一致且非空（26/26）
[OK] 两链路汇合可查（路径 354 条 / 员工 40 人 / 工时制 3 个 / 条款 22 条）
```

⇒ **§9 判据 4 / 5 均达成**。实体数逐位复现；D3 已写明「恢复 ≠ 复刻」，关系数 -86 落在
抽取的非确定性上，属允许范围。

### 3.3 一条**必须登记**的差异：`valid_to` 非空只有 30 条（J1 基线是 69）

```
cypher: MATCH ()-[r:RELATION]->() WHERE r.kg_version='attendance-demo-v1'
        AND r.valid_to IS NOT NULL RETURN count(r)   ⇒ 30
```

9-30 那次回填是 **69**。差异成因**未在本批追查到底**（再追就要摊到口径批去），
登记为已知差异。它**不影响**本批任何判据：J3 只需要图上存在过期跳即可
（§3.3 那条链就是现成的，落在 2025 版第七条）。

### 3.4 J3 端到端依赖满足

同一张图上，`as_of=2025-06-01` 的链末端确实带 `valid_to=2025-12-31`（见 §2.3）⇒
J3 的渲染前提在**本次恢复出来的图上**仍然成立，不是靠历史截图说话。

---

## 4. T4 · G3 受控题集回归（有花费）

### 4.1 引用覆盖率/拒答口径（`eval_controlled_qset.py`，40 题 live）

```
总题数 40 / 非拒答 36 / 引用命中 36 / 引用覆盖率 100.0% / 拒答口径不符 0 / 请求失败 0
结论: PASS
```

（**首跑曾全线 403 `LICENSE_MISSING`** —— 那是 dev license 缺失，不是回归，见 §6.1。）

### 4.2 C1（`eval_acceptance.py --live --criteria c1_graph_gain`）

| 项 | 本次 | P6-H 基线 |
|---|---|---|
| **C1** | **0.1765**（PASS(provisional)，阈值 10% 未校准） | 0.0294（FAIL） |
| graph | **1.000**（40/40） | 0.875（35/40） |
| baseline | **0.850**（34/40） | **0.850（34/40）** |
| corpus_layer / kg_version / pool_size | **L2 / attendance-demo-v1 / 213** | **L2 / attendance-demo-v1 / 213** |
| baseline embedding | BAAI/bge-small-zh-v1.5 | 同 |

两侧判分表为本批现判（`reports/eval/p5b-judge-{graph,baseline}.json`，rubric-v2，
依据 `eval_controlled_qset.py:73-173` 的 `expected_points` 逐条核对）：

- **baseline 侧 false 集合 = Q12 / Q34 / Q35 / Q36 / Q37 / Q38**，与
  `reports/eval/p6h-judge-baseline.json` **逐题一致** ⇒ 本次重建的 dense 基线与 P6-H 同口径同源；
- graph 侧 40/40，与 P6-J 的「40/40、C1 到顶」一致，且报告中
  `retriever = graph_mentions+lexical_rerank` 明示**图侧检索已换代**（P6-J 落的，不是本批）。

### 4.3 为什么 0.0294 → 0.1765 **不能**读成「变好了」或「回归了」

三条理由，逐条都有机器证据：

1. **pool_size / corpus_layer / kg_version / embedding 四项与 P6-H 相同** ⇒ 两侧同源可比，
   差异不来自语料或环境；
2. **baseline 侧 0.850 逐题复现** ⇒ 被测的「对照臂」没动；
3. **动的只有 graph 侧的 retriever**，而那次换代由 P6-J 早已登记、
   `p6j-judge-graph.json` 的 `_note` 写明「三条翻转归因于检索换了一代，不是 rubric 放宽」。

⇒ 正确表述：**「在 40 题口径下，图谱相对 dense top-k 基线的增益为 17.65%；
相对 P6-H 那次的 2.94%，差值全部来自 P6-J 已落地的检索换代，本批未引入任何回归。」**

### 4.4 ⚠️ 需要你知道的一件事：D4 的比对前提已经不成立了

`changes/P6-H/integration-log.md:26` 登记的是 **graph 0.875（35/40）**。但磁盘上
`reports/eval/p6h-judge-graph.json` 的 `_rubric_history` 自己写着：**本表已被 P6-I 按
rubric-v2 重判**（Q5 / Q7 两条翻 true，35 → **37**）。

⇒ **当初产生 0.0294 的那张判分表在磁盘上不存在了**，它没有被归档、只在 P6-H 的报告里留下数字。
本批因此**无法**用「同一张表重跑」的方式复现 0.0294，只能：

- 用**本轮答案 + 本轮现判**的两侧表跑出当前 C1（= 0.1765），并以 §4.2 的
  「baseline 逐题一致 + retriever 换代」两个交叉证据证明没有回归；
- 把这个错位**如实登记在这里**，不粉饰成一个整齐的对比表。

详见 §7 升级事项第 1 条。

---

## 5. T5 · D4 收口

### 5.1 pytest（**两种口径都跑，差值即结论**）

| 口径 | 读数 | 说明 |
|---|---|---|
| 本地（**补 `GRAPH_REAL_NEO4J_*`**） | **1006 passed / 4 skipped / 2 failed** | **与 §8 本地基线逐位一致** |
| 本地（不补 env，默认） | 1001 passed / **11 skipped** / 0 failed | 少的 5 条 + 失败的 2 条会转 skip |

≻ 那 **8 条 skip 的原因是缺 CI 注入的 `GRAPH_REAL_NEO4J_URI/USER/PASSWORD` 环境变量**，
不是「本地没有 Neo4j」——本地现在**有真图**。补齐后：

- **G-9 图谱侧 5 条（含 ADR-0003 §4.1 图谱侧 / DR-B11）由 skip 转为真跑并通过** ✅
  ——这是本批图谱恢复的直接收益，也是这批最实在的一条；
- 剩余 2 failed = `test_g25_real_graph_detection_is_not_empty` +
  `test_g25_v2_corpus_meets_thresholds_by_confidence_bound`，
  根因实测为 **`kg_version=affiliation-demo-v2` 在图上无数据**
  （`affiliation_detect_done total=0`、`Contract.trade_ref` 属性不存在）。
  ⇒ 即 §8 早已登记的**本地环境债**（缺 `affiliation-demo-v2` 语料），**与本批无关**，
  在 CI 上这条数据是有的。

**没有**为了让本地变绿而去动测试、也没有 SESSION 开关跳过它们。

### 5.2 三条门禁 + 护栏

| 项 | 读数 | 判据 |
|---|---|---|
| `pytest` | 见 §5.1 | ✅ 不降（本地与 §8 逐位一致；CI 待裁决） |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12** | ✅ |
| `export_openapi.py --check` | zero diff | ✅ |
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0** | ✅ 不倒退 |
| `ruff check .` / `ruff format --check .` | clean / **252 files already formatted** | ✅ 两个都跑（P2-C 教材） |
| `check_session_drift.py` | 每段收尾均 OK；S1 读到 10 条 Non-goals、S2 未超阈值、S5 无孤独模块 | ✅ |
| **CI（R-10 终裁）** | **run `37594891877` 四 job 全绿**；其中 pytest = **1007 passed / 5 skipped**，与 §8 CI 基线**逐位一致** | ✅ |

CI 四 job：`契约校验（前后端漂移门禁）` / `后端（ruff + pytest）` / `前端（lint + gen:api）` /
`流水线汇总` —— **全部 success**（`gh run watch --exit-status` 退出码 0）。
CI 侧的 ruff 也是 `All checks passed!`。

> 收尾的最后一次推送（本文档的定稿提交）亦已过 CI：**run `37595358195`** 四 job 全绿
> （`gh run watch --exit-status` 退出码 0）。本批 HEAD 与 `origin/main` 一致，工作区干净。

---

## 6. 环境债台账（**下一批开工先看这里，能省一小时**）

本批重建环境时踩到的环，全部登记。**这几样都不进提交**（`.env` 在 `.gitignore`、
`reports/` 已被忽略、`deploy/license/` 见下），换一台机器/换一个会话就会复发。

| # | 缺口 | 症状 | 处置 |
|---|---|---|---|
| 1 | **`.env` 的 `NEO4J_PASSWORD`** | 所有图谱操作 `AuthError authentication failure` | 改成容器口令 **`ci-graph-pw-2026`**（`docker inspect graphrag-neo` 可读出） |
| 2 | **PG 库 `graphrag` 不存在** | `FATAL: database "graphrag" does not exist` | `CREATE DATABASE graphrag` + public schema 授权 + `alembic upgrade head` + `init_rls_roles.py`（顺序见 §3.1） |
| 3 | **dev License 缺失** | 所有受保护端点 **403 `LICENSE_MISSING`**（首跑 G3 就是全线 403） | 按 ADR-0006 §2.3 **真签**一份 Ed25519 dev license 到 `deploy/license/app.lic`，并把 `LICENSE_FILE_PATH` / `LICENSE_PUBLIC_KEY` 写进 `.env`。私钥一次性、不入盘。**没有**用 `LICENSE_ENFORCE=false` 绕过（那会让 G-23 形同虚设） |
| 4 | **本地 embedding 服务未起** | C1 的 `awaiting_baseline` 恒为 0，报「embedding 未配置」 | `uv run python scripts/local_embedding_server.py --port 8009`（`.env` 里 `EVAL_EMBEDDING_*` 早已配好指向它） |
| 5 | **`GRAPH_REAL_NEO4J_*` 未设** | G-9 图谱侧 5 条 + `evidence_window_sentinel` 静默 skip（P7-A §5.2 的盲区） | CI 由 job env 注入；本地手动设三个变量即可让它们真跑 |
| 6 | **`affiliation-demo-v2` 语料不在本地** | G-25 两条真图判据 fail | §8 已登记的环境债；本批**未处理**（与本批恢复的 `attendance-demo-v1` 是两套语料） |

另：新增了对 `.gitignore` 的一行补充（`deploy/license/*.lic`），防止把签了名的 dev license
误提交进仓库——那是这个仓库少有的几个会真正泄漏的东西之一。

---

## 7. 收尾三问（自答）

1. **有没有"顺便做的"？属于哪条 DR / G？**
   有一处需要申报：渲染里加了一行「有效期 X ~ Y」的小字。它不属于「画虚线」的最小集合，
   但没有它，读者看到虚线**无法知道依据哪一天判的失效**（ADR-0005 的可解释性要求）。
   仍在 D2 允许的两个文件内，未新建模块（S5 绿）。其余全部对着 DR-D4 的 J3 / G3。
2. **有没有为躲坑而绕路的实现？**
   两处取舍，都登记不藏：① `todayISO()` 在 SSR 与 CSR 各算一次，跨日边界极小概率不一致
   （没有用 `useEffect` 规避闪烁，那会引入首帧错位）；② J3 的 DOM 断言降级（§2.3）。
   环境侧**没有绕**：License 403 与 embedding 404 都按根因补齐，没用 `LICENSE_ENFORCE=false`
   或关键词检索兜底。
3. **结论是真跑出来的还是读代码得出的？**
   除 J3 的渲染部分（降级，已标注）外全部实跑：typecheck / build / lint 三条 exit 0、
   `gen:api` 为零 diff、判定函数喂真实 hop 数据跑出 `ASSERT_OK`、图谱各项读数来自 Neo4j
   实读、C1 两侧 40 题 live、pytest 两种口径各跑一遍。
   **CI 已出结果并全绿**（run `37594891877`，pytest 1007 passed / 5 skipped，与 §8 基线逐位一致）
   ⇒ 终裁已过（R-10）。

---

## 8. 升级事项（须你裁决）

1. **【口径】P6-H 的 C1 = 0.0294 已不可复现**：判分表被 P6-I 原地改写且未归档
   （详见 §4.4）。两条出路：**①** 承认 0.0294 只是历史数字（判分表版本交代清楚即可）；
   **②** 专门补一批把 P6-H 原始的 rubric-v1 判分表找回来归档。
   本批**按 ① 处理**，但这是本批替你选的，请你确认。
2. **【未追查】`valid_to` 非空 30 vs 69 的差**（§3.3）：成因没有追到底。若下一批要靠这个数做
   判据，建议先把它当作独立小议题。

（其余三类升级边界均未触发：未改 spec / ADR、无边界冲突、CI 四 job 全绿。）

---

## 9. 降级登记

| # | 项 | 降级形态 | 原因 |
|---|---|---|---|
| 1 | **J3 真机 DOM 断言** | 降为「真实 API 数据 + 前端真实判定函数」断言 | Non-goal 4 禁止引入前端测试框架 ⇒ 无浏览器可驱动 |

---

## 10. 不许外推（**完成本批 ≠ 以下任何一条**）

- **J3 完成 ≠ 用户在产品里能看到虚线**：前端行为验证是**降级**的（§9）；且 as-of 入口
  根本不在前端（Non-goal 3），用户仍没有选时点的入口。
- **C1 = 0.1765 ≠ 能力变强**：那次增益是 P6-J 检索换代的产物，本批只是把它测出来。
- **C1 不可跨列比**：0.0294（35/40，rubric-v1/被改写前）与 0.1765（40/40，rubric-v2）
  分母虽同为 40，但**判分口径与被测检索都变了**。
- **图谱恢复 ≠ 复刻原库**：关系数 3643 vs 3729（-86），`valid_to` 30 vs 69。
- **本地 pytest 绿 ≠ 与 CI 同口径**：本地 2 条 G-25 仍在 fail（环境债），CI 上通过。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：P7-A §5.2 的 `skipif` 盲区仍在（本地默认读数会让
  8 条真图判据静默 skip）——本批只是用 env 把它们捞出来跑了一遍。

---

## 11. 下一批指针

- **D4 收口后**，P5 的下一个是 **D2（M6）**（`docs/delivery-plan.md:198`）。
  ⚠️ P5 从未做过 M6 的 recon，7 个端点此前全 501 —— 那批要先 recon，别直接开工。
- **下一批开工前必读**：本文件 §6（环境债台账，尤其 License 与 embedding 服务那两条），
  以及 `changes/archive/2026-10-07-P5-A/integration-log.md` §6。
- **遗留未动的清单**（Non-goal 9 / 10，留给口径订正批）：
  `_cypher_paths()` 的 DB 侧 LIMIT 400 与 Python 侧 7 维口径不一致、
  `_bridge_window.py:3` 的「（待核准记录）」注解漂移、
  DR-D4 编号改指 P5 的处置。

