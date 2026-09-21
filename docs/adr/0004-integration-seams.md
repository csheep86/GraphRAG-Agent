# ADR-0004：企业内系统集成接缝设计

- **状态**：Accepted（2026-09-21 裁决，随 v1.1.0 开发计划 v2.1 生效）
- **日期**：2026-09-21
- **决策者**：架构（`specs/` + `contracts/` 域）
- **相关**：ADR-0002（Neo4j/PG 一致性）、ADR-0003（租户隔离）、`docs/v1.1.0-demo-mvp-plan.md` §8~§9
- **落地版本**：v1.1.0（Sprint 5 批次 A2）、v1.3.0（Sprint 7 批次 B/D）、v1.4.0（Sprint 8 批次 E）

---

## 1. 背景

产品目标交付形态是**企业内网本地部署**（可能完全离线）。企业环境要求与既有系统对接，涉及身份、数据来源、模型、主数据、流程动作、输出、运维等多个方向（全景见计划文档 §9）。

关键约束：**表结构一旦落定并进入客户现场，再加字段就要做数据迁移、甚至重建索引**。因此必须在 Sprint 5 建表窗口期一次性把接缝留出来。

结论：采用**接缝式预留**——按"接缝"（而非按"系统"）预留扩展点，全部只留接口与字段，**不实现任何真实对接**。

---

## 2. 决策

采用 **8 个接缝**，成本合计 **5.5 天净增**（S5 批次 A2 2.5 天 + S7 2.5 天 + S8 0.5 天）。

### 2.1 八个接缝

| # | 接缝 | 覆盖的未来系统 | 现在预留什么（落点） | 落哪 |
|---|---|---|---|---|
| 1 | 身份接缝 `AuthProvider` | AD/LDAP、CAS、OIDC/SAML、企微钉钉扫码 | 接口收口到 `backend/app/services/auth/`，仅实现 `LocalAuthProvider`（包装现有 dev header/token 校验） | S5 批次 A2 |
| 2 | 数据接入接缝 `IngestionSource` | 共享盘 SMB/NFS、企业网盘、OA 文档库、ERP、DMS | 收口到 `backend/app/services/ingestion/`；`documents` 补 8 个可空字段（§2.2） | S5 批次 A2 |
| 3 | 模型接缝 `Provider` | 客户内网 LLM、信创模型、自备 API、统一 OCR 中台 | `parser_provider` / `llm_provider`（OpenAI 兼容），配置去 `deepseek_` 硬编码 | S5 批次 A2 |
| 4 | 流水线接缝 `EXECUTOR_REGISTRY`（**已存在**） | 客户自定义后处理、额外抽取规则 | 阶段命名规范化（`document.parse` → `document.extract` → `kg.build` → `risk.detect`，每段独立 task_type）+ `settings.pipeline_stages` 配置启停与顺序 | S5 批次 A2 |
| 5 | 事件出口接缝 `EventSink` | OA 审批流、BPM、工单/ITSM、企微钉钉通知 | `domain_events` 表 + `EventSink` 接口（仅 `db` / `log` 实现）；事件：`document.parsed` / `kg.updated` / `risk.suspect_created` / `qa.answered` | S7 批次 D |
| 6 | 数据输出接缝 `ExportSink` | 审计底稿系统、报表/BI、数据仓库、Office 插件 | 收口到 `backend/app/services/export/` + 一个 JSON/CSV 实现 | S8 批次 E |
| 7 | 实体映射接缝 `external_refs` | 内部主数据 MDM、HR 组织、工商/股权离线数据、供应商主数据 | `external_refs` 表——外来实体 ID ↔ 图谱实体 ID 的唯一映射表 | S7 批次 B |
| 8 | 外部数据导入接缝 `external_data` | 工商登记、股权结构、涉诉失信、法规/财税库**离线包** | 收口到 `backend/app/services/external_data/`；只定义导入文件 schema（JSON/CSV）+ 手工导入 CLI，**不建表** | S7 批次 B |

> 注：**可观测**（统一日志平台 / OTLP）不单列为接缝——它没有"接入方"，本质是配置开关，作为 Sprint 8 批次 E 的实施项（`settings.log_export` 开关占位）。
> 注：接缝 8 与接缝 2 语义不同——内网无法实时调工商/涉诉 API，其形式是**文件导入**而非 API 拉取。

### 2.2 `documents` 表预留字段清单（8 个，全部 nullable）

| 字段 | 用途 | 不预留的后果 |
|---|---|---|
| `source_type` | 来源类型（upload / smb / oa / erp） | 无法区分数据来源 |
| `source_ref` | 来源系统主键 | 无法回写 / 回溯 |
| `document_key` | 去重键 | 同一文件重复导入 |
| `content_hash` | 内容哈希 | 无法判定文件是否变化，增量同步无从下手 |
| `source_version` | 来源侧版本号 | 无法做增量更新 |
| `acl_scope` | 可见范围（来源系统 ACL） | 接入企业系统后无法补，只能重建索引 |
| `acl_owner_ref` | 权限主体（对应来源系统） | 同上 |
| `deleted_at` | 软删除 | 来源侧删除无法同步 |

复用已有预留：`org_id`（ADR-0003）、`storage_key`、`retry_count`、`trace_id` 已存在，无需新增。

### 2.3 未来要建的表的字段清单（现在只登记 DDL 形态，不建表）

**`users`**（Pro 阶段随 AD/LDAP 登录一起建）：

| 字段 | 说明 |
|---|---|
| `id` / `org_id` | 主键 / 租户 |
| `auth_source` | `local` / `ldap` / `oidc` |
| `external_id` | 来源系统的用户主键 |
| `display_name` | 展示名 |
| `dept_ref` | 组织架构外部引用（对接 HR / MDM） |
| `disabled_at` | 停用时间（来源侧离职同步） |

**`document_sources`**（Pro 阶段随数据接入一起建）：

| 字段 | 说明 |
|---|---|
| `id` / `org_id` | 主键 / 租户 |
| `source_type` | `smb` / `sftp` / `oa` / `erp` / `manual` |
| `connection_ref` | 连接配置引用（密钥走 `.env` / Secret，不入表） |
| `sync_mode` | `pull`（批同步）/ `push`（事件驱动） |
| `sync_cursor` | 增量水位（时间戳 / 版本号） |
| `last_synced_at` | 上次同步时间 |
| `enabled` | 启停开关 |

**`external_refs`**（Sprint 7 建表）：

| 字段 | 说明 |
|---|---|
| `object_type` | `entity` / `document` / `org` |
| `local_id` | 本系统 ID（图谱实体 ID / 文档 ID） |
| `external_system` | `mdm` / `erp` / `gsxt`（工商）/ `hr` / … |
| `external_id` | 外来 ID |
| `org_id` | 租户 |

**`domain_events`**（Sprint 7 建表）：

| 字段 | 说明 |
|---|---|
| `id` / `org_id` | 主键 / 租户 |
| `event_type` | `document.parsed` / `kg.updated` / `risk.suspect_created` / `qa.answered` |
| `aggregate_type` / `aggregate_id` | 聚合根（如 `document` / `<doc_id>`） |
| `payload` | JSON 事件体 |
| `trace_id` | 贯穿调用链 |
| `created_at` / `dispatched_at` | 产生时间 / 派发时间（本阶段恒为 NULL，只落不派） |

---

## 3. 五条硬规则

1. **预留字段一律 nullable 且不进 API 契约**（根 `CODEBUDDY.md` §功能预留原则 第 4 条）。只有真正启用某个集成时，才把对应字段提升到契约。反例警示：字段一旦进契约即成为对外承诺，改动要走完整契约流程。
2. **不做动态插件加载、不做通用连接器框架、不为未来系统写 stub**（理由见计划文档 §8.5）。
3. **新增接缝实现时，必须同步扩写本 ADR 的 §4「未来如何扩展」**——接缝的可用性靠文档维持，不靠记忆。
4. **接口实现集合 = 登记集合（不多不少）**：抽象允许有 N 个接口，但**每个接口的实现类必须恰好等于 §2.1 登记的实现集合**。Demo-MVP 阶段绝大多数为 1 个（接缝 1 仅 `LocalAuthProvider`、接缝 6 一个 JSON/CSV 实现）；**唯一例外是接缝 5 事件出口——`db` + `log` 两个本地实现**（§2.1："仅 `db` / `log` 实现"），两者都不是对外集成，而是让事件出口可观测的最小集。**出现登记集合之外的实现即越界**（如 `LdapAuthProvider` / `SmbIngestionSource` / `OaEventSink`）——那是"多做"，属 Pro / Enterprise 范围；反之少一个也是"少做"。此判据由 `backend/scripts/check_seams.py` 按接口机械执行，且**本节 §2.1 的登记行与该门禁的登记集合由 CI 强制一致**（门禁的"登记表一致"判据逐个核对第 N 行是否含登记的实现类名）。**漏改任一侧都会红**：只改代码 → 判据 1 报"登记外实现"；只改本文档 → 判据 4 报"未出现在 §2.1"。因此新增实现时**先扩写 §2.1 登记行、再改门禁**，不依赖"记得同步"。
5. **任何 `settings.*` 配置项必须能指出读取它的代码行**——无消费者的配置不得提交。这是防"**假做**"的机械判据，历史病例：`task_retry_multiplier`（声明存在，**任务退避路径从未读取**——只在 `app/services/agents.py` 作为 `exp_base` 被读）。**盲区声明**：本判据只能拦"完全无消费者"，拦不到"读它的地方不全"（B4 即后者），那类只能靠验收项兜底（计划文档附录 T11）。

> **例外登记（合规占位）**：以下配置项在 Demo-MVP 阶段为**已登记占位**，合规形态必须是"**有读取代码行 + 显式报未实现**"，禁止静默无效：`PRIVATE_DEPLOY_ENABLED`（H6 私域禁外发，计划文档 §3.4）、`settings.log_export`（可观测导出，Sprint 8 批次 E）。**除这两项外不得新增占位配置**——新增即违反第 5 条。

---

## 4. 各接缝的"未来如何扩展"

| 接缝 | 未来接入方式 | 需要新增的东西 |
|---|---|---|
| 1 身份 | 新增 `LdapAuthProvider` / `OidcAuthProvider` 实现，注册到 provider 表 | `users` 表、组织架构同步任务 |
| 2 数据接入 | 新增 `SmbIngestionSource` 等实现 + 建 `document_sources` 表 | 增量扫描任务、来源侧 ACL 同步 |
| 3 模型 | 改配置即可切内网 LLM（OpenAI 兼容） | 协议非兼容时才需新增适配器 |
| 4 流水线 | 在 `EXECUTOR_REGISTRY` 登记新阶段函数 | 阶段实现函数 + `pipeline_stages` 配置项 |
| 5 事件出口 | 新增 `WebhookEventSink` / `OaTicketEventSink` 实现 | 订阅方配置、重投递策略 |
| 6 数据输出 | 新增 `BiExportSink` / `WordReportSink` 实现 | 模板配置 |
| 7 实体映射 | 导入外部主数据 → 写 `external_refs` | 导入工具、消解策略（与 E1/E2 数据债联动） |
| 8 外部数据导入 | 扩展导入 schema 支持新数据包（新增工商/涉诉/法规类型） | 数据包格式约定、版本校验 |

---

## 5. 三个深层难题（接缝的设计依据，接入前必须解决）

1. **权限穿透**：用户提问的答案可能跨权限边界，必须在**检索层**过滤而非展示层 —— 这是 `acl_scope` / `acl_owner_ref` 存在的唯一理由（接缝 2 → 计划文档 §8.6-1）。
2. **实体消解压力随接入系统数增长**：接 1 个系统时消解简单，接 8 个系统时"同一个供应商在 ERP/OA/CLM/MDM 里是 4 个 ID"成为核心难点 —— `external_refs`（接缝 7）是接入数量的瓶颈。
3. **时效性与版本**：企业数据持续变化，用户会问"**当前**状态" —— 两级支撑：`content_hash` / `source_version`（接缝 2，判定是否需重建图）；图谱时效边 `valid_from` / `valid_to`（**本阶段不做**，登记 v1.5+）。

---

## 6. 后果

**正面**

- 未来接入企业系统不改主链路、不动已落库的客户数据；
- 连接器成为独立可交付单元（Pro / Enterprise 的收费点）。

**负面 / 风险**

- 表结构略宽（`documents` 增加 8 个长期为 NULL 的列），需靠本文档说明用途，避免后人误删；
- 存在过度设计风险（计划文档 §12 R6），通过"Sprint 5 批次 A2 净增硬顶 2.5 天 + 三个不做"约束。

**不做的事（明确记录）**

- 不实现任何真实的企业系统对接（Demo-MVP 零集成）；
- 不做联邦式实时查询（长期不做，见计划文档 §9.3）。
