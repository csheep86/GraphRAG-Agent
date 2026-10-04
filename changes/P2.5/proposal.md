# P2.5 提案 —— 第 1 个真插件 + 变体骨架（DR-A1 / DR-A2 / DR-A3 + G-14）

| 项 | 内容 |
|---|---|
| **批次** | P2.5（原 P1-E / P1-F，2026-10-01 裁决整批推到 P2 之后） |
| **日期** | 2026-10-04 |
| **状态** | **待裁决**——本文件只做查证与建议，**未动任何代码** |
| **任务清单出处** | `changes/P1/tasks.md` 第 185-191 行（E1 / E2 / E3 / F 四项） |
| **执行顺序出处** | `changes/P2/tasks.md` 第 9-12 行（P2-B → **P2.5** → P3 → P2-C → P4 → P5 → P6） |

---

## 0. 起跑状态（**实测**，非引用文档）

| 项 | 实测结果 |
|---|---|
| `plugins/` | **不存在**（`Test-Path` = False） |
| `deploy/variants/` | **不存在**（`deploy/` 下只有 `docker-compose.yml` + `README.md`） |
| `contracts/plugins/` | **不存在** |
| `pytest` | 850 passed / 3 skipped / **6 xfailed** |
| 6 条 xfailed 分布 | G-10（T2 并发）、G-12（variant 矩阵）、G-14（客户标识来源）、G-22（插件来源）、G-23 ×2（License） |
| 接缝 6 实现 | `app/services/export/json_csv.py::JsonCsvExportSink`（**已存在、在册**） |
| compose 构建上下文 | `deploy/docker-compose.yml` 第 73 行：`context: ../backend` |

---

## 1. 权威口径（逐字引用，本提案不重开任何已决问题）

| 出处 | 原文要点 |
|---|---|
| **ADR-0007 §3.6** | manifest 格式：`id` / `version` / `base_version` / `class` / `seam` / `entry_point` / `config_schema` / `openapi_fragment`；示例 `entry_point: app.services.auth.ldap:LdapAuthProvider` |
| **ADR-0007 §3.1** | 插件**构建期烘焙**，客户现场无热插拔；"拼装"由**构建机**做（COPY 进镜像） |
| **ADR-0007 §3.5** | 插件分 A / B 类，**默认一律 A 类**（纯配置、不碰契约、零前端改动） |
| **ADR-0007 §3.2** | variant 只描述"启用什么"，**不含业务代码**；禁止客户分支 |
| **ADR-0004 §2.1 第 6 行** | 接缝 6 登记：`JsonCsvExportSink`（**同一个类**同时提供 json / csv），**无 HTTP 端点** |
| **ADR-0004 §3 第 4 条** | 实现集合 == 登记集合；`LdapAuthProvider` / `OaEventSink` 被**点名**为"登记外实现 = 越界" |
| **G-22 判据** | `REQUIRED_PLUGIN_FIELDS = ("id","version","entry_point","seam","base_version")`——只验**清单字段**，**不验实现代码放在哪** |
| **需求基线 §297-300** | **GA 硬门槛**：P2.5 由"推迟"改"GA 必做"，`plugins/` 必须有**第 1 个真插件**；❌ **不许为转护栏而造空壳插件** |

---

## 2. 核心决策：第 1 个真插件用哪个能力？

「必须是真插件」与「不许造空壳」两条**只有一条路能同时成立**：把**既有能力**换一种交付形态。
因此候选必须是**已存在**的实现。逐个过筛：

| 候选 | 现状 | 判定 |
|---|---|---|
| `ldap-auth`（接缝 1） | 需新增 `LdapAuthProvider`；ADR-0004 §3 第 4 条**点名**其属"登记外实现"；且 SSO/AD 归 **P2-C** | ❌ 越界 + 跨批 |
| `oa-webhook`（接缝 5） | 需新增 `OaEventSink`；同样被**点名**越界（登记集合只有 `db` + `log`） | ❌ 越界 |
| `IngestionSource`（接缝 2） | **0 实现**（ADR-0004 §3 第 6 条明写"尚无实现"） | ❌ 必是空壳，撞 GA 硬门槛 |
| `external_data`（接缝 8） | 只定 schema + 手工导入 CLI，**不建表**；插件化意味着新造能力 | ❌ 等于新造 |
| **`json-csv-export`（接缝 6）** | `JsonCsvExportSink` **已在登记集合内**、**已有真实实现**、天然 **A 类**（无端点、不碰契约） | ✅ **唯一可行** |

### 2.1 建议的 manifest（A 类，零契约影响）

```yaml
# plugins/json-csv-export/plugin.yaml
id: json-csv-export
version: 1.0.0
base_version: "1"
class: A
seam: 6
entry_point: app.services.export.json_csv:JsonCsvExportSink
config_schema: null      # A 类暂不驱动动态表单（DR-A5 已降级）
openapi_fragment: null   # B 类才填（本插件不碰契约 ⇒ 契约零 diff）
```

**它不是空壳**：`entry_point` 指向**已投产**的导出实现（ADR-0004 §2.1 第 6 行在册）。
**它不是新造**：零新增业务代码，只是给既有能力补一份交付形态声明。

### 2.2 ✅ 先前预判的风险，经查证**不成立**（诚实更正）

我在上一轮提醒过：`check_seams.py` 的 `SCAN_DIRS = (backend/app, backend/scripts)`，
若把实现搬进 `plugins/`（仓库根）会报"缺少登记实现"。

**查证后不成立**，两条依据：

1. **ADR-0007 §3.6 的示例本身就是 `app.services.auth.ldap:LdapAuthProvider`** ⇒ 按 ADR 本意，
   实现类就住在 `app/` 里，`plugins/` 只放 manifest（+ B 类的契约片段 / 前端）；
2. 本方案**不搬代码**（`entry_point` 指向既有的 `app/services/export/json_csv.py`）
   ⇒ 判据 1（实现集合）与判据 4（登记表一致）**都不受影响**。

---

## 3. 查证中发现的**两个真坑**（都必须处置，否则 E1/E2/E3 做不下去）

### ⛔ 坑 1 —— 变体命名与 G-14 判据**结构性冲突**

需求基线 §300 要求变体来源 = **「demo（内部演示）+ default（基线）」**两个真实部署形态。
但 `test_guardrails_delivery.py::_customer_tokens()`（第 40-41 行）取的是
**变体文件名的 `path.stem`**，再对契约文本做**子串**匹配：

```python
tokens[path.stem] = f"变体文件名 {path.name}"      # "default" / "demo" 直接进黑名单
...
hits = {token: src for token, src in tokens.items() if token and token in text}
```

**实测基座契约词频**：`default` = **10 次**、`demo` = **3 次**（都是 OpenAPI schema 的
关键字 / 示例，跟客户毫无关系）。

⇒ **照文档命名 `default.yaml` / `demo.yaml`，G-14 立刻假红**，且是**结构性**的，不是偶发。
⇒ 且 `internal-demo` 含子串 `demo`，**同样假红**，改名救不了。

**处置选项**：

| 选项 | 做法 | 代价 |
|---|---|---|
| **A（我建议）** | 变体命名为 **`baseline`**（实测契约中 **0 次**），并在本提案与日志中**追加登记**"为何不用 default / demo" | 零改动护栏；与文档 §300 的**字面**命名有出入，须登记理由（守 R5：追加不删改） |
| B | 改 `_customer_tokens`：不再取 `path.stem`，只取 `customer` / `customer_id` / `name` / `id` 字段值 | **动护栏判据**——本仓一贯倾向"护栏能不改就不改"，且需论证改窄后仍拦得住 |
| C | 照文档命名并接受假红，靠人工解释 | ❌ 不可接受：假红会逼人去删契约里的 `default`，那是真破坏 |

### ⛔ 坑 2 —— E3 的 `COPY` **拿不到** `plugins/`

`PLUGIN_ROOT = 仓库根/plugins`（`test_guardrails_delivery.py` 第 23 行），
而 compose 第 73 行写的是 `context: ../backend` ⇒ **构建上下文 = `backend/`**
⇒ Dockerfile 里 `COPY plugins ./plugins` **无源，构建直接失败**。

**处置选项**：

| 选项 | 做法 | 代价 |
|---|---|---|
| **A（我建议）** | 把 backend 的 `build.context` 改为**仓库根**，`dockerfile: backend/Dockerfile`，Dockerfile 内 COPY 路径加 `backend/` 前缀 | 动 compose；须确认不影响 G-19（它只查 `image:` 与 tag，不查 build.context） |
| B | 把 `PLUGIN_ROOT` 改到 `backend/plugins` | 动测试常量（动护栏），且与 `VARIANT_DIR`（仓库根）不对称 |
| C | **本批不做 E3**：只落 manifest + variant，构建期 COPY 随"deploy 侧构建流程"一起做 | 与 G-12 现状一致（它本就等构建流程）；但 E3 会继续挂着 |

---

## 4. 范围（待裁决后填进 `tasks.md`）

| # | 项 | 依赖裁决 | 出口 |
|---|---|---|---|
| **E1 / DR-A2** | `plugins/json-csv-export/plugin.yaml` | 待裁 1 | `test_g22_plugin_source_exists` **转正**（xfail → 常驻） |
| **E2 / DR-A1** | `deploy/variants/baseline.yaml`（只描述启用什么，不含代码） | 待裁 2 | `test_g14_customer_token_source_exists` **转正** |
| **F / G-14** | 随首个插件并入，G-14 黑名单终于非空 | 同上 | 同上（**主断言仍恒绿属预期**，见 §6） |
| **E3 / DR-A3** | Dockerfile 构建期 COPY 插件 | 待裁 3 | 见待裁 3 |

---

## 5. Non-goals（本批**不做**）

- ❌ **不改** `contracts/openapi.yaml`（契约零 diff；插件是 A 类，不碰契约）
- ❌ **不做** B 类插件（无 `openapi_fragment`、无前端、无 `contracts/plugins/`）
- ❌ **不做**插件**运行期**动态装配（ADR-0007 §3.1 已裁决：构建期烘焙）
- ❌ **不新增**任何接缝实现 ⇒ `check_seams.py` 判据 1 / 4 **零影响**（不越界）
- ❌ **不改** ADR-0007 / ADR-0004 原文（守 R5；差异一律追加登记）
- ❌ **不做** `LdapAuthProvider` / `OaEventSink`（属 P2-C 且被点名越界）
- ❌ **不碰** G-10 / G-23（分属 P3 / P4）、不碰 RLS（P3）

---

## 6. 出口判据与**预期管理**（做完之后哪些转绿、哪些不转）

| 护栏 | 当前 | P2.5 后 |
|---|---|---|
| `test_g22_plugin_source_exists` | xfailed | ✅ **转正**（`plugins/*/plugin.yaml` 存在） |
| `test_g14_customer_token_source_exists` | xfailed | ✅ **转正**（`deploy/variants/` 存在且能提取标识） |
| `test_g12_variant_matrix_builds` | xfailed | ⚠️ **仍挂起**——启用条件写死 `≥ 2` 变体，本批只产 **1** 个，**不凑第二个** |
| G-10 / G-23 ×2 | xfailed | ⚠️ 不动（P3 / P4） |
| xfailed 总数 | **6** | **4** |

⚠️ **易误读的一点**：`test_g14_base_contract_has_no_customer_specific_fields`
（G-14 的**主断言**）在 P2.5 之后**仍然恒绿**，因为基座契约里本来就没有 `baseline` 字样。
**这是预期，不是缺陷**——它的职责是"客户标识一旦泄进契约就红"，平时就该绿。
真正证明"这条不是从没生效过"的，是转正常驻的**守卫**那条（`source_exists`）。

---

## 7. ⛔ 待裁三项（请逐条拍板）

| # | 问题 | 我的建议 | 理由 |
|---|---|---|---|
| **1** | 第 1 个真插件 = `json-csv-export`（接缝 6 `JsonCsvExportSink`）？ | ✅ **是** | 五个候选里**唯一**"已在登记集合 + 已有真实实现 + A 类"⇒ 不越界、不是空壳 |
| **2** | 变体命名 `baseline`（避开 `default` / `demo`）还是改 G-14 判据？ | ✅ **命名 `baseline`** | 不动护栏；契约里 `default` 10 次 / `demo` 3 次 ⇒ 照文档命名必假红 |
| **3** | E3 的 `COPY` 怎么落：改 compose context / 改 PLUGIN_ROOT / 本批不做？ | ✅ **改 compose context 为仓库根** | 插件目录在仓库根是既成事实（`PLUGIN_ROOT` 已写死）；改 context 是唯一不改护栏的解法 |

### 附带请示

**要不要新建 `changes/P2.5/` 目录**（含本 `proposal.md` + 裁决后的 `tasks.md`）？
我建议**新建**，与 P2-A / P2-B / P2-C 同构；P1 `tasks.md` 里那 4 条**搬过来并登记出处**
（P1 的历史记述**不动**，守 R5）。

---

> ⚠️ 本文件仅做查证与建议。**裁决前不动任何代码**；裁决后再写 `tasks.md` 并开工。
