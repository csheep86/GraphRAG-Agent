# P6-K · 集成日志（只建「候选窗口哨兵」，不建召回）

> **日期**：2026-10-06 ｜ **边界文档**：`changes/P6-K/proposal.md`（Non-goals 9 条已冻结）
> **拍板**：D1 **= O1**（只建哨兵，不建召回）/ D2 **机械判据** / D3 **只 warn + 一份可复跑脚本**
> **上游硬约束**：P6-J 收尾的**裁决 A** —— C1 在本口径（rubric-v2 + 40 题 + `attendance-demo-v1`）
> **封顶 17.65%**，已降级为记过账的历史指标 ⇒ **本批不用 C1 出数、不宣称任何"召回增益"**。
> **一句话**：R22 剩的那半条根因（「候选集是结构性窗口」）我用 ¥0 量过了 ——
> **本语料上候选 213 = 版本内 chunk 总数 213，一条都没丢** ⇒ 它是**规模风险**不是**当前缺陷**；
> 所以本批不建召回，只把它变成**会自己喊的东西**（生产路径留痕 + 常驻诊断脚本）。

---

## 1. 为什么是"哨兵"而不是"召回"

| 事实（磁盘已量过，本批复现） | 推论 |
|---|---|
| 语料 chunk 总数 **213**；版本内实体 **2805**；生产子图采样实体 **500**；索引行上限 **1000** | 500 个采样实体已经覆盖了全部 213 条 chunk |
| 把采样拆到全量 2805 实体（U 口径）⇒ 候选**仍是 213** | **子图采样丢 0 条**。拆上限救不出任何东西 |
| 40 题逐题：S 候选恒为 **213**，窗口完整率 **100%**，撞上限 **0/40** | 「目标片段不在候选里」在本语料**从未发生** ⇒ 真正的筛掉发生在 **213 → 32**（P6-J 已处理） |
| 500 节点 / 1000 行是**固定预算**，语料一大必然开始丢 | ⇒ 它是**规模风险**，不是**当前缺陷**。为一个还没发生的缺陷建召回（方向②/③）**没有可证伪的判据**（本语料已 40/40，改完仍 40/40） |

⇒ 本批的判据换成**机械量**（裁决 D2）：窗口完整率 / 撞上限题数 / 必然丢失率 ——
**不依赖任何人工判分**。这顺带绕开了前几批「判分与实现同一人、无独立复核」的老毛病：
本批的每个数字都是**数出来的**，不是判出来的。

## 2. 落地了什么（3 个文件 + 1 处文档措辞）

| 文件 | 改动 |
|---|---|
| `backend/app/services/graphs.py` | ① 新增 `_QUERY_COUNT_CHUNKS_IN_VERSION`（版本内 chunk 总数，**与索引 Cypher 共用同一套 org 过滤** ⇒ 分子分母同源）；② 新增 `_warn_if_candidate_window_narrow`（纯函数、返回 bool、只 `logger.warning`）；③ 新增 `GraphService._count_chunks_in_version`（哨兵自己失败 ⇒ 返回 `None` + **另一前缀**的告警，**不**打断主流程）；④ `fetch_evidence_chunks` 的 `entity_ids` 路径在 `select_evidence_chunks` **之前**调一次哨兵 |
| `backend/scripts/probe_candidate_window.py` | 探针固化为**常驻**诊断（原 `changes/P6-K/_probe_candidate_coverage.py`）：输出**只留机械量**，去掉对 `reports/eval/p6j-dryrun.json` 的依赖；`--gold-citations` 显式给才出「必然丢失率」，没给就打印 `N/A`（**不**给 0） |
| `backend/tests/test_evidence_window_sentinel.py` | 10 条单测（合成 rows + 假会话真调用 `fetch_evidence_chunks`） |
| `docs/dev-doc-status.md` | **R22 只改措辞，不关闭**（见 §6） |

**两个刻意的设计决策**（都不是顺手）：

1. **哨兵放在 `select` 之前** —— "候选少了多少"是选之前就已发生的事，与后面选哪 32 条无关，
   早一步才归因得清；
2. **两条告警前缀刻意不同** —— `证据候选窗口不完整`（风险信号）vs `证据窗口哨兵自检失败`
   （诊断失明）。若共用前缀，"确实完整"与"根本没测成"在日志里长得一模一样。

**代价要记账**：读侧每轮问答多一次 `count` 往返（很便宜，不是全表回传）——
这是"可见性"的价钱，本批认了；若将来觉得贵，那是**另一个裁决**，不是本批能顺手去掉的。

## 3. 探针原始输出（回帖作为对照）

`changes/P6-K/_probe_candidate_coverage.txt`（**¥0，2026-10-06 跑出，已提交**）：

```
kg_version = attendance-demo-v1
语料 chunk 总数 T = 213
版本内实体总数 N = 2805
生产子图采样实体数 |S_e| = 500
索引行上限 = 1000

[U] 无采样口径（全量 2805 实体）⇒ 候选 213 条（占语料 100%）

   题   锚点    S候选    A候选     引用全在S
   1    0    213      0         ✅
   …（40 题逐行，见 txt 原文）…
  40    0    213      0         ✅
自校验：✅ 40 题答案引用的 chunk 全部落在 S 候选内（探针口径与生产一致）
```

新脚本（**已去掉 p6j-dryrun.json 依赖**）独立重跑，结论一致：

```
kg_version                 = attendance-demo-v1
语料 chunk 总数 T          = 213
版本内实体总数 N           = 2805
生产子图采样实体数 |S_e|   = 500
索引行上限                 = 1000

[U] 无采样口径（全量 2805 实体）⇒ 候选 213 条（窗口完整率 100.00%）

   题   锚点    S候选     S完整率    S截断    U候选     U完整率
   1    0    213  100.00%      否    213  100.00%
   …（40 题逐行，全为 213 / 100.00% / 否）…
  40    0    213  100.00%      否    213  100.00%

=== 汇总（机械量，不含任何人工判分）===
逐题 S 窗口完整率          ：min=100.00% max=100.00% 均值=100.00%
撞 index_limit 的题数      ：0 / 40
逐题候选数去重后的取值集合 ：[213]
必然丢失率                 ：N/A（未提供 --gold-citations ⇒ **不**给 0：没测就是没测）
```

**必然丢失率的一次性对照数**：用 P6-J 判分产物（`reports/eval/p6j-dryrun.json`，**一次性**，
脚本本身**不**依赖它）抽出 40 题答案引用的 chunk id 喂给 `--gold-citations` ⇒
**必然丢失率 0 / 40 = 0.00%**（与探针的「引用全在 S」自校验同一事实，换了条路复算）。
⚠️ 这个数**只对这一份语料 + 这一代答案成立**；换语料 / 换题集须重跑。

## 4. 验证（**全部真跑**，没有一条是读代码得出的）

| # | 判据 | 结果 |
|---|---|---|
| ① | 新脚本**独立**重跑复现 213/213 | ✅ 见 §3（真 Neo4j，`$env:NEO4J_PASSWORD='graphragdev'`） |
| ② | 哨兵在**人为构造的丢数据场景**下确实 warn | ✅ 单测内 monkeypatch `_EVIDENCE_CHUNK_INDEX_LIMIT=2`、版本内 5 条 chunk ⇒ 留痕命中且原因写明两条 |
| ③ | `export_openapi.py --check` 零 diff | ✅ `[OK] …与后端模型一致` |
| ④ | 全量 `pytest` 零回归 | ✅ **988 passed / 3 skipped / 3 xfailed**（P6-J 基线 978 ⇒ **+10**，0 回归） |
| ⑤ | **反向验证**：撤掉留痕 ⇒ 单测变红 | ✅ 见 §4.1 |

### 4.1 反向验证（硬验收，做了**两遍**）

```
--- R1：把 _warn_if_candidate_window_narrow 的告警体去掉（函数与调用点都留着）---
FAILED test_warns_when_index_is_truncated
FAILED test_warns_when_candidates_short_of_total
FAILED test_unknown_total_still_warns_on_truncation
FAILED test_sentinel_fires_when_index_limit_cut_the_candidates
4 failed, 6 passed

--- R2：把 fetch_evidence_chunks 里的调用点去掉（函数还在）---
FAILED test_sentinel_fires_when_index_limit_cut_the_candidates
FAILED test_count_failure_is_logged_but_does_not_break_the_read_path
FAILED test_sentinel_denominator_is_org_scoped
3 failed, 7 passed

（两轮均随后精确还原，还原后 ruff check 通过 + 10 passed）
```

**为什么做两遍**：R1 只证明"函数会叫"，R2 才证明"**生产路径真的接上了**"。
只做 R1 的话，将来有人把调用点删了而函数还在，纯函数层用例仍全绿 —— 那等于没钉住。

### 4.2 留痕长什么样（合成场景真跑出来的原文）

```
证据候选窗口不完整（R22：候选集是结构性窗口 —— 当前语料零损失，属**规模风险**而非已修缺陷）：
kg_version=sentinel-test-v1 候选=2 版本内 chunk 总数=5 窗口完整率=40.00%
原因=索引行撞上 index_limit(2)，候选被截断；候选 2 < 版本内 chunk 总数 5
```

（`index_limit` 调小只发生在**单测内**；产品默认值 `_EVIDENCE_CHUNK_INDEX_LIMIT = 1000` **一个数没动**。）

### 4.3 单测 10 条

- 纯函数层：`test_silent_when_window_is_complete`（完整 ⇒ **一声不响**）/ `test_warns_when_index_is_truncated`
  / `test_warns_when_candidates_short_of_total`（**没**撞上限但候选不足 ⇒ 照样叫，这才是规模风险的真实形态）
  / `test_unknown_total_does_not_fake_completeness`（总数未知 ⇒ **不**谎报完整率）
  / `test_unknown_total_still_warns_on_truncation` / `test_zero_total_does_not_divide_by_zero`；
- 服务层（假会话真调 `fetch_evidence_chunks`）：`test_sentinel_fires_when_index_limit_cut_the_candidates`
  （同时断言 `selected == ["c0", "c1"]` ⇒ **留痕不改返回值**）/ `test_sentinel_silent_when_window_is_complete`
  / `test_count_failure_is_logged_but_does_not_break_the_read_path`（哨兵挂了 ⇒ 问答照常，但**必须**留痕）
  / `test_sentinel_denominator_is_org_scoped`（分母带同一个 org，分子分母同源）。

> 留痕断言用的是 **loguru sink 捕获**，不是 `caplog`：本项目日志走 loguru
> （`app/core/logging.py`）且**不**桥接 stdlib logging ⇒ `caplog` 抓不到。**等价手段，验收未降格。**

## 5. 门禁

```
pytest（真 Neo4j / 真 PG）    988 passed / 3 skipped / 3 xfailed   ← 978 ⇒ +10，**0 回归**
ruff check .                  All checks passed!
ruff format --check .         234 files already formatted
check_seams.py                ERROR 0 / WARN 0 / OK 10（无新增接缝、无无消费者配置）
export_openapi.py --check     [OK] 契约零 diff
check_session_drift.py        S1 读到 9 条边界；S2 1 文件 / 141 新增行；S3–S5 全 OK
```

（跑测需 `$env:NEO4J_PASSWORD='graphragdev'` 与 `GRAPH_REAL_NEO4J_*` 三项；
本机 `.env` 里写的 `password` 与在跑的容器不符 —— 本机环境问题，**本批不改 `.env`**。）

⚠️ **本地全绿 ≠ CI 绿（收尾时查出来的，已修）**：首轮推送后查 `gh run view` ⇒ CI 的
backend job **红在 pytest 之前的「导入受控种子语料」** —— A8 语料在仓库根
`demo/affiliation/generated/`，而该 job 的工作目录是 `backend/` ⇒ 找的是
`backend/demo/affiliation/generated/` ⇒ `CorpusError` ⇒ **自 P6-D 起连续 8 次红，
pytest 与 G-25 门禁一步都没跑到**。本批两个提交里 ruff / format / 接缝 / 契约冻结 /
契约漂移 / 前端 lint **全 ✓**。

⇒ 已登记 **`dev-doc-status.md` R26**（根因 + 证据 + 影响面），**升级用户**；授权后
一行修毕（`ci.yml` 补 `../`，提交 `460c830`），CI run **37412509873 全绿**：
后端 **986 passed / 5 skipped / 3 xfailed**（本地 988 / 3 —— 差 2 条是本地有真 Neo4j
才跑得起来的真机用例，**非回归**）、G-25 门禁 `c2_a 1.0000 → 1.0000`、
`c2_b 0.0000 → 0.0000` 判过、契约与前端 ✓。详见 §9 第 6 条。

## 6. R22：**只改措辞，不关闭**

`docs/dev-doc-status.md` 的 R22 追加一段（**本条保持挂起**）：

> **2026-10-06 P6-K 已量化（本条**不关闭**）**：¥0 探针 + 常驻诊断
> `backend/scripts/probe_candidate_window.py` 实测 —— 本语料（213 chunk / 2805 实体 / 40 题）
> **窗口完整率 100%、撞 `index_limit` 0/40、必然丢失率 0/40** ⇒ 「目标片段不在候选里」
> **在当前规模下从未发生** ⇒ 措辞由「未量化」改为「**已量化：当前规模零损失，窗口随规模劣化**」。
> 已建**候选窗口哨兵**（`fetch_evidence_chunks` 留痕，只 warn）：语料一大必然开始告警。
> ⚠️ **不许**据此宣布本条关闭——哨兵只负责喊，不负责救；真正的"扩候选集 / 召回"仍待排期（O2）。

## 7. Non-goals 核销

| # | Non-goal | 是否守住 |
|---|---|---|
| 1 | 不校准 C1、不复活 C1 当判据 | ✅ 本批**零个** C1 读数 |
| 2 | 不动 P6-J 的词面重排 | ✅ `select_evidence_chunks` / `_lexical_*` 一行未动 |
| 3 | 不改 rubric-v2 / C1 公式 | ✅ 未碰 |
| 4 | **不引入第三方依赖 / 不装向量库** | ✅ `pyproject.toml` / `uv.lock` **零改动** |
| 5 | 不动 ingestion / 不改演示语料 | ✅ 只读，未写库 |
| 6 | 不改 40 题组成 | ✅ 40 题一字未动（判据第 ④ 条因此未触发，无需 40×2 重判） |
| 7 | 不顺手修 H6 403 / 入图器自检 / P7-B / G-12 / MANIFEST | ✅ 一个没碰 |
| 8 | 不动三个配额 | ✅ 默认值**一个数没动**（`index_limit` 调小只在单测内 monkeypatch） |
| 9 | **不许把"规模风险"说成"已修复的缺陷"**、不许宣布 R22 关闭 | ✅ §6 措辞已写明，R22 **保持挂起** |

## 8. 收尾三问（自答）

1. **有没有"顺便做的"？** 有一处必须摊开：为了算"窗口完整率"必须知道**分母**，
   于是**新增了一条计数 Cypher**（读侧每轮问答 +1 次往返）。这是本批判据成立的**前提**，
   不是顺手加的；代价已记在 §2。除此之外**没有**任何 Non-goals 之外的改动。
2. **有没有为躲坑而绕路的实现？** 有一处**差点**绕：把总数塞进索引那条 Cypher
   （省一次往返）。没做——那条带 `LIMIT`，"被截断的行数"和"版本内总数"是两件事，
   硬塞只能靠标量子查询（Neo4j 5 才有），且会让哨兵的分母随 `LIMIT` 变形。
   另一处要说明：哨兵失败时**返回 `None` 而不抛**——这与本项目"投影失败显式抛"的
   取舍**相反**，是有意的：投影失败会让上层把"数据坏了"读成"没有证据"，
   而哨兵失败只损失一双眼睛，**不该**把能正常回答的问答打成 501；代价由另一条
   不同前缀的告警补上（不会静默失明）。
3. **验收是真跑还是读代码？** 全部实测：脚本真连 Neo4j 重跑（§3）、
   单测真调 `fetch_evidence_chunks`（假会话）、反向验证**真撤代码两遍**（§4.1）、
   门禁六项全跑（§5）。**没有一条结论来自读代码。**

## 9. 遗留（已登记，本批不碰）

| # | 事项 | 归属 |
|---|---|---|
| 1 | **O2**：造更大语料（让 500 采样真的开始丢 chunk），再比选方向②实体链接 / ③向量召回 | **另开批次**（D1 已裁决） |
| 2 | 哨兵一旦真的告警 ⇒ 说明规模风险已兑现，需按 O2 处理 | 由告警驱动，届时另开批次 |
| 3 | 「必然丢失率」目前靠一次性 gold（`p6j-dryrun.json`）才出数 ⇒ 无长期 gold 标注 | 换语料 / 换题集时须重新标注 |
| 4 | C1 已瞎（40/40 封顶）；扩/换题集与换语料均未做 | P6-J 遗留，裁决 A 已记账 |
| 5 | H6 403 / 入图器自检 / P7-B / G-12 / MANIFEST 语料统计 | Non-goals 第 7 条 |
| 6 | **CI 后端 job 既有红（非本批引入）**：卡在 pytest **之前**的「导入受控种子语料」—— A8 语料在仓库根 `demo/affiliation/generated/`，而 CI 在 `backend/` 下找 `backend/demo/affiliation/generated/` ⇒ `CorpusError`（自 P6-D 起连续 8 次红，pytest 从未执行） | ✅ **已修**：登记 **`dev-doc-status.md` R26** → 升级用户 → 授权后一行修毕（`ci.yml` 补 `../`，`460c830`）⇒ CI run **37412509873 全绿**（后端 **986 passed / 5 skipped / 3 xfailed**；G-25 门禁 `c2_a 1.0000 → 1.0000`、`c2_b 0.0000 → 0.0000` 判过） |
