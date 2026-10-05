# P6-F · 任务清单（解锁 C1 图谱增益）

> 对应 [`proposal.md`](./proposal.md)；边界已在 §4 Non-goals 冻结。
> **embedding 方案已拍板为 S-b**（本地薄服务 / CPU-ONNX / 不引入 torch）。
> 判据：`c1_graph_gain`（阈值 **10%**，provisional），原 UNKNOWN ⇒ **本批首次出数：0.0909**。

## 第一步：文档

- [x] **T0.1** 写 proposal：**先订正**上一轮"只补 embedding 就能出数"的说法（还需双侧判分）
- [x] **T0.2** 登记 7 条已核实事实（含 DeepSeek `/embeddings` = 404、本机无推理服务、CLI 缺基侧判分入口）
- [x] **T0.3** 三种 embedding 来源取舍表 ⇒ **已拍板 S-b**
- [x] **T0.4** 把"embedding 来源"列为**唯一需用户拍板**的事项

## 第二步：接通 embedding（S-b）

- [x] **T1.1** 写 `scripts/local_embedding_server.py`：OpenAI 兼容 `/v1/embeddings`
      + `/health`（暴露 model / dimension）⇒ 被测链路**零侵入**
- [x] **T1.2** dev-only 依赖 `fastembed`（连带 ONNX Runtime，**无 torch**）；
      首拉权重踩到两个坑并写进脚本 header：`HF_ENDPOINT=hf-mirror.com`（直连 HF 超时）
      + `HF_HUB_DISABLE_XET=1`（xet 存储未登录 401）⇒ 之后 `HF_HUB_OFFLINE=1` 即可离线起
- [x] **T1.3** 服务冒烟：3 条入 → **512 维**、两次结果**完全一致**、全已归一化、异文本 cos 0.28–0.38
- [x] **T1.4** 配 `EVAL_EMBEDDING_*` 三件套（本机 `.env`，不入版本库）⇒ 评测侧 dim=512 / n=2 ✅
- [x] **T1.5** ⚠️ 修 `check_embedding_ctx_length=False` —— 默认 True 时 langchain 发的是
      **token id 数组**而非字符串 ⇒ 本地服务 `422`；关掉还顺带消除"超长被静默跳过"
      导致的**批次错位**（跟 sortorder chunk 按位置对齐）

## 第三步：护栏（**先于功能**）

- [x] **T2** **反向验证**：`EVAL_EMBEDDING_BASE_URL` 指向不存在端口 ⇒
      `value=None / INDETERMINATE`，`blocked_by` 明写 `APIConnectionError` ⇒
      **没有退化成关键词出一堆数**，也没假装 PASS ⇒ L10-A1 刷绿条款在位
- [x] **T3.1** 补 CLI 缺口 `--baseline-judgements`（原只能靠 Python API）
- [x] **T3.2** 加守卫 `distinct_judgement_tables`：两侧指向**同一文件** ⇒ 直接报错
      （A1 裁决 3：共用一张表 = 替基线预设答案）
- [x] **T3.3** 判分文件允许 `_rubric / _judged_by / _note` 元信息键（可复核），
      **非题号键仍报错**（不许无声丢题）
- [x] **T3.4** 测试 4 条（元信息忽略 / 非法键报错 / 同源拒绝 / 异源放行）

## 第四步：双侧答案与判分

- [x] **T4.1** 让答案**可判分**：`AnswerRecord.answer_text`（原本只有 refused / citations 计数
      ⇒ 等于盲判）；`eval_graph_gain` 在缺判分时把两侧原文摊进 `awaiting_*`
- [x] **T4.2** 按 **`MANIFEST.json` 的 `rubric-v1`** 判两份独立判分表（各 14 题），
      `judged_by=architect`；⚠️ **草稿待确认**：图侧 #5 / #7 判 false，基线侧多一条 #12 false
- [x] **T4.3** 唯一变量核对：两侧 `pool.fingerprint` 同为 `e36322bb2d86865f` / size 213、
      `top_k` 同 32、`generation_model` 同 deepseek-chat、`prompt_id` 同 kg_qa_v5，
      仅 `retriever` 不同（`graph_mentions` vs `dense_top_k`）⇒ `comparability_error()=None`

## 第五步：出数与收尾

- [x] **T5** C1 **首个数字 = 0.0909**（图 12/14 vs 基线 11/14）⇒ 阈值 10% ⇒ **FAIL（provisional）**；
      `corpus_layer=**L2**`；**跑 3 遍取值完全一致**
- [x] 门禁：`pytest 963 passed`（959 → 963，+4，0 回归）／ruff OK／format OK／seams OK／契约零 diff／drift S1–S5
- [x] 集成日志：实测数字 + **3 条根因未修的缺陷** + 灵敏度警告 + 收尾三问

## 边界外（本批动了的，逐条显式登记）

- `baseline.py`：`agent._ensure_chat()` —— 产品侧根因未动，只在评测侧补装配（见日志 §5-D1）
- 其余 H6 403 / 制度入图器自检恒 FAIL / P7-B：**没碰**，只登记
