# P6-Z：供应商侧 License 签发工具 + **公钥注入方式的安全定案**

> **队列**：[`docs/delivery-plan.md`](../../docs/delivery-plan.md) §11 排期
> **裁决来源**：2026-10-11 用户「继续开工」
> **发现来源**：[`changes/P6-Y/proposal.md`](../P6-Y/proposal.md) §6.4 + 本批开工复核
> **判据源**：[`docs/adr/ADR-0006-license-control.md`](../../docs/adr/ADR-0006-license-control.md) **R-L5（第 262 行）** / §2.2
> **边界**：本文 §1（Non-goals **9** 条）

---

## 0. 本批做什么（三个 Z 半批）

| 半批 | 内容 | 起因 |
|---|---|---|
| **Z-a** | **纠正上一批的一处误判**：`license_cli.py` 没有签发子命令，是**刻意设计**，不是缺陷 | P6-Y §6.4 把它记成"缺失"，但 CLI 自己的 docstring（13-14 行）写明这是 ADR R-L5 的要求 |
| **Z-b** 🆕 | **F-P6Z-1 定案**：P6-Y 把公钥改成 `.env` 注入，**偏离 ADR R-L5 的「公钥内置」**，且与签发能力叠加后会削弱整套 License 管控 | 复核时发现，见 §0.2 |
| **Z-c** | 供应商侧**签发工具**（放在**不进交付镜像**的位置）+ 机械护栏 | §6.1 约束 3「换机须重新签发」这条流程目前**没有任何工具**可执行 |

### 0.1 Z-a：先更正我自己

上一批我写：

> ~~「`license_cli.py` 只有 `fingerprint` 一个子命令 ⇒ 换机重新签发缺工具支撑」~~

**这是误判**。该 CLI 的 docstring 第 13-14 行原文：

> ⚠️ **本 CLI 刻意不提供"签发"子命令**：私钥只存在于签发环境（离线机器 / KMS），
> **不出内网**（ADR-0006 §2.2 / R-L5）。把它做进交付物等于把签发能力交给客户。

⇒ 客户侧 CLI 不含签发是**正确的**；真正缺的是**供应商自己**的签发工具，
而且它必须放在**不会进交付镜像**的位置。这个区分是 Z-c 的设计前提。

### 0.2 Z-b：F-P6Z-1（本批最关键的发现）

**ADR-0006 R-L5 原文（第 262 行）**：

> | **R-L5** | 私钥泄露 = 可任意签发 | 私钥不出签发环境（离线 / KMS），**公钥内置**；泄露需轮换公钥（= 发新版） |

**P6-Y 的改动**：在交付 compose 里加了 `LICENSE_PUBLIC_KEY: ${LICENSE_PUBLIC_KEY:?…}`
（必填插值，值来自现场 `.env`）。

**冲突所在**：

| | 公钥**内置**（ADR 原意） | 公钥**可配**（P6-Y 现状） |
|---|---|---|
| 客户能否更换验签公钥 | ❌ 不能（要改代码 / 重出镜像） | ✅ **能**（改 `.env` 即可） |
| 换密钥成本 | 发新版 | 改一行配置 |
| **反盗版强度** | 强：绕 License 必须改代码 | **弱**：换公钥 + 自签 License 即可绕过 |

单看 P6-Y 那一处，危害还是"潜在"的 —— 客户手上没有签发能力。
但**叠加 Z-c 就闭环了**：

```
backend/Dockerfile:39   COPY backend/scripts ./scripts
```

⇒ **`backend/scripts/` 整个目录会进交付镜像**。若把签发工具写在这里，
客户就同时拿到「① 可替换公钥」+「② 自签能力」⇒ **机器绑定与整套 License 管控失效**。

⇒ 因此 Z-b（公钥注入方式）**必须先于 Z-c 定案**，且 Z-c 的工具位置由 Z-b 的结论约束。

### 0.2.1 实证：这套攻击**确实可行**（2026-10-11 实跑，非推断）

**攻击模型**（四步，**全程不接触我方私钥** —— 不需要偷密钥，只需要改配置）：

1. 在目标机运行 `license-cli fingerprint` ⇒ 取本机指纹（CLI 的既定用途，不是漏洞）；
2. 在自己机器上生成一对 Ed25519 密钥（`Ed25519PrivateKey.generate()`）；
3. 用自己的私钥签一份 `fingerprint == ①` 的 License（字段与 canonical 规则照抄
   `conftest.py:129-140` 那套公开写法）；
4. 把步骤②的公钥配进 `.env` 的 `LICENSE_PUBLIC_KEY`（**P6-Y 之后这是现场可配的**）。

**实测读数**（drill 环境，攻击者密钥 `q0xoPLOn…`，自签 License `license_id=11111111-…`）：

```json
{"has_license":true,"enforced":true,"code":null,"license_id":"11111111-2222-4333-8444-555555555555",
 "status":"active","in_grace":false,"not_before":"2026-10-11T00:00:00Z","not_after":"2099-12-31T00:00:00Z",
 "grace_days":30,"limits":{"max_orgs":100,"max_seats":100},
 "modules":["connectors","m1_ingest","m2_extract","m3_graphqa","m4_affiliation","m5_permission","m6_ontology"]}
```

受保护端点随之返回 **401**（缺登录凭据）而非 LICENSE 的 **403** ⇒ **License 这道闸已经被绕过去了**。

⇒ 一次性拿到：**永久有效期 + 100 租户 / 100 席位 + 全部 7 个模块**。
⇒ **结论：F-P6Z-1 属实。** 机器绑定对"能改 `.env` 的客户"而言形同虚设，
而这是 **P6-Y 引入的**（P6-Y 之前公钥缺失 ⇒ 压根验不了签，当时是"不可用"而非"可绕过"，
性质不同：一个是装不起来，一个是可以自己造一把钥匙）。

**善后**：PoC 脚本与自签 `.lic` 已删除（原本就写在 `backend/reports/delivery/`，
被 gitignore 覆盖 ⇒ **从未入库**）；`.env.drill` 中的公钥已换回开发环境那把；
drill 栈已拆 ÷ 卷已删、`graphrag-neo` 已启回、`git status` 无残留。

### 0.3 Z-c 的设计前提（已核实的机械事实）

| 事实 | 坐标 |
|---|---|
| 签发算法 | Ed25519：`public_bytes_raw()` 取公钥（base64）；canonical = `json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",",":"))`；签 `canonical.encode()` 后 base64 作为 `signature` 字段 |
| License body 字段 | `license_id` / `schema_version` / `product` / `customer` / `fingerprint` / `issued_at` / `not_before` / `not_after` / `grace_days` / `limits{max_orgs,max_seats}` / `modules[]`（签名另加 `signature`） |
| 现成参考实现 | `backend/tests/conftest.py:106-145`（**进程内临时密钥**，不入仓库、不作交付资产） |
| **`scripts/` 进镜像** | `backend/Dockerfile:39` ⇒ 签发工具**不得**放此目录 |

---

## 1. Non-goals（**9** 条 —— 改任何一条之前先按本文 §5 升级）

1. **不改验签语义、不改 License body 结构、不改 canonical 规则**
   （改任一项 = 所有已签发 License 立即失效）。
2. **不把签发能力交付给客户**：工具不得落在 `backend/scripts/`（会被
   `Dockerfile:39` COPY 进镜像），不得进 tar，不得出现在 `deploy/` 交付模板里。
3. **私钥不入仓库、不进任何交付物、不进日志**；仓库里只允许出现**用于测试的进程内临时密钥**
   （现状 `conftest.py`，保持不变）。
4. **不做 License 服务端 / 在线激活**：仍走离线渠道（客户寄指纹 → 供应商回 `.lic`）。
5. **不在客户侧 CLI 加签发子命令**（ADR R-L5 + `license_cli.py` docstring 明令）。
6. **不弱化机器绑定**：不许为了让演练变绿而给某个接口开「跳过指纹比对」的后门。
7. **不写 `docs/drills/` 任何内容、不代签任何署名**（沿用 P6-X 的红线）。
8. **不顺手改 pricing / modules 清单**：`modules[]` 取值以 `policy.py` 现有为准，本批只做签发通道。
9. **AI 不得代填判分**：Z-b 属**安全强度**取舍，必须由人裁决；我给代价测算，不给结论。

> ⚠️ 实现中若发现必须触碰某条 Non-goal ⇒ **先缩范围再报告**。

---

## 2. 决策表（**待你逐条拍板**）

| # | 决策 | 建议 |
|---|---|---|
| **Z1** ✅ | 是否开本批 | 待裁决（用户已说"继续开工"） |
| **Z2** 🚨 | **公钥注入方式**（F-P6Z-1） | 三选一，见 §2.1；**这是本批第一优先** |
| **Z3** 🆕 | 签发工具放哪 | 建议 `tools/license/`（仓库根，**不**参与任何 COPY / 打包），并配一条机械护栏断言"交付物不含签发能力" |
| **Z4** 🆕 | 私钥怎么喂给工具 | 建议：`--private-key-file <PEM path>`（默认不读环境变量，避免出现在 `env` / 日志 / shell history），密钥文件默认权限 `600` |
| **Z5** 🆕 | 是否加 `pubkey` 子命令 | 建议加：从私钥导出 base64 公钥，给"签发端↔配置端"对不上时排查用（**只输出公钥，绝不出私钥**） |
| **Z6** 🆕 | 要不要端到端正例验证 | 建议要：用工具签一份**匹配当前环境指纹**的 License ⇒ 放进容器 ⇒ `has_license=true`；这是"签发链路真的通"的唯一硬判据 |
| **Z7** 🆕 | 签发工具要不要加进 `install_acceptance` 十项 | 建议**不动**：第 9 项判据仍只认留证文件存在，不因本批而放宽 |

### 2.1 Z2 三选一（**最关键**）

| 候选 | 做法 | 收益 / 代价 |
|---|---|---|
| **A. 保持现状（`.env` 可配）** | 公钥经 `.env` 注入，客户可改 | ✅ 换密钥不用出新版 / ❌ **客户可自签绕过**（与 R-L5「公钥内置」不符），一旦 Z-c 工具泄露，防线全失 |
| **B. 回到内置** | 公钥 baked 进镜像 / 代码，移除 `LICENSE_PUBLIC_KEY` 配置项 | ✅ 符合 R-L5、客户改不了 / ❌ 换密钥必须出新版；且等于**反转 P6-Y 的 Y2 决策**（刚修好的注入通路要改回去） |
| **C. 内置为默认 + 显式开关才允许覆盖** | 默认用内置公钥；仅当显式配 `LICENSE_PUBLIC_KEY_OVERRIDE=1` 时才读外部公钥，且启动时写一条告警审计 | 兼顾；❌ 引入"第二个旋钮"，而旋钮本身是绕过面（除非配合运行时审计 + 交付文档明令生产禁用） |

> **我的诚实意见（§0.2.1 实证之后更新）**
>
> 1. P6-Y 选 `.env` 注入，是为了解决"客户照模板装就必然失效"；当时**没有**把 R-L5 的
>    「公钥内置」纳入考量 —— 是漏了一处 ADR 约束，不是有意取舍。
> 2. 实证把"潜在风险"变成了**实测可行**：四步、不用偷密钥、一次拿满额度。
>    ⇒ 选项 A 的含义随之改变 —— 它不是"接受某种弱化"，而是**接受一条已被验明的绕过路径**。
> 3. **一个反直觉的点**：**B（回到内置）顺带把 F-P6X-1 也一并解决了** —— 公钥内置就不需要
>    现场配置 ⇒ 不存在"模板漏写、客户没配、必然失效"。换言之，P6-Y 为修那个坑而增加的
>    **这一个配置项，恰恰带来了现在的安全代价**。
> 4. B 的代价（换密钥 = 重新出镜像）**ADR 本来就已经接受了**：R-L5 原文写着
>    「泄露需轮换公钥（**= 发新版**）」⇒ 这不是新增约束，而是回到原约定。
>
> ⇒ 我倾向 **B**；若确需保留"现场可换公钥"的灵活性，则退而选 **C**，并必须配套：
> 生产默认禁用覆盖 + 覆盖时写告警审计 + 交付文档明文标注后果。
> ⇒ 无论选哪个，**Z-c 的签发工具位置都必须锁死**（不许进 `backend/scripts/`）。
>
> ⚠️ **但我不替你定**：这是"要不要给现场留一把可自行更换的钥匙"的商业 / 安全取舍，
> 属 §1 第 9 条 —— 我只负责把代价算清楚、把实证摆出来。

---

## 3. 判据（机器可跑的才算完成）

| # | 判据 | 期望 |
|---|---|---|
| J1 | 签发工具产出的 `.lic` 能被现有验签路径接受 | 目标环境 `license/status` 返回 `has_license=true` |
| J2 | 工具位置不含于任何交付物 | 镜像内 `find / -name "issue*"` 无命中；tar 清单无该文件；`deploy/` 无引用 |
| J3 | 私钥不出工具进程 | 工具只接受文件路径；不写日志、不打印私钥、不进 `env` |
| J4 | **换机重签流程可执行** | 「取客户指纹 → 签发 → 放回」三步跑通（这是 §6.1 约束 3 第一次有工具支撑） |
| J5 | Z2 的选定方案已落到代码 / 配置 / 文档 | 选 A/B/C 其一并有对应实现 |
| J6 | 护栏不倒退 | 全量 pytest 0 failed；J7 契约零 diff；`install_acceptance` 十项不倒退（第 9 项仍 SKIP） |

### 3.1 实测读数（2026-10-11）

| # | 读数 |
|---|---|
| J1 ✅ | **正例**：新签发工具产出 `.lic` ⇒ 现有验签路径接受：`has_license=True` / `code=None` / `max_orgs=100` / `max_seats=100` / 7 模块 / 有效期至 2036。**全程未经任何 `.env` 公钥配置**（公钥由内置常量提供） |
| J2 ✅ | `backend/Dockerfile` 的 COPY 列表不含 `tools`；`test_signing_capability_is_not_packaged` 断言 `backend/scripts/` 无签发实现 |
| J3 ✅ | 工具签名只接受 `--private-key-file` 路径；三个子命令均不打印私钥；`test_no_private_key_material_in_repo` 断言仓库内无 `.pem` / `private*` 文件 |
| J4 ✅ | 「取指纹 → 签发 → 放回」三步跑通：本机指纹 `0d531a1f913adc481d84db4e19b703da` ⇒ 签发 ⇒ `current_state()` 立即变为 `has_license=True` |
| J5 ✅ | **Z2 已裁决为 B**：`LICENSE_PUBLIC_KEY` 配置项删除；交付 compose / 两份 `.env.example` 均已清理；ADR-0006 §3.2 加了修订记录 |
| J6 ✅ | 全量 pytest **1236 passed / 43 skipped / 0 failed**（新增 8 条护栏全绿） |

---

## 4. 任务拆分与进度（2026-10-11 收口）

| # | 任务 | 状态 |
|---|---|---|
| **T1** | Z-b：按 **Z2 = B** 把公钥改回**内置**，并把安全后果写进交付文档与 ADR | ✅ 已完成（详见 §6.1） |
| **T2** | Z-c：`tools/license/issue_license.py`（`genkey` / `issue` / `pubkey`） | ✅ 已完成 |
| **T3** | 护栏：`backend/tests/test_license_guardrails.py`（8 条静态断言） | ✅ 已完成 |
| **T4** | 端到端正例：新工具签发 ⇒ 验签路径接受 ⇒ `has_license=true` | ✅ 已完成（§3.1 J1） |
| **T5** | 回归 J6：全量 pytest + 契约 + 十项验收 | ✅ 已完成（1236 passed / 0 failed） |
| **T6** 🆕 | **私钥离线保管**（移交人） | ⏳ **待你处置** —— 见 §6.3 |
| **T7** 🆕 | 重出交付镜像 + 离线包（让本批代码改动进入客户的包） | ✅ **已完成**（经你批准，读数见 §6.4） |

---

## 5. 升级路径

出现下列任一情形 ⇒ 停下找用户，**不自行放宽**：

1. 要改验签语义 / canonical / License 结构（触 Non-goals 第 1 条）；
2. 要让私钥以任何形式进入仓库 / 镜像 / tar / 日志（触第 3 条）；
3. 要给客户侧 CLI 加签发子命令（触第 5 条，直接违反 ADR R-L5）；
4. Z2 涉及**削弱或加强反盗版强度**的最终取舍 —— **一律由人裁决**，AI 只给代价；
5. 出现"为了让某项变绿而放水"的诱惑（写留证、代署、改判据）⇒ 一律先升级。

---

## 6. 实现记录（2026-10-11）

### 6.1 Z-b：公钥回到内置（方案 B）

| 文件 | 改动 |
|---|---|
| `backend/app/services/license/public_key.py`（新增） | 内置公钥常量 `BUILTIN_LICENSE_PUBLIC_KEY_B64`；docstring 记录四步攻击与该文件不可覆盖的理由 |
| `backend/app/services/license/provider.py` | `_verify()` 改为读内置常量、**不再接收 `settings`**；**函数内 import** 是刻意的 —— 这让"换公钥"只对进程内替换模块常量生效，对环境变量 / 交付配置完全无效 |
| `backend/app/core/config.py` | 删除 `license_public_key` 字段（连 settings 层面都不再留这个面） |
| `backend/tests/conftest.py` | 测试用临时公钥改为**替换模块常量**（进程内接缝），不再经 `settings` / `env` |
| `deploy/docker-compose.delivery.yml` | 删除 `LICENSE_PUBLIC_KEY` 注入行，注释写明"刻意不注入"及其代价史 |
| `deploy/.env.example` / `backend/.env.example` | 删除该配置项；`deploy/.env.example` 改回**四项**必配，并说明 License 文件要靠供应商签发、换机须重签 |
| `deploy/README.md` | 「五项必配」→ 「四项必配（验签公钥已内置）」 |
| `docs/deployment-spec.md` | §3 必配密钥表移除该项 |
| `docs/adr/ADR-0006-license-control.md` | §3.2 表格该行标注删除，并**追加修订记录**（说明"可覆盖"为何被推翻、代价为何由 R-L5 预先接受过） |

**正向收益**：内置之后不再需要现场配置 ⇒ **F-P6X-1（模板漏配 ⇒ 必然验签失败）一并消失**。
换言之，P6-Y 为修那个坑而引入的配置项，正是这次被证伪的安全代价。

### 6.2 Z-c：签发工具

`tools/license/issue_license.py` + `tools/license/README.md`（仓库根，**不参与镜像构建**）：

- `genkey` —— 生成密钥对，私钥以 PEM 落到 `~/.graphrag-license/`（仓库之外，POSIX 下 600）；
- `issue` —— 按 `fingerprint` / `customer` / 有效期 / 额度签发；**`--fingerprint` 不允许为空**（空指纹会签出万能 License）；
- `pubkey` —— 只导出公钥 base64（任何子命令都不输出私钥）；
- canonical 规则与 `provider._verify` / `tests/conftest.py` **逐字一致**（改这里 = 所有已签发 License 失效）。

### 6.3 ⚠️ T6：私钥待你离线保管

本批生成的新密钥对：

- **公钥** `R5Q6Ab4q6cylp3RXRPBd/vbeIoCXvaOGEGdQFkiLyG4=` —— 已内置进代码，可公开；
- **私钥** `~/.graphrag-license/private.pem`（即本机 `%USERPROFILE%\.graphrag-license\private.pem`）
  —— **在仓库之外**（`test_no_private_key_material_in_repo` 保证仓库内 0 命中）；
  本机绝对路径不写在这里，免得随本文件进公开仓库。

⇒ **请你把它转移到真正的签发环境 / 密码管理器 / KMS**，并从本机删掉。
泄露 ⇒ 攻击者可签发任意 License，届时只能轮换公钥（= 发新版，重新出镜像）。

### 6.4 T7：重出交付镜像 + 离线包（2026-10-11，**经你批准**后执行）

本批改了 `provider.py` / `config.py` / 新增 `public_key.py` ⇒ 这些**都在交付镜像里**。
不重出包 ⇒ 客户拿到的镜像仍会读那个已被删除的 `settings.license_public_key`
⇒ 等价于"没有公钥" ⇒ 全部 License 验签失败、业务 403。

**`--save` ⇒ `--verify`，并对新镜像做了随机抽样**：

| 判据 | 读数 |
|---|---|
| 公钥来源**已是内置常量** | 镜像内 `public_key.BUILTIN_LICENSE_PUBLIC_KEY_B64` = `R5Q6Ab4q6cyl…` ✅ |
| **不再读 settings** | `hasattr(Settings, "license_public_key")` = **False**；`_verify` 形参 = `['body', 'signature']`（已无 `settings`）✅ |
| **签发能力未混入交付镜像** | `/app/tools` **不存在**；全 `/app` 检索 `Ed25519PrivateKey.generate` **0 命中** ✅ |
| `--verify` | **7 项全 PASS**（manifest 可解析 / app_version / tar SHA-256 / tag 与 compose 逐字节一致 / 第三方不入包 / 两枚 image id 一致） |
| 体积旁证 | tar `496,529,920` → **`496,532,480`** 字节（**+2,560**）⇒ 镜像内容确实变了 |

> ⚠️ 说明：本次**未**再起 drill 栈做端到端演练（你选的是"重出并验证"而非含演练的那一档）。
> 镜像内的公钥来源已完成抽样确认；若需"按交付物原样安装 ⇒ License 不再失效"的端到端留证，
> 属下一批范围（届时需要再停一次 `graphrag-neo`）。
