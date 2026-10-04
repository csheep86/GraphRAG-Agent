# P6-B 集成日志 —— **A6 + L8 兑现：C2-c 两档输出 + 拒答误伤立独立判据**

| 项 | 内容 |
|---|---|
| **批次** | P6-B（P6 第一步的第二半；与 P6-A（A8）同属"P6 第一步"） |
| **日期** | 2026-10-04 |
| **依据** | `changes/P0-m6-eval/integration-log.md` **L10-A6 裁决**配套第 1 / 2 条 + **L11(b)2**（已承诺未兑现） |
| **出口判据** | `proposal.md` §4：① passed 不减；② 反向验证判红；③ 真链路实测（**未达成，已如实登记**）；④ 全部门禁 |

---

## 1. 门禁实测（**跑出来的**）

| 门禁 | 起跑（P6-A 收束后） | 收束（本批） |
|---|---|---|
| `uv run pytest -q` | 922 passed | **930 passed / 3 skipped / 3 xfailed**（+8 = `tests/test_eval_refusal_a6.py`） |
| `ruff check` / `ruff format --check` | 双绿 | 双绿（224 files） |
| `check_seams.py` | 接缝 OK 10 | 接缝 OK 10 / ERROR 0 |
| `export_openapi.py --check` | 零漂移 | 零漂移 |

## 2. 做了什么

| 文件 | 改动 |
|---|---|
| `app/evaluation/runner.py` | ① C2-c **补含拒答档**（`coverage_including_refused` + `coverage_require_span_including_refused` + `coverage_basis` 口径标注），**判据值仍是排除拒答档（不改行为）**；② 新增 `_QaRun` 快照 + `_QA_CACHE` ⇒ **C2-c 与拒答误伤共用一遍问答**（不付两倍 LLM 调用，也不会两遍结果打架）；③ **误伤/漏拒方向分家**（`false_refusals` / `missed_refusals`）；④ 新增判据 `refusal_false_refusal`（值 = 误伤条数，阈值 **0**，越低越好）并登记 + 进 `ALL_CRITERIA`（**紧跟 C2-c**） |
| `app/evaluation/report.py` | 人读摘要：C2-c 那行并列显示**含拒答档**与口径标注（只打 1.0000 ⇒ 拒答缺陷被覆盖率盖住） |
| `tests/test_eval_refusal_a6.py`（新增） | 8 条纯逻辑（桩掉题集与问答，**不需要后端 / LLM / Neo4j**） |
| 文档 | 需求基线 **DR-D10**（C2-c 两档 + 新判据 FAIL + 未实测登记）、**G-25** 基线文件名订正为 `ci-c2-v2.json`（P6-A 遗漏）、`docs/release-notes/v1.6.0.md` 新增「C2-c 的口径必须一起读」表（L10-A6 配套第 3 条要求）、`P0-m6-eval` 日志 **L11(b)2 勾销** |

## 3. ⚠️ 未达成：**真链路实测没做成**（不拿单测冒充实测）

试过，卡在**演示数据重建**，不在本批边界内：

| 步骤 | 结果 |
|---|---|
| 起后端 | ✅ 先补 `alembic upgrade head`（dev 库缺 `app` schema）+ `init_rls_roles.py`（缺受控函数）后，后端 HTTP 200 |
| `agent/query` | ❌ 恒 **501**，detail 明写：`Neo4j 不可用: PG kg_versions 中无 ready 版本（PG 为真源）` |
| 重建演示图 | ❌ `ingest_attendance_csv.py` ⇒ `GOVERNED_BY 连边为 0——事实与条款未连通（R10 目标未达）`，拒以 active 收场；先跑 `ingest_attendance_policies.py` 仍未解 |

⇒ **本批的两档数字（1.00 / 0.786）与误伤数（1 条 Q8）沿用 P0-m6-eval 的历史实测**，
本批**没有**新的真链路数字。已在需求基线、release notes、本日志三处标明"未实测"。
**复现命令留在下面**，等演示图重建好后一条命令即可补测。

## 4. 反向验证（**逐条判红**）

| 破坏 | 判红 |
|---|---|
| 去掉含拒答档（detail 不再输出） | ✅ |
| 判据值改用含拒答档（⇒ C2-c 对拒答不再免疫 / 触发 F3） | ✅ |
| 误伤方向合并（漏拒也算误伤 ⇒ 0 阈值判据失真） | ✅ |
| 新判据不登记 | ✅ |
| 链路不可用时误伤判据返回 0（⇒ 假绿） | ✅（首版破坏是空操作 `if False`，已重做为真破坏） |
| 问答跑两遍（缓存失效） | ✅ |

## 5. 踩坑（写进测试注释了）

**`_QA_CACHE` 键只有 `mode`** ⇒ 单测里换场景若不清缓存，第二次拿到**上一次**的快照
（实测症状：两档都成 1.0、误伤数恒 0）。生产路径一次 CLI 运行只有一份 ctx ⇒ 无此问题，
但测试 fixture 必须显式 `clear()`（已写进 fixture docstring）。

## 6. 未决事项

| # | 事项 | 级别 | 处置 |
|---|---|---|---|
| 1 | **Q8 拒答误伤的链路修复**（本批只立判据、不修链路） | 高 | 另批（需真机 + LLM，可能 flaky）；判据已 FAIL ⇒ 它现在**会拦人**了 |
| 2 | **真链路实测**（演示图重建：`GOVERNED_BY=0`） | 中 | 另批或人工重建后补测（命令见下） |
| 3 | **A1**（向量基线 + 双侧判分 + 反向守卫）⇒ C1 图谱增益 ≥10% 仍判不出 | 高 | 下一阶段 |
| 4 | **L2 端到端**未做（且**未裁决**："什么叫端到端"要先定义） | 高 | 下一阶段（先裁定义） |
| 5 | **TBD-7 收敛口径**的 N / X 未裁（需人裁） | 中 | 等人裁 |
| 6 | 本批**未**把新判据放进 CI 门禁（当前 FAIL + 依赖 LLM ⇒ 会 flaky） | 低 | 修好 Q8 后再议 |

## 7. 复现命令

```bash
cd backend
export NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=graphragdev
uv run alembic upgrade head                      # dev 库第一次要跑（否则缺 app schema）
uv run python scripts/init_rls_roles.py --admin-url postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag
uv run python scripts/ingest_attendance_policies.py   # ⚠️ 当前卡在这里：GOVERNED_BY 连边仍为 0
uv run python scripts/ingest_attendance_csv.py
uv run uvicorn app.main:app --host 127.0.0.1 --port 8002   # 另开一个终端
uv run python scripts/eval_acceptance.py --live \
  --criteria c2_c_citation_coverage,refusal_false_refusal
uv run pytest -q tests/test_eval_refusal_a6.py     # 8 条（不需要后端）
```

> ⚠️ 无 `Authorization: Bearer`（`/auth/login` 未实现，P3-D 缺口 C）⇒
> 直接 curl `agent/query` 会 401；评测脚本走 `X-Org-Id` / `X-Actor-Id` 头（dev fallback）。
