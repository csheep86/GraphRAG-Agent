# ADR-0006：License 控制与离线激活

- **状态**：Accepted（2026-09-27 裁决，**用户拍板四项**）
- **日期**：2026-09-27
- **决策者**：用户（产品 / 商业化）+ 架构（`specs/` + `docs/` 域）
- **相关**：ADR-0003（租户隔离，租户数维度依赖 `org`）、ADR-0004（接缝门禁机制，接缝 9 复用其门禁；`users` 表登记）、M5（席位数依赖 `users` 表）、**`docs/deployment-spec.md`**（离线交付，本 ADR 的前提）
- **落地版本**：**v1.7.0（Sprint 11）** —— ⚠️ **2026-10-01 重排**：`S11` 编号已废，实现编排改指 `delivery-plan.md` **P4**（DR-C1）。**正文中的 `S11` 一律读作 P4**，另有两处裁决已改，见下方重排注记。

> ### ⚠️ 2026-10-01 重排注记（**不篡改 ADR 正文，守 R5**）
>
> **1. `users` 表归属已改**（正文多处写「`users` 表 S11 才建 / 随 M5」——§26 / §214 / §229 / §248）：
> ⚠️ **`users` 表按 DR-B13 前置到 `delivery-plan.md` P2 第一步，不随 M5**。
> 它是 **SSO（DR-D9）/ RBAC（DR-B9）/ License 席位（本 ADR）**三者的**共同前置**，
> 沿用正文口径会同时阻塞 P2 与 P4。
>
> **2. License 落地阶段改 P4**（原「与 M5 同批」失效）。
>
> **3. 完成判据由护栏 G-23 机械判定**：`licenses` 表 / `LicenseProvider` / **纯 ASGI**
> `LicenseMiddleware` / 6 个 `LICENSE_*` 契约码（**§122 所列即为其清单**）/
> `GET /license/status` / `license-cli fingerprint`，外加「移除 license ⇒ 受保护端点
> 403 `LICENSE_MISSING`、**拒绝必须落审计**」。截至 2026-10-01 **全部为零代码**
> ⇒ G-23 以 `xfail` 骨架挂起：**有本篇 ADR 不等于 License 已做**。

---

## 1. 背景

产品交付形态是**企业内网本地部署，可能完全离线**（ADR-0004 §1）。商业化要求对"谁能用、能用多少、能用多久"可控 ⇒ 必须有 License 控制。

离线这一前提有三个直接后果，决定了 License 不能照抄 SaaS 做法：

| 后果 | 为什么 |
|---|---|
| **不能联网激活 / 心跳 / 远程校验** | 客户机无外网，任何"打电话回家"的设计都会直接不可用 |
| **系统时钟不可信** | 无 NTP，时钟可漂移、可被人为回拨；`not_after` 判定不能只看 `now` |
| **不能远程吊销** | 吊销只能靠"换 license 文件 + 重新签发"，是交付流程问题不是技术问题 |

**为什么现在就必须定**（与 ADR-0004 §1 同理，避免后期返工）：

1. License 校验是**中间件 + 错误码**形态，一旦散落到全部路由再加就是全量返工；
2. **席位数依赖 `users` 表**，而该表按 ADR-0004 §2.3 登记在 **S11** 才建 ⇒ License 实现与 S11 同批成本最低；
3. 绑定维度（`max_orgs` / `max_seats` / `modules`）会渗进数据模型与新建流程，**先定维度再建表**，与"表结构一旦进客户现场再加字段就要迁移"（ADR-0004 §1）是同一条纪律。

---

## 2. 决策

**用户 2026-09-27 拍板四项**（本 ADR 的不可协商前提）：

| # | 决策项 | 拍板结果 |
|---|---|---|
| 1 | 激活方式 | **机器指纹 → 签发 license 文件**（离线签发，非联网激活） |
| 2 | 绑定维度 | **组合**（租户数 + 席位数 + 功能模块 + 有效期，四者同时生效） |
| 3 | 超限行为 | **拒绝** |
| 4 | 校验点 | **每个请求均校验** |

以下 §2.1 ~ §2.8 是这四项的执行化设计。

### 2.1 机器指纹（Machine Fingerprint）

| 项 | 规则 |
|---|---|
| 采集源 | ① OS 机器标识（Linux `/etc/machine-id`、Windows 注册表 `MachineGuid`）② 主板 / CPU 稳定标识 ③ **主网卡 MAC**（取排序后第一个非回环、非虚拟网卡） |
| 归一化 | 各组件小写、去分隔符 → **排序拼接** → 加 salt → `SHA-256` → 截断 **32 位 hex** |
| salt | `LICENSE_FP_SALT`（应用级，同一客户/同一版本一致，**不是密钥**） |
| **漂移容忍** | **组件交集 ≥ 2/3 视为同一台机器**（换网卡 / 改主机名 / 重装 OS 不误拒） |
| 禁止采集 | **IP 地址**（易变）、**磁盘序列号**（云主机/虚拟盘易变）、**任何个人信息**（合规） |
| 虚拟化 / 容器 | 指纹取宿主可见的稳定信息；确无法稳定时允许 `LICENSE_FP_OVERRIDE` 显式覆盖（**必须落审计** `license.fp_override`） |
| 对外输出 | `license-cli fingerprint` 命令 → 输出指纹 + 组件明细（供客户核对，便于"换了网卡要不要重签"的判断） |

### 2.2 license 文件（离线签发）

- **形态**：`*.lic`，UTF-8 JSON 正文 + **detached Ed25519 签名**（base64，正文与签名分离，便于人读与归档）。
- **字段**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `license_id` | STRING | 是 | License 唯一标识（UUID） |
| `schema_version` | INT | 是 | 文件结构版本（**新增字段只能追加，禁止改语义**） |
| `product` | STRING | 是 | 产品标识（防跨产品串用） |
| `customer` | STRING | 是 | 客户名（展示用，不参与校验） |
| `fingerprint` | STRING | 是 | 机器指纹（§2.1） |
| `issued_at` | ISO8601 | 是 | 签发时间 |
| `not_before` / `not_after` | ISO8601 | 是 | 有效期（§2.4 维度 4） |
| `grace_days` | INT | 否 | 过期宽限天数，默认 **30**（TBD-L2） |
| `limits.max_orgs` | INT | 是 | 租户数上限（§2.4 维度 1） |
| `limits.max_seats` | INT | 是 | 席位数上限（§2.4 维度 2） |
| `modules` | ARRAY | 是 | 授权模块列表（§2.4 维度 3，取值见 §3.3） |
| `signature` | STRING | 是 | Ed25519 签名（base64）——**不参与**正文 JSON 的哈希计算 |

- **签发流程（全程离线）**：

```text
1. 客户装机 → 运行 license-cli fingerprint → 得到指纹（+ 组件明细）
2. 客户把指纹发给供应商（邮件 / 工单，离线渠道）
3. 供应商用【私钥】签发 .lic（含四维度 limits）
4. 供应商回传 .lic 文件
5. 客户放入 LICENSE_FILE_PATH 指向路径 → 重启 / 热加载生效
6. 系统校验：签名 → 指纹 → 有效期 → 维度（顺序固定，见 §2.6）
```

- **密钥形态**：**Ed25519 非对称**——**公钥内置**于镜像 / 代码（不是 `.env`，防随手改），**私钥只存在于签发环境**（离线机器或 KMS），**不出内网**。

### 2.3 签名与验签

- 算法：**Ed25519**（签名短、验签快、无随机数陷阱）。
- **验签失败 = License 无效**（`LICENSE_INVALID`），不做"宽松通过"。
- **TBD-L1（S11 立项时确认）**：验签库选型。判据：① 纯 `pip` / `uv` 可装；② **无原生编译依赖**（离线 wheelhouse 友好）；③ **无任何网络回调**；④ 支持 Ed25519。候选：`pynacl` / `cryptography`。**未落选前不得先写代码**。

### 2.4 绑定维度（组合，四项同时生效）

| # | 维度 | 字段 | 判定式 | 超限拒绝动作 |
|---|---|---|---|---|
| 1 | 租户数 | `limits.max_orgs` | `count(org where enabled) > max_orgs` | 拒绝**新建** org |
| 2 | 席位数 | `limits.max_seats` | `count(user where activated_at IS NOT NULL AND disabled_at IS NULL) > max_seats` | 拒绝**新建 / 启用**用户 |
| 3 | 功能模块 | `modules[]` | 请求所属模块 ∉ `modules` | 拒绝该请求（模块级 403） |
| 4 | 有效期 | `not_before` / `not_after` | `now < not_before` 或 `now > not_after + grace_days` | 见 §2.5 |

> 四者是 **AND** 关系：任一不满足即按 §2.5 拒绝。

> **席位口径（2026-09-27 定）**：席位 = **已激活且可登录**的用户（`activated_at IS NOT NULL AND disabled_at IS NULL`），**与 AD / LDAP 目录同步进来的总人数解耦**——目录同步只落「未激活」记录（`activated_at IS NULL`，**不占席位**），该用户**首次成功登录**才回填 `activated_at` 并计席位。
>
> **理由**：企业 AD 目录动辄数千人，若按目录人数计席位，License 事实上无法定价售卖，且交付时必然争议。字段登记见 ADR-0004 §2.3 `users.activated_at`（**MVP 内该字段存在但消费者只有 License 一处**，不进契约）。

### 2.5 超限 = 拒绝（分级落地）

用户拍板"超限则拒绝"。**"拒绝"的具体对象需要分级**——这是架构侧的执行裁决（**可被用户推翻**），分级如下：

| 情形 | 行为 | 理由 |
|---|---|---|
| 文件缺失 / 验签失败 / 指纹不符 | **全量拒绝**（含只读），仅 `/health` 与 `/license/status` 可访问 | 这是"有没有权用"的问题，宽松即 License 形同虚设 |
| 模块未授权（`LICENSE_MODULE_DISABLED`） | 该模块请求 **403** | 同上，按模块收费的兑现点 |
| **租户数 / 席位数超限** | **拒绝"新增"动作**（新建 org / 新建或启用用户）；**已有数据与只读查询不受影响** | 超限就锁死只读 = **拿客户数据当人质**，企业客户不可接受，且必然引发交付纠纷；正确做法是"卡增量、保存量" |
| **过期** | 宽限期 `grace_days`（默认 30）内**只读**；超宽限期 → **全量拒绝** | 离线环境时钟不可信（§2.7），硬拒有误伤风险；宽限期是行业惯例 |

- **HTTP 状态码**：统一 **403**（**不用 402**——402 语义未标准化，client / 网关处理不一致）。
- **错误码**（进契约，S11 落地）：`LICENSE_MISSING` / `LICENSE_INVALID` / `LICENSE_FINGERPRINT_MISMATCH` / `LICENSE_EXPIRED` / `LICENSE_LIMIT_EXCEEDED` / `LICENSE_MODULE_DISABLED`。
- **拒绝必须留痕**：每次拒绝写 `audit_log`（`action = license.denied`，`detail` 含错误码与维度，**不含** License 正文 / 签名）。
- **禁止静默放行**：`LICENSE_ENFORCE=false` 时放行，但**必须**落 `audit_log`（`action = license.bypass`），与 ADR-0004 §3 第 5 条"合规占位不得静默无效"同款纪律。

### 2.6 每个请求均校验

- **落点**：`LicenseMiddleware`（**纯 ASGI**，与既有 `AuditMiddleware` / `RateLimitMiddleware` 同款写法）。
- **中间件顺序（固定）**：`审计 → License → 限流 → 路由`。理由：审计要能记录 License 拒绝本身；License 在限流之前，避免无效 License 消耗限流配额。
- **性能约束（关键）**：每请求**只做内存判断**，不读盘、不验签：

| 项 | 策略 |
|---|---|
| 重载时机 | ① 进程启动；② license 文件 **mtime 或内容 hash** 变化；③ 缓存 TTL 到期（默认 60s） |
| 重载动作 | 读文件 → 验签 → 解析 → 生成内存 `LicenseState`（limits / modules / 有效期 / 状态） |
| 每请求开销 | **O(1)**：有效期比较 + 模块集合 `in` + 计数比较。**S11 须实测 P95 增量 < 1ms 并登记** |
| 计数缓存 | 租户数 / 席位数**内存缓存**；启动时全量加载；**写操作（新建 org / 新建或启用用户）后失效** |

- **豁免清单**（集中声明，与限流 `EXEMPT_ROUTE_NAMES` 同款）：`/health`、`/license/status`、静态资源。**自检端点必须可访问**，否则现场无法诊断。
- **机械判据**：无有效 License 时，任意受保护端点必须返回 403 + `LICENSE_*`（测试断言，不靠人看）。

### 2.7 时钟（离线环境的真实风险）

| 问题 | 处置 |
|---|---|
| 时钟漂移 / 回拨 | 持久化 `max_seen_ts`（防重启丢失）；`now < max_seen_ts - tolerance` ⇒ 记 `license.clock_skew` **告警，不拒绝**（避免客户调时钟把自己锁死，也留下绕过痕迹） |
| 过期判定 | `now > not_after + grace_days` 才判过期；宽限期内只读 |
| 容忍度 | `LICENSE_CLOCK_SKEW_TOLERANCE_DAYS`（默认 7） |

### 2.8 不做（明确记录）

- **不做**联网激活 / 心跳 / License 服务器 / 远程吊销；
- **不做**硬件加密狗（USB dongle）；
- **不做**按用量计费（token 数 / 文档数按量结算）——本期只做**维度上限**；
- **不做** license 文件自动更新 / 自动续期；
- **不承诺防破解**：指纹可被克隆镜像或篡改绕过。**License 是合规门槛，不是安全边界**——真正的安全边界是 ADR-0003 的 RLS。这一条必须写清楚，避免销售侧按"防破解"对外承诺。

---

## 3. 数据登记（**现在只登记，不建表、不落配置**）

> 与 ADR-0004 §2.3 同款纪律：**先登记形态，落地时才建**。现在落代码即违反 ADR-0004 §3 第 5 条（无消费者的配置不得提交）。

### 3.1 `licenses` 表（**S11 建**）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | UUID | 是 | PK |
| `license_id` | TEXT | 是 | License 唯一标识（唯一索引） |
| `fingerprint` | TEXT | 是 | 本机指纹（用于回溯"这台上装过什么"） |
| `not_before` / `not_after` | TIMESTAMP | 是 | 有效期 |
| `grace_days` | INT | 是 | 宽限天数 |
| `max_orgs` / `max_seats` | INT | 是 | 维度上限 |
| `modules` | JSONB | 是 | 授权模块列表 |
| `raw_payload` | TEXT | 是 | license 正文原文（**不含签名**；审计/争议取证用） |
| `signature` | TEXT | 是 | 签名（base64） |
| `activated_at` | TIMESTAMP | 否 | 首次生效时间 |
| `status` | TEXT | 是 | `active / expired / revoked / superseded` |
| `created_at` | TIMESTAMP | 是 | - |

> **RLS 豁免声明（ADR-0003）**：`licenses` 是**实例级**表（一机一 License，无租户维度），**显式豁免 RLS**——与 `roles` 全局字典表同理。**豁免必须在代码评审中显式确认**，且该表**禁止**写入任何租户业务数据。

### 3.2 `settings.*` 配置（**S11 落地，届时每项必须有消费点**）

| 配置 | 说明 | 消费点（S11 落位） |
|---|---|---|
| `LICENSE_FILE_PATH` | license 文件路径 | `LicenseProvider` 加载器 |
| `LICENSE_PUBLIC_KEY` | Ed25519 公钥（**`.env` 可覆盖，默认内置**） | 验签 |
| `LICENSE_ENFORCE` | 强制开关；`false` 时放行但**必须**落 `license.bypass` 审计 | `LicenseMiddleware` |
| `LICENSE_FP_SALT` | 指纹 salt | 指纹计算 |
| `LICENSE_STATE_TTL_SECONDS` | 内存态 TTL，默认 60 | 重载判定 |
| `LICENSE_CLOCK_SKEW_TOLERANCE_DAYS` | 时钟回拨容忍，默认 7 | §2.7 |

> **纪律**：ADR-0004 §3 第 5 条——无消费者的配置不得提交；例外登记仅 `PRIVATE_DEPLOY_ENABLED` 与 `settings.log_export` 两项，**License 配置不得走占位**。

### 3.3 模块清单（`modules[]` 取值，与 PRD §2 对齐）

| 取值 | 对应 |
|---|---|
| `m1_ingest` | M1 文档接入与解析 |
| `m2_extract` | M2 抽取与建图 |
| `m3_graphqa` | M3 图谱问答与溯源 |
| `m4_affiliation` | M4 关联交易识别 |
| `m5_permission` | M5 权限与审计 |
| `m6_ontology` | M6 本体与增量 |
| `connectors` | **未来**：ADR-0004 接缝真实启用（HR / ERP / OA…）时才授权（TBD-L3） |

---

## 4. 接缝 9 登记（归属本 ADR，复用 ADR-0004 门禁）

| # | 接缝 | 覆盖的未来形态 | 现在预留什么（落点） | 落哪 |
|---|---|---|---|---|
| **9** | `LicenseProvider` | 不同计费形态（订阅 / 买断 / 按模块组合）——**不覆盖**任何具体客户系统 | 接口收口到 `backend/app/services/license/`；**唯一实现 `DevLicenseProvider`**——**必须真实读文件 + 校验**，`LICENSE_ENFORCE=false` 时放行但**落** `license.bypass` 审计；**禁止实现成恒 true**（那是"假做"） | **S11**（与 M5 同批，依赖 `users` 表） |

**编号归属**：接缝 9 由**本 ADR** 管辖，ADR-0004 §2.1 的"8 个接缝"**数量与编号不变**（ADR-0004 是"对外集成"，本 ADR 是"商业化约束"，性质不同，不并入）。

**门禁同步（由后端 B 执行）**：`backend/scripts/check_seams.py` 需新增登记行 `LicenseProvider → [DevLicenseProvider]`（`max_impls = 1`）。按 ADR-0004 §3 第 4 条——**先扩写本 ADR §4 登记行，再改门禁**；只改代码 → 报"登记外实现"，只改文档 → 报"未出现在登记行"，**漏任一侧 CI 必红**。

---

## 5. 与 ADR-0004 的关系

| 项 | ADR-0004（接缝 1–8） | ADR-0006（接缝 9） |
|---|---|---|
| 性质 | **对外集成**（接客户既有系统） | **商业化约束**（控制使用范围） |
| 门禁 | 共用 `check_seams.py` 与"登记表一致"判据 | 同左 |
| 纪律 | 预留必须登记、实现集合 = 登记集合、配置必须有消费者 | 同左 |
| 依赖 | — | 席位数依赖 `users` 表（ADR-0004 §2.3 已登记，S11 建） |

---

## 6. 风险

| # | 风险 | 缓解 |
|---|---|---|
| **R-L1** | 指纹漂移误拒客户（换网卡 / 重装 / VM 迁移） | 交集 ≥ 2/3 容忍（§2.1）+ 重新签发流程 + `LICENSE_FP_OVERRIDE` 兜底 + 交付侧承诺重签 SLA |
| **R-L2** | 克隆镜像 / 篡改绕过 | **不承诺防破解**（§2.8）；商业上靠合同与交付流程约束，不靠技术 |
| **R-L3** | 时钟回拨 / 漂移误判过期 | `max_seen_ts` + 宽限期 + 只告警不拒绝（§2.7） |
| **R-L4** | 每请求校验的性能 | 内存态 + TTL 重载 + O(1) 判断；**S11 实测 P95 增量 < 1ms 并登记** |
| **R-L5** | 私钥泄露 = 可任意签发 | 私钥不出签发环境（离线 / KMS），公钥内置；泄露需轮换公钥（= 发新版） |
| **R-L6** | 超限锁死客户数据引发交付纠纷 | §2.5 分级："卡增量、保存量"，租户/席位超限**不**锁只读 |

---

## 7. 排期与验收

**落地 Sprint：S11（v1.7.0）**——与 M5（`users` 表 + RBAC + RLS）同批，且部署规格（内网双轨）同批落地。

| 侧 | 内容 | 状态 |
|---|---|---|
| **文档侧** | 本 ADR + PRD **H13** + 验收矩阵 H13 行 + `sprint-calendar` S11 行与闸门 | ✅ **本次完成**（2026-09-27） |
| **实现侧（S11）** | ① `licenses` 表 + `LicenseProvider` / `DevLicenseProvider` + `LicenseMiddleware`；② `license-cli fingerprint` 命令；③ 6 个 `LICENSE_*` 错误码进契约 + `GET /license/status` 端点；④ 四维度拒绝的机械判据 | ⏳ 未开始 |
| **签发工具** | 离线签发 CLI（用私钥）——**独立仓库 / 独立工具，不入主仓**，避免私钥与代码同库 | ⏳ 未开始 |

**验收锚点**：PRD §4 **H13**。判据（S11）：无 License → 受保护端点 403 `LICENSE_MISSING`；过期 → 宽限期只读、超期 403 `LICENSE_EXPIRED`；模块未授权 → 403 `LICENSE_MODULE_DISABLED`；席位超限 → 拒绝新建用户且已有用户只读可用；每次拒绝落 `audit_log`。

---

## 8. 未决事项（TBD-L）

| # | 事项 | 建议 | 收敛时点 |
|---|---|---|---|
| **TBD-L1** | 验签库选型（Ed25519） | `pynacl` 或 `cryptography`，按 §2.3 四条判据选 | S11 立项 |
| **TBD-L2** | `grace_days` 默认值 | **30 天** | S11 立项 |
| **TBD-L3** | `connectors` 模块何时进入可售清单 | ADR-0004 某接缝**真实启用**时同步启用（不提前售卖未实现的能力） | 首个连接器落地时 |

---

## 9. 不做 vs 已做（一句话对账）

- **已做（本文档）**：四项决策执行化（指纹 / 文件格式 / 四维度 / 分级拒绝 / 每请求校验 / 时钟）、`licenses` 表 DDL 登记、接缝 9 登记、风险与排期。
- **未做（不伪装）**：**零代码**——`backend/` 无 `services/license/`、无 `LicenseMiddleware`、契约无 `LICENSE_*`；`check_seams.py` **尚未**登记接缝 9（须由后端 B 同步，见 §4）；签发工具未建。
