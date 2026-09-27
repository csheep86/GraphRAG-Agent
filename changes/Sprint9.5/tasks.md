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
- [ ] **B1-follow** 考勤实体类型**尚未进** `graphs.py::_ENTITY_TYPE_TO_CATEGORY`
  ⇒ 前端 13 类节点会全部兜底成 `topic`（同色、类型列无区分）。
  需在批次 E 前补：**域化**映射（优先从 `ontology_schemas` 读，而非再硬编码一坨）
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

## 阻塞（2026-09-27 实测，需先解除才能进入批次 B）

- [x] **B0-1 · 外网间歇不可达** —— **已解除**：`git push` 首次报 `Failed to connect to github.com:443`
  （DNS 抖动），**重试第二次成功**：`95eea160..85a92b32 main -> main`。
  ⇒ 后续网络操作**先重试再判定失败**。
- [ ] **B0-2 · M1 解析依赖外网，与私有化部署冲突**：`parser_provider` 当前唯一实现为 `mineru_cloud`
  （`backend/app/core/config.py:59`，注释明写"内网本地解析通路未落地"）。
  ⇒ 而 `docs/deployment-spec.md` 刚定为**离线私有化交付**。**两者直接矛盾**，
  需在 S11 前决策：① 落本地解析通路（plan §18.4）；② 或改为"客户侧预解析后导入"。
  **本 DEMO 的制度文档链路（B2）同样受阻于此**。

## 门禁

| 闸门 | 判据 |
|---|---|
| **CP-A1** | 仿真语料齐备且四个演示用例数据成立（批次 A 收尾） |
| **CP-A2** | 两链路数据入图成功且汇合可查（批次 B 收尾） |
| **CP-A3** | 规则引擎数值**可手工核算验证**（批次 C 收尾）——**不可核查即判定失败** |
| **CP-A4** | `demo_rehearsal.py --domain attendance` **全绿**（交付前） |

## 不做（再次划界）

其他 6 个业务域 / M6 冷启动 GUI / 校正界面 / 增量重算 / 真实客户数据 / License / RLS / RBAC / 部署 / SSO。
