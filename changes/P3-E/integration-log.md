# P3-E 集成日志 —— **G-25：C2-a / C2-b 进 CI 成真门禁**

| 项 | 内容 |
|---|---|
| **批次** | P3-E（G-25 本体） |
| **日期** | 2026-10-04 |
| **前置** | P3-B 已给 CI 的 backend job 起 `neo4j:5.26-community`（与 G-9 共用的工程项） |
| **出口判据** | `proposal.md` §2：① passed 不减；② gate 规则各自反向验证判红；③ **真图实测**（含空图守卫取证）；④ 全部门禁 |

---

## 1. 门禁实测（**跑出来的**）

| 门禁 | 起跑（P3-D 收束后） | 收束（本批） |
|---|---|---|
| `uv run pytest -q` | **892 passed**（开真图开关） | **903 passed / 3 skipped / 3 xfailed**（+11 = `test_eval_ci_gate.py`） |
| `check_startup_readiness.py` | 无 G-25 条目 | **G-25 11 项**（按 `test_g25_*` 认领） |
| `ruff check` / `ruff format --check` | 双绿 | 双绿（220 files） |
| `check_seams.py` | 接缝 OK 10 | 接缝 OK 10 / ERROR 0 |
| `export_openapi.py --check` | 零漂移 | 零漂移 |
| `ci.yml` 解析 | — | 新增两步：**导入受控种子语料** → **C2-a / C2-b 门禁**（`--gate`） |

## 2. 真图实测（本地 Neo4j 5.26，**非打桩**）

| 步骤 | 实测 |
|---|---|
| 导入受控种子语料（`demo/affiliation/*.csv`，`--purge` 幂等） | **176 entity / 173 relation**，`kg_version=affiliation-demo-v1` |
| `--live --criteria c2_a,c2_b` | **recall = 1.0000 / fpr = 0.0000**（与 P0-m6-eval 的实测一致 ⇒ 语料**可复现**） |
| `--gate`（有种子） | **退出 0**（与基线一致） |
| **清空种子后**再 `--gate` | **退出 1**，报错直指「空图守卫——gold 9 组、检测产出 0 疑点 ⇒ 种子语料没导入」 |
| 重新导入后 | 退出 0 ✔ |

> C2-a / C2-b 走 `AffiliationService().detect()`：**只读 Neo4j、零 LLM、零 HTTP**
> ⇒ 不需要 LLM key，也不会因模型输出抖动而 flaky（P0-m6-eval 实测 2.72 秒）。

## 3. 改动清单

| 文件 | 改动 |
|---|---|
| `backend/app/evaluation/gate.py`（新增） | 门禁**纯逻辑**五条规则：① `value is None` ⇒ fail；② 基线缺项 ⇒ fail（**不许跳过比对**）；③ 空图守卫（`gold>0` 且 `detected==0` ⇒ fail）；④ 退化（recall ↓ / fpr ↑ 超容差 0.02）⇒ fail；⑤ **不达标 ⇒ 不 fail**，只 warning |
| `backend/scripts/eval_acceptance.py` | `--gate` / `--baseline` / `--tolerance` / `--update-baseline`（写基线时打印"刷基线即重设门禁刻度"警告） |
| `backend/data/eval/baselines/ci-c2-v1.json`（新增，入库） | **实测**值：recall 1.0 / fpr 0.0，带 `git_hash` / `generated_at` / 容差 |
| `backend/tests/test_eval_ci_gate.py`（新增） | 10 条纯逻辑（**不需要 Neo4j**）+ 1 条真图端到端 |
| `.github/workflows/ci.yml` | 两步：导入种子语料 → `--gate`；失败摘要补复现命令与基线说明 |
| 文档 | 需求基线 G-25 行转 ✅（含"它不判什么"）；`delivery-plan.md` P6 行 |

## 4. 反向验证（**逐条判红**）

| 破坏 | 判红 |
|---|---|
| 去掉空图守卫分支 | ✅ |
| 去掉"基线缺项 ⇒ fail" | ✅ |
| 去掉"`value is None` ⇒ fail" | ✅ |
| 误报方向写反（`worse = -delta`） | ✅ |
| 容差放大到 1.0 | ✅ |
| **清空种子语料**（真图端到端） | ✅ `--gate` 退出 1 |

## 5. ⚠️ 本批踩到的两个坑（都值得记住）

1. **fixture 泄漏**：真图 e2e 用例 monkeypatch 了 settings 并 `GraphService.reset()`，
   但**没在 teardown 再 reset 一次**——`GraphService` 是单例、缓存了 driver，
   monkeypatch 还原 settings **不会**让它重连 ⇒ 后续 3 条「Neo4j 不可达 ⇒ 501」的用例
   被带红（症状是"别人的用例红了"，排查方向完全错）。已改成 fixture 里 `yield` + **双重 reset**。
2. **静态断言被 docstring 蒙过**（P3-D 已遇同型病）：判据 9 初版用文本匹配
   `"database_url_owner" in text`，去掉 owner 后仍绿——因为 docstring 里提到了这个词。
   G-25 的门禁规则因此**全部做成纯函数 + 单测**，不靠文本匹配。

## 6. 未决事项

| # | 事项 | 级别 | 处置 |
|---|---|---|---|
| 1 | **达标判定**（召回 ≥0.80 / 误报 ≤0.15）仍在 P6，且需先裁 **A6+L8**、完成 **A8 扩标** | 中 | CI 只判不退化；达标另议 |
| 2 | 基线值是 **provisional 语料**（8/60/30/9）上的值，不是 spec 的 200/500/100/20 | 中 | A8 扩标后必须**重设**基线（那时 `--update-baseline`） |
| 3 | 一次 `test_upgrade_head_matches_metadata` 偶发红（`permission denied to terminate process`），重跑即绿 | 低 | 疑似本地残留的超级用户连接（我的临时脚本）所致；非代码缺陷。本地另有 3 个孤儿 `graphrag_mig_*` 测试库，可自行 `DROP DATABASE` |
| 4 | TBD-7 收敛口径（本批 `--tolerance` 借用了相关脚本？否——本批独立） | 低 | 与 G-25 同批由人裁，另议 |

## 7. 复现命令

```bash
cd backend
docker run --rm -d -e NEO4J_AUTH=neo4j/ci-graph-pw-2026 -p 7687:7687 neo4j:5.26-community
export NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=ci-graph-pw-2026

uv run python scripts/ingest_affiliation_sources.py --purge        # 受控种子语料
uv run python scripts/eval_acceptance.py --live \
  --criteria c2_a_hidden_relation_recall,c2_b_false_positive_rate --gate
uv run pytest -q tests/test_eval_ci_gate.py                        # 11 条
```
