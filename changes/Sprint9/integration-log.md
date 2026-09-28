# Sprint 9 集成日志（证据链）

> 2026-09-28 实跑（Windows / DeepSeek 真机 / SQLite）。

## 1. 抽取侧改造（零外部依赖测试）

`tests/test_extraction_temporal.py` 8 条全过：

- v3 模板声明 `{{document_date}}`，**v2 的占位符集合未被改动**（`test_v2_is_untouched`）；
- 真实文档日期被渲染进 Prompt（`2025-06-30` 出现在 LLM 输入里）；
- **日期未知渲染为 `"unknown"`**——不代填今天（R4）；
- `valid_from` / `valid_to` 解析并进 `to_json_dict`；
- **中文日期格式 ⇒ 只丢时态字段、关系本体保留**（`test_invalid_date_drops_field_but_keeps_relation`）；
- 模型没给日期 ⇒ `None`（不解读为"今天生效"）。

连锁修正（版本升级导致旧快照断言红，属预期）：

- `test_prompt_loader`「取最大版本」改为**按可用版本集合取 max**（写死 2 ⇒ 每次升版必红，
  把语义判断退化成数字游戏）；
- `test_extraction_prompt_v1` 的产物 shape 断言补 `valid_from` / `valid_to`。

全量：**516 passed**（批次前 508），ruff check / format 全绿。

## 2. 真机探针（DeepSeek，`document_date=2026-06-30`）

输入 5 句（含成立时间 / 变更句 / 注册资本无显式日期）。结果：

| relation_type | valid_from | valid_to | 备注 |
|---|---|---|---|
| `RELATED` | 2018-03-01 | None | 动词不在枚举，降级为 RELATED（符合 v3 硬约束 2） |
| `LEGAL_REP`（张三） | 2023-04-01 | None | 与下一条构成跨期矛盾，需仲裁 |
| `LEGAL_REP`（张三） | 2023-04-01 | **2025-05-01** | **模型自行给了失效日**（见 §3） |
| `LEGAL_REP`（李四） | 2025-05-01 | None | 当前值候选 |
| `HAS_FINANCIAL_INDICATOR` | **2026-06-30** | None | 文本无显式日期 ⇒ 取 `document_date` 兜底 ✓ |

**`valid_from` 覆盖率 = 5/5 = 100%**（ADR-0005 P3-L0 判据 ≥ 90%；注：本次 **n=1**，
「稳定性」按 PoC 口径要 n≥3，留批次 B 复跑）。

## 3. 本次实测的两个发现（登记，不装看不见）

1. **模型会自己填 `valid_to`**（变更句场景给了 `2025-05-01`）。这不算违反 R4
   （日期在文本里明写），但意味着**仲裁不能依赖模型输出**：模型并非每次都给，
   遗漏时只能靠 R2 规则兜底 ⇒ 批次 B 的规则仍是必需品，不是冗余。
2. **降级边仍占一席**（`RELATED`）：`"成立于 2018 年 3 月"` 这类句子在受控枚举里
   无处安放。它是"有依据的事实"，但 `(head, relation_type)` 精确匹配仲裁
   对 `RELATED` 无能为力（不同类型无法判定矛盾）⇒ **L1 的仲裁默认只管受力点明确的
   类型**（`LEGAL_REP` / `REGISTERED_AT` 等），`RELATED` 不参与——批次 B 落实。

## 4. 批次 B（写侧 + 仲裁）：真机 Neo4j 端到端，**n=1 达 3/3**

场景：同一租户先后构建两份披露文件（doc-A 2023-04-01 法人张三 / doc-B 2025-05-01 法人李四），
策略表里 `LEGAL_REP` 配成 `single_current`。真机 Neo4j + SQLite 实跑：

| 步骤 | affiliation_edges | expired | 说明 |
|---|---|---|---|
| build v-l1-a | 1 | 0 | 首份文档，没有可比旧边 |
| build v-l1-b | 1 | **1** | 李四取代张三 ⇒ R1 封旧边 |

图谱里的最终状态：

| tail | valid_from | valid_to | source_document_id | invalidated_reason |
|---|---|---|---|---|
| 张三 | 2023-04-01 | **2025-05-01** | doc-A | **R1** |
| 李四 | 2025-05-01 | NULL | doc-B | — |

判分（ADR-0005 P3-L1 口径）：**当前值唯一 = 李四 ✓ / as-of 2024-06-01 = 张三 ✓ /
历史保留 = 2 条边活着 1 条 ✓** —— 3/3。

**注意 n=1**：CP-T2 要求 n≥3，且要求 PoC 迁入 `backend/tests/`
（批次 B2 的剩余项）。这一轮先明确：**写侧闭环已被真机证实**，
"当前值唯一"不再是纸面结论。

## 5. 批次 B 的关键发现（降级登记，不装看不见）

1. **通用 `[:RELATION]` 层做不了跨文档仲裁**——`:Entity` 的 id 是 `ent_<uuid>`，
   **每次抽取都不同**，两份文档里的同一家公司是两个节点，`(head, relation_type)`
   匹配无从谈起。要做需先有**实体消解**（属 M4 完整化，`sprint-calendar` S9 已排）。
   ⇒ 本期仲裁**只对 M4 主体层**（`sha256(name)` 稳定 id）生效，这也是价值最高的两类边
   （`LEGAL_REP` / `REGISTERED_AT`）。
2. **同一事实的多份证据必须合并**，且 `valid_from` 取**最早**：dict 直接覆盖是
   "后来者赢"，会把 2023 年披露的事实改成 2025 年的生效日——悄悄改写历史。

## 6. 批次 B2（读侧 + 收口）：**CP-T2 达成**，n=3 达 3/3

### 6.1 读侧时态视图

`graphs.py` 新增 `_temporal_view(alias)` + `validate_as_of`，**判据只有一处**，接入五条链：
概览 / 实体详情 / 全实体子图 / **共享法人** / **共享地址**；`as_of` 一路透传到 `fetch_*` 签名。

判据本身是一段字符串常量：`as_of` 为 NULL ⇒ 只看当前（`valid_to IS NULL`）；
非空 ⇒ 把视图倒回那一天。两种视图**共用同一段字符串**，
这样"默认视图"与"as-of 视图"不可能各说各话。

其中**共享法人 / 共享地址是时态视图真正生效的地方**：疑点的判据是"现在是否仍由同一人
代表"，旧法定代表人早在当年就被 R1 封了边——不过滤有效期，这条疑点会**年年报警**。

### 6.2 L0 欠账结清：答案模板

新增 `prompts/kg_qa_v3.md`（**v1 / v2 零改动**）：`{{as_of_date}}` 取自 `documents.document_date`，
v2 的 chunk 引用纪律（chunk_id 必须逐字出现在 text_chunks、F3 引用覆盖率 100%）**一条不减**。
**顺带解决了另一个问题**：批次 A 落的那列此前一直是没有消费者的预留字段，现在它是
"答案说依据截至哪天"的唯一出处；不可得时给字面量 `unknown`，不许让 LLM 自己编。

### 6.2.1 一次必须记录的操作失误（已纠正）

动手时**误把改动写进了 `prompts/kg_qa_v2.md`**——而 v2 是 Sprint 6 批次 B 的既有版本
（chunk 级引用回查），等于**原地覆盖了历史版本**，直接违反 CODEBUDDY.md
「Prompt 版本管理规范」第 2 条；更糟的是它抹掉了「chunk_id 必须逐字出自 text_chunks、
禁止伪造」这条 F3 引用的机械判据。

**没有任何一道门禁拦得住**：测试全绿、ruff 全绿、契约零漂移——因为 loader 只校验占位符，
`test_prompt_loader` 里 KG_QA_VARS 加了 `as_of_date` 之后连渲染都是绿的。
最后是靠 `git status` 里那行反常的 ` M prompts/kg_qa_v2.md`（新文件本该是 `??`）
发现的，随即从 HEAD 逐字节取回原文，改动改投 v3。

教训：**prompt 目录里的任何文件变"已修改"都应当视为红灯**——它们只允许新增，
不允许修改。这条现在写在这里，下次谁看见 `M prompts/` 就该停手。

日期查询失败降级为 `None`（不是炸掉问答）——与既有语义一致：连 QaLog 写失败都不该影响回答。

### 6.3 PoC 迁入正式测试集（`sprint-calendar` §4 CP-T2 强制项）

`temporal_poc/run_track_s.py` 的判分口径迁入 `tests/test_temporal_track_s.py`，三处改造：
**不调 LLM**（relations 的 `valid_from` 写死，要验的不是抽取）、**默认零外部依赖**
（`conftest` 刻意把 Neo4j 指到不可达端口保 CI 确定性）、**重复 3 轮**（单次成功只证明能跑）。
`temporal_poc/README.md` 顶部已注明"判据改动一律走正式测试集"，PoC 目录转为实验原迹。

真机（设 `TEMPORAL_TRACK_REAL_URI` 后同一组断言跑三轮）：

| 轮次 | 当前值 | as-of 2024-06-01 | 历史保留（总边 / 存活） |
|---|---|---|---|
| v-track-s-1 | 李四 | 张三 | 2 / 1 |
| v-track-s-2 | 李四 | 张三 | 2 / 1 |
| v-track-s-3 | 李四 | 张三 | 2 / 1 |

⇒ **3/3**。pytest 全量 516 → 544。

### 6.4 真机抓到的一个真 bug（值得单独记一笔）

`_temporal_view` 的初版第二个条件写成
`($as_of IS NULL OR valid_to IS NULL OR valid_to > $as_of)`：
`$as_of` 为 NULL 时**整个条件恒真** ⇒ 默认视图变成了"什么都查得到"，docstring 声称的
"只看当前值"与实际行为**正好相反**。表现是当前法定代表人读到 `['张三', '李四']`。

它骗过了所有单元测试（8 分钟后它们不看 Cypher 语义），也骗过了肉眼review（读起来像对的），
只有**真跑一遍 Cypher**才暴露。教训：凡是"判据"，注释声称的语义必须有一条真机断言看着。
现在这段 warning 就写在 `_temporal_view` 的 docstring 里，防止有人为了"对称"改回去。

## 7. 真机体检（CP-T2 之后的「能力是否真的接上」复核）

CP-T2 达成只证明**逻辑对**，不证明**接上了**。于是做了一次只读真机体检
（¥0、不写库、不调 LLM），结果抓到两个「表/列存在、但没人写」的洞——
这类洞的共同特点是**不报错，只安静降级**。

新增两个脚本（都幂等 / 只读优先）：

| 脚本 | 作用 |
|---|---|
| `scripts/probe_temporal_state.py` | 体检：迁移漂移 / 列落地 / 文档日期覆盖 / 策略与**仲裁判定** / 图上时态边；任一 FAIL ⇒ 退出码 1 |
| `scripts/seed_expiry_policies.py` | 初始化 `relation_expiry_policies`（幂等，已存在不覆盖） |

### 7.1 洞一：dev 库从未应用过迁移（已修）

`alembic current` **为空**，而 head 是 `4e7759c33526`——库是 `create_all` 建出来的，
`documents` 表**根本没有 `document_date` 列**（模型里却有）⇒ 读它的代码在
开发态直接 `no such column`。

**为什么没人发现**：测试用的是 `create_all` 建的**新库**（列齐全），
于是「模型与库漂移」这件事被测试天然掩盖了。

修：按不丢数据的路线对齐——`stamp 00f44b912817`（baseline 视为已应用）→
`upgrade 7989c2c821da`（补列）→ `stamp 4e7759c33526`（`relation_expiry_policies`
已由 `create_all` 建好，跳过建表）。现在 `current == head`。
体检脚本第 1 项就是这条：**库没 stamp、或版本不等于 head ⇒ FAIL**。

### 7.2 洞二：`relation_expiry_policies` 0 行 ⇒ L1 仲裁永不生效（已补）

真机：策略表 **0 行** ⇒ `load_expiry_policies` 走保守默认 `append_only`
⇒ **L1 不封任何旧边**。「法定代表人换了人，旧边被封」在真实租户下根本不会发生。

对照讽刺的一点：PoC 与 `test_temporal_track_s` 之所以 3/3，是因为它们**自己插了
策略行**——缺的从来不是逻辑，是把逻辑接上的那一步初始化。

补：`seed_expiry_policies.py` 按 ADR-0005 §6 L1 落三类行
（`LEGAL_REP` / `REGISTERED_AT` = `single_current`，`'*'` = `append_only` 兜底）。
现已写入默认租户，体检转绿且**断言的是仲裁函数本身**（`judge('LEGAL_REP') is True`），
不是数行数——数行会放过「类型名拼错」这种同样安静的失败。

### 7.3 洞三：`document_date` 全库 0 条（**未修，需决策**）

`documents` 13 条，**`document_date` 非空 = 0**。连锁后果：

- 抽取侧：`{{document_date}}` 恒渲染 `unknown` ⇒ R4 兜底源在真实数据上从未生效
  （批次 A 真机那次 5/5 覆盖，日期是**手工给**的）；
- 问答侧：`as_of_date` 恒 `unknown` ⇒ 答案模板只能说「截至日期未知」。

根因：**没有任何写入路径**。全项目只有两处**读**（`registry.py`、`agents.py`），
`backend/scripts` 里 0 处写；模型注释写的是「本期由集成侧写入，REST 上传暂不接收」。

⇒ 这是**需要拍板**的一项（涉及契约 / 前端表单，不擅自跨端做），候选方案：
甲 上传接口加可选字段（进契约 + 前端可选日期输入）；
乙 后台任务从正文/文件名解析后回填（可人工覆盖）；
丙 维持只靠集成侧导入（真实用户路径继续降级）。

### 7.4 顺带看到的一个事实

真机 active kg_version = `attendance-demo-v1`（考勤域），全库 4239 条边里
**只有 15 条带 `valid_from`**，且集中在 `LEGAL_REP` / `REGISTERED_AT` /
`HAS_FINANCIAL_INDICATOR` 这三类**披露域**类型上。⇒ 时态治理在当前演示域
几乎没有受力点：不是逻辑问题，是**域不匹配**。切换演示域或给考勤域定义
「唯一当前」的关系类型，是让这项能力可见的另一条路（同样需决策，未擅动）。

## 8. 迁移

`7989c2c821da_add_documents_document_date_adr_0005_l0.py`：autogenerate 后人工审阅，
仅一条 `add_column`，`downgrade` 对称。空库 `upgrade head` 通过，
等价性测试（`test_migrations_baseline`）自动把新列纳入比对——
这是 S9.7 纪律的第一次实战，**加列忘写迁移 ⇒ CI 必红**已被验证有效。

## 9. 洞三收口：`document_date` 的写入路径（甲 + 乙，已拍板）

§7.3 留下的三选一，拍板为**甲 + 乙组合**：人工指定优先，正文解析兜底，
认不出就留 `null`。

### 9.1 甲：上传接口的可选字段

`POST /api/v1/documents/upload` 新增可选表单字段 `document_date`（`date`、可空）。
契约由后端模型生成（`export_openapi.py`），落地后 `Body_uploadDocument` 自动带上；
前端 `npm run gen:api` 后 `api.d.ts` 出现 `document_date?: string | null`，
上传对话框加了一个**可选**日期输入（带说明：留空则由系统识别，识别不出即为空）。

**它同时是乙的覆盖开关**：解析再准也是猜，人给的值永远优先——已由
`test_extract_does_not_overwrite_explicit_date` 钉住。

### 9.2 乙：抽取执行体从正文认

新增 `app/services/parsing/document_date.py`，接入点在 `registry._do_extract`
（构造 `LangextractClient` 之前）。

两个设计约束是实测逼出来的：

1. **文件名不能用于解析**——库里只落 `filename_hash`（M5 §4.5 禁原文），
   没有文件名可解析。所以原方案里的"文件名日期"一半作废，只剩正文。
2. **只在有出处的日期才算**：正文里日期很多（成立日期、他方披露日、合同签署日…），
   只认「报告期 / 披露日期 / 签署日期 / 截止 / 截至 …」等关键词**紧跟**的日期，
   且关键词与日期之间只允许标点空白（防止跨句张冠李戴）。
   三种粒度：日（直接用）、月（取**月末**）、年（取 **12-31**，财年期末）——
   后两条是**约定**不是事实，故必须可被人工覆盖。

纪律与抽取侧 R4 同口径：**认不出返回 `None`**，不猜、不用"今天"兜底；
`2025年2月30日` 这类非法日期返回 `None` 而**不就近修正**成 2-28。

### 9.3 测试与一个顺带发现

- 解析单测 14 条（`test_document_date.py`）：重点在**什么时候必须说 None**；
- 端到端 6 条（`test_document_date_flow.py`）：上传落库、不填为 null、
  非法格式 400、正文识别回填、无出处留 None、人工值不被覆盖。

**顺带发现**：日期格式非法时接口返回 **400 而非 422**——本项目由全局异常处理器
统一转 `400 VALIDATION_ERROR`（FastAPI 默认 422 在此不成立）。测试按项目语义断言，
不按框架默认。

### 9.4 未做（明确不留尾巴）

**历史 13 份文档的 `document_date` 仍是 `null`**：甲 / 乙只对**新上传**生效，
没有做存量回填——当前不需要演示，回填属运维动作，等真要演示时按
`probe_temporal_state.py` 的红灯决定做不做。

## 10. 追加第 5 类接缝判据：Prompt 版本不可覆盖（含一处更正）

`scripts/check_seams.py` 新增判据：**`prompts/*_v{N}.md` 入库后只允许新增版本，
原地修改 / 删除一律 ERROR**（`CODEBUDDY.md`「Prompt 版本管理规范」第 2 条）。
此前这条规则只写在文档里，**没有任何机械手段执行**。

### 10.1 一处更正

我此前在对话里说"这次覆盖 `v2` 的事没有门禁拦得住"。动工前用
`git log --diff-filter=MD -- prompts/` 一查：结果**为空**——`prompts/` 全历史
只有 A（新增），从未发生过原地修改或删除。是我记错了。

这句更正已写进脚本注释，并作为该判据为什么读 git 而非人的陈述的理由
（条例可能缺记、记忆可能出错，只有 git 的事实算数）。

### 10.2 三个刻意的设计

1. **`--no-renames`**：`git mv v2 v3` 若启用重命名检测会显示为一条 R，看上去
   "不是覆盖"，实则是把历史版本的身份挪给新内容——更隐蔽。禁用后落成 D + A，
   删除那一头跑不掉。
2. **判不出来 ⇒ ERROR**：git 不可用 / 基准不可达时不放行。悄悄通过的门禁
   比没有门禁更危险。
3. **`--base` / `GITHUB_BASE_REF`**：默认 HEAD 在 CI 上是**假绿**（checkout 后
   工作区恒干净，与 HEAD 比永远是"无改动"）。故 CI 下自动取 PR 的 base，
   本地可用 `--base main` 审查已提交区间。

附带修掉一处会误导人的细节：被改写版本的"下一步该加哪个版本"不能机械 +1——
`kg_qa` 已有 v1/v2/v3 时改 v1，提示 v2 等于把人引向"再去覆盖 v2"。

### 10.3 反向验证（不只是单测绿）

真机器上给 `prompts/kg_qa_v1.md` 追加一行 ⇒ 门禁**转红、退出码 1**，消息指明
被改文件并给出该新增的版本号；随后还原（`git diff` 验证为空）。

还原有个小插曲：`Add-Content` 写入带 CRLF，删掉那行后 `git status` 仍显示 M
而 `git diff` 为空（索引 stat 陈旧 + `core.autocrlf=true`），最终用
`git show HEAD:<file>` 的字节流覆盖写回、`git add` 归一化才彻底干净。
⇒ **改文件做验证的成本比预想高**：以后这类反向验证建议用临时新文件（A 状态），
而不是动历史文件。

### 10.4 未接 CI（新的「存在但没人跑」）

仓库**没有** `.github/workflows`——`check_seams.py` / `export_openapi.py --check`
/ `pytest` 目前都只在**本机手工跑**。也就是说今天补的这条判据仍未自动执行，
与 §7 的"表响了没人写"是同一类病：

> 东西写出来了 ≠ 它在你们的流水线上跑。

是否建最小 CI（对 push/PR 跑 `check_seams` + 契约零漂移 + `pytest` + 前端
`typecheck/lint`）属仓库级配置变更，未擅自动手，待定。
