# P6-F · 任务清单（解锁 C1 图谱增益）

> 对应 [`proposal.md`](./proposal.md)；边界已在 §4 Non-goals 冻结。
> **前提条件**：§5「embedding 来源」需用户拍板 ⇒ 拍板前的 T0/T2/T3 可以先做。
> 判据：`c1_graph_gain`（阈值 **10%**，provisional），当前 UNKNOWN。

## 第一步：文档

- [x] **T0.1** 写 proposal：**先订正**上一轮"只补 embedding 就能解锁 C1"的说法（还需双侧判分）
- [x] **T0.2** 登记 7 条已核实事实（含 DeepSeek `/embeddings` = 404、本机无推理服务、CLI 缺基侧判分入口）
- [x] **T0.3** 三种 embedding 来源的取舍表 + 推荐 **S-b（本地薄服务，走 HTTP 兼容端点）**
- [x] **T0.4** 把"embedding 来源"列为**唯一需用户拍板**的事项（依赖 / 重资产不擅自决定）

## 第二步：接通与护栏（不依赖外部资源也能做）

- [ ] **T2** **反向验证**（先做，因为它在补 Steiner 之前要先确认现有护栏在位）：
      把 `EVAL_EMBEDDING_BASE_URL` 指向不存在端口 ⇒ 必须 `UNKNOWN + blocked_by`，
      **不许**静默退化成关键词检索出一堆数（L10-A1 刷绿条款）+ RED 记录
- [ ] **T3** 补 CLI 缺口 **`--baseline-judgements`**（F6：现只能靠 Python API）+ 1 条测试
      ⚠️ 不许顺便加 `--judge-baseline-with-same-table`（双侧必须**两张**判分表，A1 裁决 3）

## 第三步：接通 embedding（**待拍板**）

- [ ] **T1.1** 按选定方案落 `EVAL_EMBEDDING_BASE_URL / _API_KEY / _MODEL`
      ⚠️ **不许给 `_MODEL` 编默认值**；TLS/地址写错要当场暴露，不许推迟到跑数据那天
- [ ] **T1.2** 冒烟：单次 embed 成功 + **维度固定** + 同一输入两次结果一致 + 记录模型 id / 维度

## 第四步：双侧答案与判分

- [ ] **T4.1** 生成图侧答案（14 题，`/agent/query`）+ 基线侧答案（dense top-k）
- [ ] **T4.2** 产出判分表**草稿**（按 MANIFEST 的 rubric），交用户确认
      —— A3：**脚本不自动判分**；`judged_by` 写进 provenance
- [ ] **T4.3** 核对 `pool_fingerprint` **两侧一致**（池不同 ⇒ 增益无意义）

## 第五步：出数与收尾

- [ ] **T5** 带两份判分表跑 C1 ⇒ **首个数字**；报告里核对
      `corpus_layer = L2` / 两侧 `retriever` 不同 / `comparability_error() is None`
- [ ] **T6** 集成日志：首值 + "付出什么代价"（依赖 / 费用 / 时长）+ 收尾三问
- [ ] 门禁：`uv run pytest -q`（passed **不减**，基线 **959**）／`ruff check .`／`ruff format --check .`
      ／`scripts/check_seams.py`／`scripts/export_openapi.py --check`／`scripts/check_session_drift.py`（S1–S5）

## 边界外（只登记，不动）

- H6 引用回溯 403（`no_role_assignment`）
- 制度入图器「条款数一致」自检多文档恒 FAIL
- P7-B readiness 静默 skip 盲区
- 阈值校准（属阶段 ⑤ TBD-7）
