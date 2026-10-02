# P0 · M6 spec v1.0 定稿 · 任务清单

> 与 [`proposal.md`](./proposal.md) 配套。**批次边界以 proposal §4 Non-goals 为准**。
> 每批收尾跑：`uv run python scripts/check_startup_readiness.py`，确认没有护栏被本批**意外**转绿或转红。
> 只删 xfail、测试没真通过 —— **不算转正**（行动指引第 2 条）。

**状态（2026-10-02）**：**F1 已完成**（fake + 真机各跑通，P1-5 解除）；F2 / F3 未开工。
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

- [ ] 后端 B：`app/api/` 增加 7 个端点的**骨架**，**一律返回 501 + 明确"未实现"说明**
      `POST /ontology/cold-start` / `POST /ontology/confirm` / `POST /ontology/merge` /
      `POST /ontology/split` / `POST /ontology/rename` / `GET /ontology/active` / `GET /cost/dashboard`
      - [ ] 请求 / 响应 schema 逐字照 m6 §5.5（含 `SCHEMA_VERSION_NOT_ACTIVE` 409、`FORBIDDEN` 403 跨 org）
      - [ ] ⚠️ **不写业务逻辑**（Non-goals）；占位骨架不等于实现
- [ ] 架构师：`uv run python scripts/export_openapi.py` 重导 `contracts/openapi.yaml`
- [ ] 前端 A：`npm run gen:api` 重导 TS 类型 + `git diff --exit-code` 零漂移；**只同步类型，不补业务**
- [ ] `uv run python scripts/export_openapi.py --check` ⇒ **零 diff**（契约零漂移门禁）
- [ ] 反向核对：契约路径数 **19 → 26**（原 19 + 新增 7）

## F3 — spec 升 v1.0（架构师）

逐项勾 §10 checklist（**勾完才允许改版本行**）：

- [ ] ① §4.4 与 M2 §4.5 接口对齐复核 ⇒ ✅（实测已加 `applied` 注脚；注明代码/契约侧待 M6 落地）
- [ ] ② PRD §2 / 附录 C 同步 ⇒ 实测 `03-prd.md` §2 的 M6 行是否已为「P0 / 进入 MVP」；已同步则勾，未同步则改
- [ ] ③ **删除 §7**（草案专属的口径说明，口径已收敛进 PRD）
- [ ] ④ 契约漂移核验 ⇒ 由 F2 提供证据后勾选
- [ ] ⑤ 配置项消费者核验 ⇒ **本批标注「实现时回填」**（`ONTOLOGY_LLM_SUGGEST_TIMEOUT` /
      `INCREMENT_REBUILD_BATCH_SIZE` / `COST_RATIO_ALERT_THRESHOLD` 三个配置在 M6 实现批次逐个核验，
      **无消费者的配置不得提交** —— CODEBUDDY §功能预留原则 第 6 条）
- [ ] ⑥ 版本行改写：`> **版本**：v0.1（草案…）` → `> **版本**：v1.0`；状态行去掉"草案"
- [ ] ⑦ 回填 `docs/dev-doc-status.md`：**P1-3 置 ✅** 并注明日期（**P1-4 已是 ✅、P1-5 由 F1 置 ✅**）

## F4 — C1–C3 评测方案定稿（**另立一批**，见 D3）

- [ ] 受控问题集与指标定义（图谱增益 / 召回 / 误报 / 引用覆盖 的**计算口径**）
- [ ] **TBD-7**：反证条件 F4（单位成本）阈值落 `config.py`，可经 `.env` 覆盖
- [ ] 脚本入口设计（DR-D10「评测脚本待建」）

---

## 出口判据（一句话）

`m6` 版本行 = **v1.0**、§10 checklist **七项全勾**、§7 **已删**；
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
