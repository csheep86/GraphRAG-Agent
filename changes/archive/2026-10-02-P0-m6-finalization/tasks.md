# P0 · M6 spec v1.0 定稿 · 任务清单

> 与 [`proposal.md`](./proposal.md) 配套。**批次边界以 proposal §4 Non-goals 为准**。
> 每批收尾跑：`uv run python scripts/check_startup_readiness.py`，确认没有护栏被本批**意外**转绿或转红。
> 只删 xfail、测试没真通过 —— **不算转正**（行动指引第 2 条）。

**状态（2026-10-02）**：**F1 / F2 已完成**（P1-5 解除；契约 19 → 26 路径、零漂移）；F3 未开工。
事后实测证据与遗留记 [`integration-log.md`](./integration-log.md)（本文件是事前计划，两者不可互相替代）。

---

## F1 — schema-suggestion 端到端 PoC（P1-5 硬闸门）

> ⚠️ **必须先跑它再定稿**：PoC 不通 ⇒ spec 要改，先定稿即返工（风险 R2）。

- [x] 读 `app/services/ontology.py` 现有能力（`load_active_ontology` / `extraction_type_vocabulary` /
      `entity_type_categories`），确认**哪些已有、缺哪一段**
      ⇒ 实测：v1 参数注入**已通**（`tasks/registry.py:60`、`graphs.py:2320` 在真消费），缺的只有冷启动建议
- [x] 写最小 suggest 通路：`domain_description` → LLM 建议 `{entity_types, relation_types}` →
      **只返回建议、不落库**
      - [x] **未确认不生效**：`suggest_ontology_types` **签名里没有会话参数** ⇒ 结构上写不出
            「未确认即生效」（M6 §3.1 验收 1 / §3.5 验收 12）。⚠️ 实测修正：spec §4.1 的 `status`
            **只有 `active` / `superseded`**，本就不存在"候选"这一档，故**不做**"落候选行"
      - [x] **不阻断抽取**：取不到 active 时走内置默认 schema（既有纪律，未改动）
- [x] **可注入 fake provider**（默认路径，CI 可跑、零成本）+ **真 LLM 留证**（决策点 D1）
      ⇒ `scripts/probe_ontology_suggest.py`；实测产出 12 实体 + 12 关系类型（双双命中上限）
- [x] 端到端判据：建议结果**能被抽取链路消费**（`extraction_type_vocabulary` 取到建议的类型集），
      且**未确认前不生效** ⇒ 两条都有测试钉住
- [x] 出口：`dev-doc-status.md` **P1-5 置 ✅**（PoC 口径：跑通，非"写了一半"）
- [x] ⚠️ **差异登记**：验收 1 原文点名复用 `kg_qa_v1.md`，与"生成本体建议"语义错配
      ⇒ 本次新增 `prompts/ontology_suggest_v1.md`;**F3 定稿时必须裁决**（日志 §1.4）

## F2 — 契约先行（§5.5 的 7 个端点进契约）

> 契约由 `scripts/export_openapi.py` **从 app 导出** ⇒ 必须**先有路由骨架**（决策点 D2）。

- [x] 后端 B：`app/api/` 增加 7 个端点的**骨架**，**一律返回 501 + 明确"未实现"说明**
      `POST /ontology/cold-start` / `POST /ontology/confirm` / `POST /ontology/merge` /
      `POST /ontology/split` / `POST /ontology/rename` / `GET /ontology/active` / `GET /cost/dashboard`
      - [x] 请求 / 响应 schema 逐字照 m6 §5.5（含 `SCHEMA_VERSION_NOT_ACTIVE` 409、`FORBIDDEN` 403 跨 org）
      - [x] ⚠️ **不写业务逻辑**（Non-goals）；占位骨架不等于实现
- [x] 架构师：`uv run python scripts/export_openapi.py` 重导 `contracts/openapi.yaml`
- [x] 前端 A：`npm run gen:api` 重导 TS 类型 + `git diff --exit-code` 零漂移；**只同步类型，不补业务**
- [x] `uv run python scripts/export_openapi.py --check` ⇒ **零 diff**（契约零漂移门禁）
- [x] 反向核对：契约路径数 **19 → 26**（原 19 + 新增 7）⇒ 实测 26，7 个新路径全在

> **F2 带出的 5 个待裁决项（F3 处理，详见 `integration-log.md` §2.4）**：
> ① 501 语义冲突（项目既有口径是"基础设施不可用"）｜② 6 个响应缺 `trace_id`（spec 未列，
> 与项目惯例冲突）｜③ `split.new_entities[]` 的省略号未展开｜④ `cost.by_date[]` 每项字段未定义
> ｜⑤ 前端 mock / api 包装**未建**（无 UI 消费，补了属强行同步开发）

## F3 — spec 升 v1.0（架构师）

逐项勾 §10 checklist（**勾完才允许改版本行**）：

- [x] ① §4.4 与 M2 §4.5 接口对齐复核 ⇒ ✅ **实测**：M2 §4.5 `status` 行已写「另有 M6 前向预留值 `applied`」
      + 独立注脚（M2 阶段不落该值、口径不变、M6 落地前走契约同步 5 步）。
      ⚠️ **代码 / 契约侧未动**（`applied` 未进 Pydantic / 契约）= M6 实现批次动作，已入 spec §10.1
- [x] ② PRD §2 / 附录 C 同步 ⇒ ✅ **实测**：`03-prd.md` §2 M6 行**已是**「P0（口径修订）」（2026-09-21 改，R1 已闭环）；
      本次改的是**附录 C.0 第 5 行**（v0.1 草案 → **v1.0 定稿 2026-10-02**）+ §7 冲突登记改「已裁决」+ 头部关联规格行
- [x] ③ **删除 §7** ⇒ ✅ 草案专属的口径演化正文**已删**、结论并入 PRD §2；**编号位保留**
      （整节删会让 §8/§9/§10 错位，多处锚点指向 §10；守 `dev-doc-status.md` **R5** 编号只追加）
- [x] ④ 契约漂移核验 ⇒ ✅ 由 F2 提供证据：路径 **19 → 26**、`export_openapi.py --check` **[OK] 零 diff**、
      `gen:api` + `typecheck` + `lint` 通过
- [x] ⑤ 配置项消费者核验 ⇒ ✅ **不适用（本批不实现）**：**实测**（全仓 grep 三个配置名）确认
      三个配置（`ONTOLOGY_LLM_SUGGEST_TIMEOUT` / `INCREMENT_REBUILD_BATCH_SIZE` /
      `COST_RATIO_ALERT_THRESHOLD`）**只出现在 spec §6 与本文档，一个都没落 `config.py`**
      —— 无消费者的配置不得提交（CODEBUDDY §功能预留原则 第 6 条）。
      spec §10 已注明：勾选含义 = **本批没有违规配置项**，**不是**「三个配置已就绪」
- [x] ⑥ **接缝登记核验**（**spec §10 有此条，本文件先前漏列 —— 2026-10-02 复核补齐**）
      ⇒ ✅ **实测**：本批未引入任何 `settings.*` 字段、未新增 ADR-0004 §2.1 接缝实现类
      （只加路由 / schema / 1 个错误码）；`uv run python scripts/check_seams.py` = **ERROR 0 / WARN 0 / OK 10**
- [x] ⑦ 版本行改写 ⇒ ✅ `v0.1（草案…）` → **`v1.0`（2026-10-02 定稿）**；状态行「草案」→「**定稿**」；
      并加一句「**定稿 ≠ 已实现**」警告
- [x] ⑧ 回填 `docs/dev-doc-status.md` ⇒ ✅ **P1-3 置 ✅ 2026-10-02**（含证据路径）；
      同步 §0 汇总表（P1 已完成 2 → **4**、进行中 **1**）与 **R2 风险置「已闭环」**

> **F3 顺带裁决的 2 件事**（F1 / F2 各自登记、本批必须给结论）：
> ① **prompt 语义错配**（F1 §1.4 / PRD §7 点名）：冷启动由 `kg_qa_v1.md` → **新增 `ontology_suggest_v1.md`**，
> spec §3.1 验收 1 + §9 关联表 + PRD §7 三处同步；
> ② **F2 的 5 个待裁决项**（501 语义 / 缺 `trace_id` / split 省略号 / `by_date` 字段 / 前端 mock）
> ⇒ 裁决写入 **spec §5.5.1** 与 **§10.1**，详见 `integration-log.md` §3.2。

## F4 — C1–C3 评测方案定稿（**另立一批**，见 D3）

- [ ] 受控问题集与指标定义（图谱增益 / 召回 / 误报 / 引用覆盖 的**计算口径**）
- [ ] **TBD-7**：反证条件 F4（单位成本）阈值落 `config.py`，可经 `.env` 覆盖
- [ ] 脚本入口设计（DR-D10「评测脚本待建」）

---

## 出口判据（一句话）

`m6` 版本行 = **v1.0**、§10 checklist **八项全勾**（spec §10 实为 8 个 checkbox；本文档早前列 7 项系漏列第 ⑥ 接缝核验，已补齐）、§7 **已删**；
`dev-doc-status.md` **P1-3 / P1-5 = ✅**；契约含 **7 个 ontology/cost 端点**且 `--check` **零 diff**。

## 收尾三件套（每子任务都跑）

- `uv run pytest -q`（数字只增不减，无失败）
- `uv run ruff check .` + `uv run ruff format --check .`（**不用 Black**）
- `uv run python scripts/check_startup_readiness.py` + `scripts/check_seams.py`
- `uv run python scripts/export_openapi.py --check`（契约零漂移）
- `uv run python scripts/check_session_drift.py`（每个子任务收尾，退出码恒 0，是报告）

## Non-goals 提醒

不实现 M6 / 不改 §1~§6 实质内容 / 不动 ADR 原文 / 不做 P2-B·P2.5·P3 / 不调阈值与 prompt /
F1 只做 PoC 通路、F2 只做占位骨架。

---

## ⬛ 批次状态：**已归档（2026-10-02）**

**F1 / F2 / F3 完成**，出口判据三项达成；**F4（C1–C3 评测方案）按决策 D3 另立一批**，不在本批。
本目录已 `git mv` 至 **`changes/archive/2026-10-02-P0-m6-finalization/`**（只读沉淀，
全仓 30 处引用已同步更新，残留 **0**）。
**后续入口**：P5-M6 实现批次（照 spec §10.1 六条）与 F4 批次，详见
[`integration-log.md`](./integration-log.md) §5。
