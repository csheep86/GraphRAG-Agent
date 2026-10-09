# P6-S · A1 向量基线 + 双侧出卷 ⇒ 让 C1 的分母**可判**（判分仍归 P6-T）

> **日期**：2026-10-09 ｜ **上游**：[`changes/P6-R/`](../P6-R/)（2026-10-09，裁决 **O1** 已落地：接缝 3 钉 `temperature=0`）
> **计划真源**：[`docs/delivery-plan.md` §9.2 队列第 2 项](../../docs/delivery-plan.md)
> **判据真源**：`docs/dev-doc-status.md:380`（**A1 行**）+ `backend/app/evaluation/runner.py:1011`（`eval_graph_gain`）
> **一句话**：P6-R 把采样钉住后两侧终于同源；本批把 C1 从「不知道被什么挡住」推到
> **「两侧 40 题答卷都已出齐、双侧共因清单机器可读、只差人工判分」** —— 判分（P6-T，纯人工）
> 之前必须能**先看懂两侧是不是可比**，否则 80 道人工可能白判。

---

## 0. 开工实测（**本批自己跑出来的，不是引用**）

| 项 | 机读事实 | 出处 |
|---|---|---|
| 起点 | commit `101773e7`，CI run `37890683002` 四 job 全绿；工作区干净 | `git log` / `gh run list` |
| 护栏 | `check_startup_readiness.py` = **`[OK]` 17 / `[~~]` 0 / `[--]` 0** | 实跑 |
| 接缝 | `check_seams.py` = **ERROR 0 / WARN 0 / OK 12** | 实跑 |
| 契约 | `export_openapi.py --check` = **零 diff** | 实跑 |
| A1 反向守卫 | `tests/test_eval_baseline_a1.py` = **20 passed** | 实跑 |
| C1 的 `blocked_by`（**原文**） | `A3：图侧没有一题被人工判分（用 --judgements 提供）；脚本不自动判分 ⇒ 不判就等于没跑` | `reports/eval/p6s-c1-01.json` |
| 两侧是否出数 | `awaiting_graph` **40 题**（refused **4**）／`awaiting_baseline` **40 题**（refused **9**） | 同上（`git_hash=101773e7`） |
| 本地 embedding | 本地 `BAAI/bge-small-zh-v1.5` @ `127.0.0.1:8009`，冒烟 **dim=512 / n=2** | `local_embedding_server.py` + `Invoke-RestMethod` |

> ⚠️ **环境事实（P6-S 自发现）**：8002 上原本跑的后端进程是 **13:33 启动**的，
> 早于 P6-R 的 T=0 提交（**13:46**）⇒ **旧代码**。本批已**杀掉并重启** ⇒ 两侧才真正同源（D4）。
> 8009 未监听 ⇒ 本批拉起了本地 embedding 服务。

## 1. D1：C1 到底被什么挡住（**结论：不是"基线协议没建"**）

`dev-doc-status.md:380` A1 行写着「`BaselineRunner` 协议**并未建立**（`backend/` 内**零匹配**）」——
这句话**已过期**，本批用实跑否证：

- `app/evaluation/baseline.py` **494 行**已落地：`BaselineSpec` / `Embedder` Protocol /
  `OpenAICompatibleEmbedder` / `DenseTopKRetriever` / `answer_with_dense` / `comparability_error` /
  `pool_fingerprint` / `graph_side_spec` / `baseline_side_spec`；
- 基线侧**真的出了 40 题答案**（不是 fixture、不是空表）⇒ 「协议零匹配」已不成立；
- 真正缺的是 **A3 人工判分**（Non-goal 2：脚本不许代判 ⇒ 只能留给 P6-T）。

⇒ **D5 裁决**：按 **R-5 只追加不重排**，在 A1 行末尾**追加订正块**（含上述证据与 run id）。

## 2. D2：真缺陷 —— 「不可比」要等判完才暴露

`eval_graph_gain`（`runner.py:1011`）当前的返回顺序是：

```
mode → _qa_run(40 题 HTTP) → 判分闸门(1059 return) → … → 可比性断言(1080) → 出数
```

⇒ **`graph_spec` / `baseline_spec` 与 `comparability_error` 排在判分闸门之后**，
**没有判分就一个字都拿不到**。后果：

1. 若两侧实际**不可比**（换了池 / 基线侧 k 更小 / prompt 或模型不同），
   要等 P6-T 判完 **80 题**才被告知 ⇒ **人工劳动全部作废**；
2. 本批此刻**无法**贴出任何关于「防刷绿三条」的机器证据（D3 三条全部拿不到）；
3. 顺带多花了钱：`_run_baseline_side`（40 次 LLM）在**不可比**时照样跑完。

**本批的刀**：把双侧共因清单与可比性前置断言**提到判分闸门之前**（且提到付费之前）——
缺判分时**照旧不给任何判据数字**（`value=None`），但把「两侧怎么比的」完整落盘。

## 3. 关键决策（D1~D8，含开场提示词的必答项）

| # | 决策 | 处置 |
|---|---|---|
| **D1** ⚠️ | C1 真实阻塞项 | **已查实**：判分缺失（§1）。❌ 不许照抄 A1 行的旧口径 |
| **D2** ⚠️ | 完成线划在哪 | **出数不可能**（A3 + Non-goal 2 ⇒ 要有人的判分）。完成线 = ① 两侧 40 题答卷已跟踪落库（同一趟产出）；② 报告里必有 `graph_spec` / `baseline_spec` 与可比性结论；③ 防刷绿三条可贴机器输出。**增益数字仍为 `None`** |
| **D3** ⚠️ | 防刷绿三条怎么验 | ① 基线分落盘 ⇒ 本批尚无分（判分在 P6-T），但**落盘通道**（`baseline_accuracy` 字段）不改；② `baseline_spec` 进报告 ⇒ **本批补上**（含 `retriever` / `top_k` / `generation_model` / `prompt_id` / `embedding_model` / pool 指纹）；③ 反向守卫 ⇒ `test_eval_baseline_a1.py` 20 条继续全绿，**既有断言一条不放宽** |
| **D4** ⚠️ | 与 P6-R 同源怎么证 | 报告 `git_hash=101773e7`（含 T=0）+ 采样未被回滚（Non-goal 1）+ 两侧 `generation_model` / `prompt_id` 同源由 `_comparability` 机器比对 |
| **D5** ⚠️ | 过期口径订正 | A1 行追加订正块（§1）。`eval_acceptance` CLI docstring 的 `upgrade_todo` 里「A1 待裁决」一并点名（同一过期口径的第二落点） |
| **D6** | 判据进不进 CI | **不进**（依赖 live LLM + embedding，且判分未满）。新增/改动落在 `eval_graph_gain` 与 `_load_judgements` 的单测**本来就在 CI**，必须继续绿 |
| **D7** | 审计 / RBAC | 不动（`PROTECTED_ENDPOINTS` 现 **10 条**） |
| **D8** ⚠️ | 成本敞口 | 已完成 **1 趟**（`p6s-c1-01.json`：40 HTTP + 40 基线 LLM）。改动后**再 1 趟**取证（约同量）。每趟对应此前拿不到的结论：第 1 趟 = 出卷 + 查实阻塞项；第 2 趟 = 证明修复后报告带双侧 spec。**禁止「再跑一遍看看」** |

## 4. 明确不做（**Non-goals，10 条**）

1. **不回滚 / 不改 P6-R 的 `temperature=0`**（不许做成配置项）
2. **不得用脚本代判分**（A3）——导出的答卷只带 `answer` 原文，**不带任何 `correct` 值**
3. **不动题集**（`controlled-qset-v4.json` 40 题一字不改）
4. **不动 C2-a / C2-b / C2-c 口径**
5. **不动召回 / 重排**（P6-N / P6-J 已定案）
6. **不用 BM25 作主基线**（A1 已裁；本批连敏感性对照都不做）
7. **不做 L2 端到端 / 演练留证**
8. **不动 D4 / Sprint10.5**（队列第 4 项）
9. **不动前端**（无新消费方）
10. **不新增契约端点 / 错误码 / `settings.*`**（⇒ 不触发 S3）

> ⚠️ 若实现中发现必须新增 `settings.*` ⇒ 立即停下（升级第 2 类）。

## 5. 任务

| # | 任务 | 需要裁决 |
|---|---|---|
| T1 | 边界三件套 + 开工自检 | 否 |
| T2 | 查实 D1（实跑 C1）+ 起本地 embedding + 重启后端为最新码 | 否 |
| T3 | **重排 `eval_graph_gain`**：双侧 spec + 可比性断言提到判分闸门与付费之前 | 否 |
| T4 | `_load_judgements` 拒绝非布尔值（`bool(None)=False` 静默判错的洞） | 否 |
| T5 | 新增 `scripts/export_judging_sheets.py` ⇒ 两侧答卷（含题干 + `expected_points`）跟踪入库，锁「同一批改分」 | 否 |
| T6 | 单测补齐（**只加不放宽**）+ 本地全量 pytest | 否 |
| T7 | 改动后 **1 趟 live** 取证 + 口径回登（A1 行订正 / 集成日志 / 下一批指针）+ 收尾推送 | 否 |
