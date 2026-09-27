# Sprint 9.5 · 考勤业务域 DEMO（任务清单）

> 提案：[`proposal.md`](./proposal.md)　|　状态：待开工
> **铁律**：本清单是**唯一执行口径**；与 `specs/` / `docs/` 冲突时以本清单为准。

## 执行纪律（沿用既有）

1. **契约同步 5 步走**（`backend/CODEBUDDY.md` §3）：改 spec → Pydantic 枚举 → `export_openapi.py` → `npm run gen:api` → 契约漂移检查。**任何接口/枚举变更必须走满 5 步**。
2. **零假数据**（A15）：图谱中每个节点必须能回溯到语料的具体行/页；**禁止**硬编码演示答案。
3. **数值不出 LLM**：所有数值结论（36h / 60h / 108h / 置信度）由**规则引擎确定性计算**，LLM 只做自然语言组织。
4. **演示语料标注**：产物全程标注「演示语料（仿真）」，**不得**称为真实客户数据（R9）。

---

## 批次 A · 语料与本体（架构师 + 后端 A）

- [x] **A1** 生成仿真语料包 —— **已完成**，`demo/attendance/generate_corpus.py`（seed 固定，零第三方依赖）
  - 4 份制度文档：`policies/*.md`（源）+ `corpus/*.docx`（M1 消费，标准库手写 OOXML 转换）
  - 9 张 CSV：`corpus/{employees,attendance_records,shifts,leave_requests,overtime_records,business_trips,work_orders,location_records,access_records}.csv`
  - **5 条演示用例已埋设并通过自检**（见 `README.md` §6）
  - 制度文档含 **2025→2026 版本更替**（外勤手工补卡 → 自动补卡），用于验证 ADR-0005 时效知识
  - `README.md` 已标注「演示语料（仿真），非真实客户数据」
- [x] **A2** 建 `ontology_schemas` 表 + 考勤 schema 种子 —— **已完成**
  - 模型：`backend/app/db/models.py::OntologySchema`，字段逐字照 M6 §4.1
  - **主键取 `(org_id, version)` 复合主键**（version 每 org 独立自增），
    与其余表的 UUID 单主键惯例不同——**以 spec 为准**；索引仍以 `org_id` 打头（ADR-0003）
  - 种子：`demo/attendance/ontology_schema.json`（实体 13 类 / 关系 14 类）
  - 写入：`backend/scripts/seed_attendance_ontology.py`，**幂等**（已有 `version=1` 则 SKIP）
  - 守 M6 §3.5 验收 12：`status=active` 视同已确认，`suggested_by_llm=false`，
    `confirmed_by_user` 取 `settings.default_actor_id`
  - **不做**冷启动 GUI / 校正界面 / 增量重算（保持 S12）
- [x] **A3** CSV→图谱映射配置 —— **已完成**，`demo/attendance/mapping.yaml`
  - 12 类节点 / 11 类关系；`POLICY_CLAUSE` 归 M2 抽取，汇合关系见文件末尾（B3 消费）

## 批次 B · 数据入图（后端 A）

- [x] **B1** 实现**结构化数据入图器**（接缝 8 扩展）—— **已完成**
  `backend/scripts/ingest_attendance_csv.py`
  - 读 `mapping.yaml`，CSV 行 → Neo4j 节点/关系，**确定性映射，不用 LLM**
  - **沿用真机图谱模型**（关键修正）：节点统一 `:Entity` + `entity_type` 属性、
    关系统一 `:RELATION` + `relation_type` 属性，与 `kg/builder.py` 逐字一致。
    *初稿按"每类一个标签"设计是错的*——`graphs.py` 全部查询只读 `:Entity`，
    多标签会导致数据**进得了库、查不出来、前端渲染不出**（2026-09-26 刚因同款
    错配出过"类型列空白、节点全一个颜色"的演示事故）。`mapping.yaml` 已升 v2
  - ADR-0002 三段式写入 + **写入自检**（回读计数不符即回滚）+ **演示用例可用性验证**
  - 实测：实体 2954 / 关系 3952 / `KgVersion=active` / 重跑幂等一致（870ms）
  - **不新建表**（延续接缝 8 范围纪律）
  - **B1-fix（2026-09-27 补，重要）**：脚本原先**只写 Neo4j `:KgVersion`、未登记 PG**
    ⇒ 按「PG 才是 kg_version 真源」（S6.3 收口，`graphs.py:496-500`）读侧拿到的是
    **旧的** active 版本 `v-s71a-fe1c4dc3`，考勤图**实测 `nodes = 0`**
    （数据写进去了却查不出来 —— 与 9-26 那次演示事故**同族错配**）。
    已补 `register_pg_kg_version()`：``pending → building → ready``，同版本幂等复用。
    复测：`kg_version=attendance-demo-v1` / 实体 2954 / 关系 3952 /
    **nodes 500 / edges 529**，分类分布 EMPLOYEE·DEPARTMENT·POSITION=`org`、
    WORK_TIME_SYSTEM=`system`（本体分类同时生效）。
    ⇒ 教训已写入脚本 docstring：**入图 ≠ 可查，两边都要登记**
- [x] **B1-follow** 图例分类**域化** —— **已完成**（选型 C：`category` 进本体，**契约零改动**）
  - `demo/attendance/ontology_schema.json` 每个 `entity_type` 补 `category` 字段
  - 新增 `backend/app/services/ontology.py`：`entity_type_categories()` 读该 org 的
    active 本体；**合法值由契约枚举反推**（`get_args(GraphCategory)`，不二次硬编码）
  - `graphs.py` 新增 `_resolve_category()`：**本体优先 → 内置表 → `topic` 兜底**；
    `_load_entity_type_categories()` **每请求解析一次**（不逐节点查库），
    失败则 warn 后回落，**不阻断查询**——图例是展示增强，不是数据正确性
  - 调用点注入：`fetch_entity_detail`、`fetch_graph_overview` → `_project_overview_nodes`
  - `seed_attendance_ontology.py` 增加**真源同步**：已存在但内容不一致时按 JSON 更新
    （`version` 不变、不擅自升版）——否则幂等 SKIP 会让新字段**静默不生效**
  - 实测：13 类 = `org` 3（EMPLOYEE/DEPARTMENT/POSITION）+ `norm` 1（POLICY_CLAUSE）
    + `system` 1（WORK_TIME_SYSTEM）+ `topic` 8（各类事实记录）；
    `EMPLOYEE` 有本体= `org` / 无本体= `topic`（覆盖生效），`ORG` 仍走内置表
  - 测试：`tests/test_ontology.py` 新增 6 项全绿，既有 16 项无回归；
    `export_openapi.py --check` 零漂移；`check_seams.py` ERROR 0 / WARN 0
  - **已知边界（方案 C 固有）**：`category` 仍是契约 4 值 ⇒ 8 类事实记录共享 `topic`
    一色。要逐类型分色须走方案 B（扩枚举，动契约 + 前端色板 + `gen:api`），**本 Sprint 不做**
- [ ] **B2** 制度文档走既有 M1 解析 + M2 抽取链路，`entity_types` / `relation_types` **从 `ontology_schemas` 读**（M6 §5.2 参数化注入，**不新增 Prompt 版本**）
- [ ] **B3** 校验两链路汇合：员工节点能沿 `APPLIES_WORK_TIME` → `GOVERNED_BY` 连到 `POLICY_CLAUSE`

## 批次 C · 规则与归因（后端 B）

- [ ] **C1** 实现**确定性规则引擎**：
  - 规则值**从图谱 `POLICY_CLAUSE` 读取**，不硬编码（制度改了规则自动变）
  - 覆盖 `proposal.md` §5.3 五条规则；输出必须含**计算过程**（如「62h = 排班 6 天 × 平均 10.3h」）
- [ ] **C2** 扩展 M4（**只加不改**）：
  - `suspicion_type` **域化**（按本体域可配置，保留金融枚举不删）
  - 新增 `causes: [{reason, confidence, evidence[]}]`
  - **置信度由证据匹配度确定性加权**，**禁止** LLM 生成置信度
- [ ] **C3** 合规预警扫描端点：返回风险清单 + 图谱推理依据 + 等级 + 建议动作

## 批次 D · 问答与推理路径（后端 B）

- [ ] **D1** M3 响应新增 `reasoning_path`（`proposal.md` §5.5 结构），多跳 Cypher 补全路径返回
- [ ] **D2** 定职责边界：**规则引擎出数值 → LLM 只出措辞**；无溯源即拒答（守 F3）
- [ ] **D3** 契约同步 5 步走（`reasoning_path` / `causes` / 合规端点 / 域化枚举）

## 批次 E · 前端（前端）

- [ ] **E1** 业务域导航（对齐 `docs/demo.html` 侧栏）；非考勤域标「规划中」
- [ ] **E2** 政策问答子页：**推理路径链可视化** + 判定结论条
- [ ] **E3** 异常归因子页：用例列表 + 原因排序（含置信度条）+ 跨系统证据链
- [ ] **E4** 合规预警子页：风险清单表 + 依据 + 建议动作
- [ ] **E5** 页脚/页头标注「演示语料（仿真）」（R9）

## 批次 F · 彩排与文档（架构师）

- [ ] **F1** 彩排脚本 `demo_rehearsal.py --domain attendance`：全链路一条命令可复现，预期**全绿**
- [ ] **F2** 文档同步：`docs/03-prd.md`（业务域）、`acceptance-traceability-matrix.md`、`sprint-calendar.md`（登记 S9.5）、`dev-doc-status.md`（登记 R9~R13）
- [ ] **F3** 提交与 tag（按 §8.1 判据：tag 的树须包含 notes 声称的全部交付）

---

## 环境备注（2026-09-27 实测）

- [x] **B0-1 · 外网间歇不可达** —— **已解除**：`git push` 首次报 `Failed to connect to github.com:443`
  （DNS 抖动），**重试第二次成功**：`95eea160..85a92b32 main -> main`。
  ⇒ 后续网络操作**先重试再判定失败**。
- [x] **B0-2 · M1 解析走外网 MinerU** —— **定性为已接受的部署约束，不阻塞 B2**：
  文档解析（版面 / 表格 / OCR）与 LLM 抽取**无法本地自足**，依赖第三方是行业现实，
  **非本项目选型缺陷**。与 `docs/deployment-spec.md` 亦**不矛盾** —— 该文档要的是
  「数据不出内网」+「模型可内网、改配置即可」（§3 `PRIVATE_DEPLOY_ENABLED=true`、
  §8「模型可内网」走 ADR-0004 接缝 3，组件表更直接列了「内网 LLM / OCR：客户自备」），
  **从未要求第三方服务封装进镜像**。
  ⇒ **分阶段口径**：DEMO 阶段（本 Sprint）接受外网 MinerU / LLM，对齐 plan §3.4；
    交付阶段（v1.7.0 / S11）由客户内网等价物替换，切换位 = `parser_provider` 抽象
    —— **当前唯一实现 `mineru_cloud` 即正确的当下状态**（登记集合就该是 1，加实现须先
    扩 ADR-0004 §2.1 登记行再改门禁）。
  ⇒ **唯一需向客户明示的点**：MinerU 云是**文件本体出网**（上传至 OSS），比 LLM 文本
    出网更敏感，属**数据合规事项** —— 交付说明 / release notes 必须写明，**不得静默**。
    （`config.py:59`「内网本地解析通路未落地」的注释保留，它描述的是事实，只是不阻塞 DEMO。）

## 门禁

| 闸门 | 判据 |
|---|---|
| **CP-A1** | 仿真语料齐备且四个演示用例数据成立（批次 A 收尾） |
| **CP-A2** | 两链路数据入图成功且汇合可查（批次 B 收尾） |
| **CP-A3** | 规则引擎数值**可手工核算验证**（批次 C 收尾）——**不可核查即判定失败** |
| **CP-A4** | `demo_rehearsal.py --domain attendance` **全绿**（交付前） |

## 不做（再次划界）

其他 6 个业务域 / M6 冷启动 GUI / 校正界面 / 增量重算 / 真实客户数据 / License / RLS / RBAC / 部署 / SSO。
