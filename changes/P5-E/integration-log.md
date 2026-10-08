# P5-E · 集成日志（M5 收尾：`mask(field, category)` 统一脱敏 + 「无原文落库」机械判据）

> **日期**：2026-10-08　**分支**：`main` 直推　**执行模式**：无人值守
> **上游**：[`../P5-D/integration-log.md`](../P5-D/integration-log.md)（`main` = `04836c10`，CI run `37719472362` 四 job 全绿）
> **边界**：[`proposal.md`](./proposal.md)（**11 条** Non-goals）｜**花销**：**¥0**（全程固定字符串，零 LLM 调用）
> **状态**：**已收口** —— 五笔提交在 `main`，CI **run `37723651857` 四 job 全绿**
> （pytest **1094 passed / 5 skipped / 0 failed**）

---

## 0. 一句话结论

**M5 §3 验收 3 的「统一敏感字段脱敏工具」从零命中变成了真的**：`app/core/masking.py`
提供 `mask(field, category)`，八类策略**逐字**产出 spec §4.5 示例列的形态
（`1,234,567.89` → `***,***.00`、`INV202403150001` → `INV2****0001`、
`6228123456781234` → `6228 **** **** 1234`、`13812341234` → `138****1234`、
税号 / 法人 / 身份证 → 加 `mask_salt` 的 64 位 hex、文件名 → 与 `documents.filename_hash` **同值**），
并接线到 **`audit_log.detail` 写入之前**与 **loguru JSON 出口**两处。

**判据是机械的、且对象是"跑出去的东西"而不是"函数返回值"**（决策 **D8**）：断言的是
① **已落库的 `audit_log.detail` JSON**（真 PostgreSQL，写进去再读回来）
② **运行期捕获的 loguru JSON 输出**——两者都被断言「八类原始串一个都不出现」，
且都先断言「确实写了 1 行 / 确实抓到 1 条」以免空转成恒绿（**R-9**）。

**契约零漂移**：全程 `--check` 零 diff、26 路径不变 ⇒ 决策 **D6** 的「预期零改动」成立，
**没有**触发契约同步五步。

---

## 1. 开工自检（**结论来自脚本**）

| 项 | 读数 | 与 §8 基线 |
|---|---|---|
| `check_startup_readiness.py` | **`[OK]` 17 / `[~~]` 0 / `[--]` 0**，地雷 0 项，反向守卫在 `[SG]` 区 | ✅ 一致（**动手前**跑的） |
| `check_seams.py` | **ERROR 0 / WARN 0 / OK 12**（66 个字段全部有消费者） | ✅ 一致 |
| `export_openapi.py --check` | 零漂移（26 路径） | ✅ 一致 |
| 起点 CI | run `37719472362`（P5-E 提示词落地）success | ✅ 起点绿 |

⚠️ **诚实标注**：上表第一行是**动手改代码之前**跑的；`check_seams` 与 `export_openapi`
两条是动工**之后**才补跑的（读数与基线逐位一致，且本批改动是纯增量、基线上它们是绿的由 CI
run `37719472362` 背书）⇒ 没有带着红底写代码，但这两条不是"动手前实读"。

---

## 2. T1 · `mask(field, category)` 工具 + 八类策略

新文件 `backend/app/core/masking.py`（319 行）。四条实现纪律写进了模块头：

| # | 纪律 | 为什么 |
|---|---|---|
| 1 | **类别由调用方 / 登记表显式给，代码绝不"猜"** | Non-goal 10：让代码推断"这个值像不像身份证" ⇒ 漏判方向恒为"放行"且无从追责 |
| 2 | **未登记类别一律抛 `ValueError`** | 静默返回原文 = 「以为脱敏了其实没有」，比不脱敏更危险（**P5E-4**） |
| 3 | **一律单向** | Non-goal 7：哈希加 salt 不可逆；掩码类丢掉的部分不留旁路 |
| 4 | **绝不造第三个哈希实现** | 文件名类**直接调用** `documents.hash_filename`（**D4**）；加 salt 形态照抄 `license/fingerprint.py:79` |

### 2.1 四处 spec 未写清的地方（**登记，不升级**：Non-goal 2 之外，全部落在「第 2 类升级处置顺序」可自行决定那一侧）

| # | 冲突 | 本批取法 | 理由 |
|---|---|---|---|
| **P5E-1** | 银行账号 / 电话的**策略列**写「仅保留后 4 位」，**示例列**却是 `6228 **** **** 1234` / `138****1234`（保留了前段） | 取**示例列** | 示例是 spec 里唯一给出具体形态的一侧，而批次判据 1 要求「逐字照示例」；这两个示例也正是国内通行脱敏形态（卡 BIN / 手机号段）。**若后续裁决改取策略列字面语义，只需改 `_mask_bank_account` / `_mask_phone` 两个函数** |
| **P5E-2** | 合同金额示例 `1,234,567.89` → `***,***.00` 只有两组，而输入的整数部分有三组 | 取**固定掩码**（不随量级变化） | 按组数掩码会保留**量级**（三组 = 百万级），而金额量级本身就是敏感信息；固定掩码同时逐字节等于示例 |
| **P5E-3** | 输入不足掩码所需长度（3 位银行账号、短于 8 位的发票号） | **不足即全掩码**（`****`） | 回退原文 = 泄露；抛错 = 拖垮主流程。边界形态留给后续批次裁决 |
| **P5E-4** | 未知 `category` | **抛 `ValueError`** | 见上纪律 2 |

### 2.2 陷阱表最后一条（中文形态）的实际处置

`_digits_only` 先做**全角 → 半角**（`str.translate` 的表形态），再只留 ASCII 数字
⇒ `６２２８１２３４５６７８１２３４` / `6228 1234 5678 1234` 与 `6228123456781234`
产出**同一个**掩码；身份证加空格 / 连字符也算同一个哈希。四条 variant 用例钉住
（`test_chinese_variants_are_normalized_before_masking` / `test_id_card_normalization_makes_variants_collide`）。

---

## 3. T2 · 配置 `mask_salt` + `.env.example`

| 落点 | 内容 |
|---|---|
| `app/core/config.py` | `mask_salt: str = "graphrag-mask-salt-v1"`，注释明写「**应用级 salt，不是密钥**」（ADR-0006 §2.1 同口径） |
| `backend/.env.example` | 新段，列出「哈希类三类用 salt / 掩码类五类不用 / 文件名复用既有 hash」三件事 |
| 消费者 | `masking.py::_mask_hashed` —— `get_settings().mask_salt` |

三条硬约束全部到位：`check_seams.py` 判据 2 认账（**ERROR 0 / WARN 0**）、
S3 报「已落位」、不是占位（ADR-0004 §3 第 5 条的占位清单仍只剩 `log_export` 一项，本批未动）。

---

## 4. T3 · 接线 ① `audit.py::record_audit_entry`

```python
detail=mask_mapping(detail, sensitive=sensitive) if detail is not None else None,
```

- 位置：**`session.add()` 之前**。写进去再想办法擦 = 原文已经在库里待过。
- 「自动」来自**登记表** `SENSITIVE_DETAIL_FIELDS`（17 个 key 名 → 八类之一），
  **不是**按值识别 ⇒ 与 Non-goal 10 不冲突。
- 调用方可经 `sensitive=` 显式增补 / 覆盖（二者合并，登记表不因显式指定而失效）。
- `detail=None` 仍落 `None`（`test_audit_detail_none_stays_none`）——既有调用方大量不传 detail。
- 文件头注释第 2 条「本批次不引入脱敏器（属 H5 / S11）」的**过期口径已改**，
  并补了一句新的：脱敏只认登记表里的 key 名 ⇒ **「只写结构化字段」这条纪律不因脱敏器而放宽**。

---

## 5. T4 · 接线 ② loguru JSON 出口（**为什么会走到 patcher**）

**D3 原文的处置顺序**是「优先显式调用，实测显式调用有漏才补兜底 filter」。本批的**实测**是：
全仓 `logger.bind(...)` **144+ 处**，靠每个调用点自觉调 `mask()` ⇒ 必然有漏，
且「漏埋」比「多写」更难被发现（与审计中间件 A1 决策同一条理由）。
⇒ 在 `core/logging.py::setup_logging` 里加**一行** `logger.configure(patcher=mask_log_record)`。

**为什么装全局 patcher 而不是某个 sink**：换 sink（含测试捕获 sink、未来的 OTLP sink）
不该换掉脱敏语义——「换个写法就绕过」正是这类防线的典型失效方式。这不是重写日志配置
（只有一行，原有的 sink 参数一行未动），不构成 Non-goal 9 的违反。

**诚实边界**（已写进模块头并有专门用例）：patcher **只处理 `record["extra"]`**。
日志 `message` **正文**里的原文本批不覆盖——那里要脱敏就只能"猜值"（Non-goal 10）。
`tests/test_masking.py::test_loguru_unregistered_extra_key_is_untouched` 明着断言
「未登记的 `supplier_mobile` 照样原样进日志」，就是防止这条被事后读成"全字段已脱敏"。

`core/middleware.py:106` 那句「本批次无脱敏器」的注释同步改掉了。

---

## 6. T5 · 测试（新文件 `tests/test_masking.py`，**28 条**）

| 组 | 条数 | 钉的是什么 |
|---|---|---|
| 八类登记表 + 示例列逐个对偶 | 4 + 4 | 判据 1（含全角 / 空格 variant） |
| 哈希三类 = 64 hex、variant 归一本 | 3 + 1 | 税号 / 法人 / 身份证 |
| 文件名 = `hash_filename` + **独立复算 SHA-256** | 2 | 判据 2 / 9（不复用被测实现复算，避免等式恒绿） |
| salt 真的从 settings 读到（换 salt ⇒ 换哈希） | 1 | 陷阱表第 2 条：`extra="ignore"` 会静默吃掉拼错的环境变量 |
| 短输入 / 未知类别 / 空值 | 7 | P5E-3 / P5E-4 |
| **落库判据**（真 PG，写后读回） | 3 | **判据 4** |
| **日志判据**（运行期捕获 loguru JSON） | 2 | **判据 5** + 未登记 key 的诚实边界 |

两条核心判据都**先断言非空的抓取结果**（`len(rows) == 1` / `len(sink) == 1`），
否则「没写进去」和「没抓到」都会让后面的 `not in` 恒绿（R-9）。

**测试计数对账**：CI 1066 → **1094**（**+28**），skip 5 不变、failed 0 不变 ✅ 无其它增减。

关于**本地**口径：本机跑出 `1088 passed / 11 skipped / 0 failed`，与提示词 §8 的本地基线
`1065 / 4 / 2` 有差异。`-rs` 实读的 11 条 skip 理由**全部**是 Neo4j / `TEMPORAL_TRACK_REAL_URI`
未注入（`test_eval_ci_gate` / `test_eval_corpus_a8` / `test_evidence_window_sentinel` /
`test_guardrails_graph` ×5 / `test_temporal_track_s` ×3）——本机只设了 `GRAPH_REAL_NEO4J_URI`、
没设 USER / PASSWORD ⇒ 这批真图用例改走 skip。**属本机环境口径差异，不是本批改动所致**；
判据 8 以 **CI 口径**为准不做推断。

---

## 7. 验收判据（**每条都贴了机器输出**）

| # | 判据 | 证据 |
|---|---|---|
| 1 | 八类策略逐字照 spec | 实跑：`mask("1,234,567.89", contract_amount)` = `'***,***.00'`；`'INV2****0001'`；`'6228 **** **** 1234'`；`'138****1234'`；税号 `6eadc936…5057ca01b77a55376997a6edfc7a8ec2`（64 hex）；4 条 parametrize 用例全绿 |
| 2 | 文件名 = 既有 hash | `mask("合同.pdf",'filename') == hash_filename("合同.pdf")` → `True`；另独立复算 `hashlib.sha256(name.encode('utf-8')).hexdigest()` 同值 |
| 3 | salt 可配且有消费者 | `check_seams.py` **ERROR 0 / WARN 0 / OK 12**（66 字段全部有消费者）；`check_session_drift.py` S3 = 「新增 Settings 字段均在 `.env.example` 落位」；换 salt 后哈希随之改变（用例断言） |
| 4 | **审计链路无原文（真落库）** | `test_audit_detail_persisted_without_any_original`：写含八类原文的 `detail` → commit → **用另一个 session 读回** → `json.dumps(detail)` 中八类原文**一个都不在**；并钉住 `detail["contract_amount"] == "***,***.00"` / `detail["invoice_no"] == "INV2****0001"` |
| 5 | **日志链路无原文** | `test_loguru_json_output_has_no_original`：`logger.bind(**八类原文).info(...)` → 捕获 `serialize=True` 的 JSON → 八类原文均不在；`extra.phone == "138****1234"`、`extra.filename == hash_filename(...)`、`len(extra.tax_no) == 64` |
| 6 | 契约零漂移 | `export_openapi.py --check` = 「**OK** … 与后端模型一致」，CI「契约校验」job 双绿；26 路径不变；**未触发**同步五步（D6 的预期分支） |
| 7 | 护栏不倒退 | `check_startup_readiness.py` = `[OK]` **17** / `[~~]` **0** / `[--]` **0** |
| 8 | pytest 不降 | **CI 1094 passed / 5 skipped / 0 failed**（实读 run `37723651857`，+28 全为本批新增）；既有正向守卫 `test_audit.py:103` / `test_guardrails.py:320` / `test_guardrails_compliance.py:208` **一行未改**且仍绿 |
| 9 | 既有行为未被改写 | `filename_hash` 独立复算一致；`:LegalPerson.id_hash` 未被触碰；P5-D 的出向守卫代码本批**零改动**（`app/core/egress.py` 未进入 diff） |
| 10 | CI 四 job 全绿 | ✅ **run `37723651857` / commit `b86bc954`**，`gh run watch --exit-status` = **EXIT=0** |

---

## 8. 门禁读数

| 项 | 读数 |
|---|---|
| `check_seams.py` | ERROR **0** / WARN **0** / OK **12** |
| `export_openapi.py --check` | 零漂移（26 路径） |
| `check_startup_readiness.py` | `[OK]` **17** / `[~~]` **0** / `[--]` **0** |
| `ruff check` / `ruff format --check` | All checks passed / **257** files already formatted |
| `check_session_drift.py` | **S1 读到 `changes/P5-E/proposal.md` 的 11 条**；S2 = 5 文件 / **+49 行**（未超阈值）；**S3 已落位**；S4 = 「本批未触碰契约 / 路由」（与 D6 一致）；S5 无孤独模块 |

### 8.3 ✅ CI：**run `37723651857`（commit `b86bc954`）四 job 全绿**

```
✓ 前端（lint + gen:api）      success   ESLint / tsc / gen:api
✓ 后端（ruff + pytest）       success   1094 passed, 5 skipped, 1 warning in 43.13s
✓ 契约校验（前后端漂移门禁）  success   export_openapi --check + 前端类型 git diff --exit-code
✓ 流水线汇总                   success
gh run watch 37723651857 --exit-status  => EXIT=0
```

> pytest 计数取自实读（`gh run view <id> --log | Select-String '\d+ passed'`）。
> 下一批请继续**实读**，不要抄本表的数字。

**前端**：本批**未触及** `frontend/` 任何文件（Non-goal 11），CI 的前端 job 绿是回归证明，不是本批产物。

---

## 9. 收尾三问（自答）

1. **有没有顺便做的？**
   没有。五个改动文件全部对着 §4 判据：`masking.py`（判据 1/2）、`config.py` + `.env.example`
   （判据 3）、`audit.py` + `logging.py`（判据 4/5）。**没有**碰 RLS / RBAC / 租户隔离
   （本批一次都没 import `db/rls` / `rbac`）；**没有**碰 P5-C 的 ontology 端点；**没有**碰
   P5-D 的 `egress.py`；**没有**动 `alert` 表（Non-goal 1）。
   唯一可争议的「多出」是 §5 的 patcher——但它是接线点 ② 本身（§3 三刀之第二刀），不是新增需求。
2. **有没有为躲坑而绕路的实现？**
   两处，都已登记：① **P5E-1**（银行 / 电话取示例列而非策略列字面）——绕开了"与 spec 文字冲突"
   这个难处，登记了撤回方式（改两个函数）；② **只做 `extra` 不做 `message`**——绕开了
   "必须猜值"这个 Non-goal 10 禁区，代价是留下一个已知缺口（有专门用例把缺口写成显式断言，
   让它不可能被事后读成"已覆盖"）。**没有**任何一处是为了省事而塞进去的简化。
3. **结论是真跑出来的还是读代码得出的？**
   **全部实跑**：八类 `mask()` 真机输出（§7 判据 1，逐字节贴值）、**真 PostgreSQL 写后读回**
   （判据 4）、**运行期捕获的 loguru JSON**（判据 5）、pytest 两口径、三条门禁 + ruff 两件套、
   `check_session_drift` 五条判据、**CI 四 job 全绿（run `37723651857`，exit 0）**。
   唯一"读文档得出"的是 §1 的诚实标注（哪几条是动手前跑的）。

---

## 10. 已沿用 / 新登记的决策

- **D3（接线点）**：**两处都做**，且 loguru 侧走到了 patcher —— 触发条件是原文写的
  「实测显式调用有漏」，实测依据是 `logger.bind` 144+ 处 ⇒ 理由已在本 log §5 登记。
- **D6（契约）**：**如期零改动**，`--check` 证明它没有动 ⇒ 同步五步**未触发**，符合预期分支。
- **D8（机械判据）**：**未走捷径**。判据 4 / 5 的断言对象都是"跑出去的东西"（库里 JSON / 日志输出），
  且都带非空前置断言；另用**独立复算 SHA-256** 交叉验证文件名（避免等式恒绿）。
- **P5E-1 ~ P5E-4**：新增的四条边界处置（内容见 §2.1），全部登记、未升级。
- **本批没有触发任何一类升级**：前置成立、未动 spec / ADR、未撞 Non-goal、CI 一次绿。

---

## 11. 下一批指针（**按实际结果更新，别照抄**）

1. **M6 第一批 B：`applied` 枚举 + 契约同步五步** —— 很小的一批
   （`specs/m6-ontology-incremental.md` §4.4 明写它是 `/ontology/merge` 的**前置**），
   做完可为 merge / split / rename 开路。
2. **增量重算**（m6 §3.3 验收 6）—— merge / split / rename 的第二个硬前置，**不存在**，属独立批次。
3. **`alert` 表 + 限流超阈值联动**（M5 §3 验收 5 的 P2 部分；**已连续三批**有意不做）。
4. **日志 `message` 正文的脱敏**：本批明确不覆盖（要覆盖就得猜值）。若要推进，
   正确路径是**逐个把 `mask()` 调用点补到写敏感值的日志语句上**，而不是做值识别。
5. **登记表扩表**：`SENSITIVE_DETAIL_FIELDS` 现在 17 个 key 名。新增 any 一个把敏感值写进
   `detail` / `extra` 的调用点，都应同批补一行——建议后续加一条"新增 logger.bind 的敏感语义 key 必须登记"的检查。
6. **`GET /cost/dashboard` + `cost_metrics` 表**（§3.4 验收 8 / 9），与 MVP 准入 **C3-a / C3-b** 一起做。
7. **多租户出向审计归属**：脱离「一套 compose = 一个租户」时需给 `build_chat_model` /
   `build_default_embedder` 补 org 传递（P5-D 的 X-3 撤回条件，本批**仍未触及**）。
8. **RBAC 债随端点走**：`merge` / `split` / `rename` / `/cost/dashboard` 谁实现谁同批补
   ① `require_permission` ② `PROTECTED_ENDPOINTS` 登记。
9. **D7（`question` 参与检索）/ D5（M4 完整化）/ D8**：算法活，各自单独排。

---

## 12. 不许外推（**完成本批 ≠ 以下任何一条**）

- **mask 写了 ≠ 没有泄露面**：只覆盖 **spec 点名的八类 × 两处接线点**。第九类字段、
  第三个写入路径（如 MinerU 上传的国家别的中间产物、Neo4j 节点属性）照样漏。
- **八类策略全通过 ≠ 真实语料不泄**：单测用的是**固定形态**（半角、无 OCR 错字）。
  真实抽取结果里的格式变体本批**只验了全角 / 空格两种归一**，其余不验证。
- **"无原文"断言过了 ≠ 不可还原**：哈希类加 salt 后**单向、不可逆**，但本批**不评估**
  「加 salt 后是否仍可被彩虹表撞库」，也不做可逆脱敏。
- **`mask_salt` 可配 ≠ 已做密钥管理**：它是「和 `license_fp_salt` 同款的应用级 salt」，
  **不是密钥**，不得写成"我们有加密"。
- **登记表自动脱敏 ≠ 全字段已脱敏**：只认**登记表收录的 key 名**。
  `test_loguru_unregistered_extra_key_is_untouched` 明着断言未登记 key 原样进日志——
  这条用例存在的意义就是防止上一句被读反。
- **日志 extra 已脱敏 ≠ message 正文已脱敏**：`logger.info(f"电话 {phone}")` 这类写法**照样漏**，
  本批没有覆盖，也没有任何机制阻止它。
- **M5 §3 验收 3 达成 ≠ M5 完成**：`alert` 表（验收 5 的 P2 部分）**仍在缺**。
- **契约零漂移 ≠ 功能可用**：判据只证明了"契约没被踩歪"。
- **本地 1088 绿 ≠ CI 绿 / 本机口径 ≠ 基线口径**：本机 11 条 skip 全是 Neo4j / TEMPORAL 环境未注入；
  CI 才是终裁（**R-10**）。
- **`[OK]` 17 条护栏 ≠ 全绿真实**：`check_startup_readiness.py` 自己写着「pytest 全绿 ≠ 护栏在拦」。
- ⚠️ **本批未动租户隔离路径**（预期不动，结果也确实未动：`git diff` 里没有 `db/rls.py` /
  `rbac/` / `egress.py`）⇒ 未触及 ADR-0003 §4.1 的 **T1 / T2** 两类测试；
  **下一批若碰到**，仍须带上它们并在 PostgreSQL 上执行、纳 CI 必过项、禁止标 `local_only` 绕过。
