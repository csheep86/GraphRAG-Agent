# P6-Y：License 交付缺口修复（F-P6X-1）+ 跨机恢复 License 失效定案（F-P6Y-1）

> **队列**：[`docs/delivery-plan.md`](../../docs/delivery-plan.md) §11 排期
> **裁决来源**：2026-10-10 用户拍板 —— 「推吧，按你建议开吧」
> **发现来源**：[`changes/P6-D1b/integration-log.md`](../P6-D1b/integration-log.md) **§9.4**（P6-X 首炼预演实测）
> **判据源**：[`docs/deployment-spec.md`](../../docs/deployment-spec.md) §6.1 / §6.2 / §6.4 / §10
> **上一批交接**：[`changes/P6-D1b/new-session-prompt.md`](../P6-D1b/new-session-prompt.md)
> **边界**：本文 §1（Non-goals **9** 条）

---

## 0. 本批到底做什么（三个 Y 半批）

| 半批 | 内容 | 起因 |
|---|---|---|
| **Y-a** | **F-P6X-1**：把 `LICENSE_PUBLIC_KEY` 真正送进 `backend` 容器 + 现场模板给出对应说明 | 交付 compose 的 `environment:` 白名单里没有它；compose 的 `--env-file` **只插值不注入** ⇒ 客户照模板装 ⇒ License 必然验签失败、业务接口全 **403** |
| **Y-b** | **F-P6Y-1**：实跑定案「License 绑机器指纹 ⇒ 跨机恢复必然失效」 | `provider.py:211-219` 逐次比对 `compute_fingerprint()`；这让 §6.1 的 License 备份对象在 DR 语境下形同虚设 |
| **Y-d** 🆕 | **F-P6Y-2**：容器化交付下指纹 = 容器网卡 MAC，**重建容器即失效** | 实测：容器内三源只剩 MAC；`--force-recreate` 后 MAC 与 fp 双双变化 |
| **Y-c** | **F-P6X-3**：交付 README 补「图库 load 后必须 `restart neo4j`」 | `neo4j-admin database load` 后库停 offline；`neo4j start` 误报 `already running (pid:7)`；Community 版不支持 `START DATABASE` |

### 0.1 三条发现的证据链（全部为实测 / 源码坐标）

**F-P6X-1（四条互证）**

1. `deploy/docker-compose.delivery.yml:114-128`（`backend.environment`）**没有** `LICENSE_PUBLIC_KEY`；
2. `deploy/.env.example` **一行 LICENSE 都没有**；
3. compose 语义：`--env-file` 只提供插值变量，不自动注入容器；
4. 实证：容器内 `env | grep -i license` 为**空**；日志 `app.services.license.provider:_verify:192 - license_public_key_missing`。

配套的**产品常量**：`backend/app/core/config.py:54-56` —— `license_public_key: str = ""` 且注释写明
「**留空 = 一律验签失败**」。

**F-P6Y-1（源码坐标 + 待实跑区分）**

```211:219:backend/app/services/license/provider.py
expected_fingerprint = str(body.get("fingerprint") or "")
actual = compute_fingerprint()
if expected_fingerprint != actual:
    ...
    return LicenseState(has_license=False, code=ErrorCode.LICENSE_FINGERPRINT_MISMATCH)
```

**✅ T1 已实跑（2026-10-10）**：公钥经 `.env` 插值 + 临时 override 注入容器
（`env | grep -c LICENSE_PUBLIC_KEY` = **1**）后，返回

```
{"has_license":false,"enforced":true,"code":"LICENSE_FINGERPRINT_MISMATCH", ...}
```

⇒ **验签过了**（不再是 `LICENSE_INVALID` / `license_public_key_missing`），
失败点落在指纹比对 ⇒ **F-P6Y-1 成立**，且证明了 F-P6X-1 是独立存在的**第二层**缺口
（先缺公钥 ⇒ 根本走不到指纹这一步）。

**F-P6Y-2（T1 实跑中新挖出，比 F-P6Y-1 更严重）：容器化交付下指纹退化为「容器网卡 MAC」**

`fingerprint.py` 采集三源：`/etc/machine-id`、主网卡 MAC、`/sys/class/dmi/id/product_uuid`。
在 backend 容器内实测：

```
components = {'mac': '32:72:a2:00:f2:ff'}   ← 三源里只剩 MAC
fp         = 044a7756a3c5402590585e3f852ff8db
/etc/machine-id            → No such file or directory
/sys/class/dmi/id/product_uuid → NOT readable
```

再 `up -d --force-recreate backend` 一次（**不换机器、不换镜像、只重建容器**）：

```
重建前  mac=32:72:a2:00:f2:ff  fp=044a7756a3c5402590585e3f852ff8db
重建后  mac=16:62:cf:1e:75:22  fp=140addd3edfa1b536399653a232eb042
```

⇒ **客户每次 `docker compose up -d`（重启 / 升级 / 扩缩）都会换新 MAC ⇒ 指纹变 ⇒ License 失效。**
这不是"换机恢复"才遇到的问题，是**交付形态本身不可持续**：§6.4 冒烟第 3 条
「License 正常」在容器形态下无法稳定成立。

**F-P6Y-2 的补救实测（2026-10-10，临时容器两次 run 对比，未起栈、未停开发图库）**

| 方案 | 两次 run 的 fp | 结论 |
|---|---|---|
| 不挂（现状） | `70547486665fa71441e07d3b21303229` / `d0cc60c11aaa6f6dff06a13456c671c4` | ❌ 每次都变 |
| **只挂 `/etc/machine-id:ro`（候选 D）** | machine-id 稳定为 `208c9ebe76b44a14b97149e300502066`，但 mac `06:20:6c:55:87:5c` → `0a:e5:be:9c:f3:c5` ⇒ fp `fc3eccf3…` / `83c4ebc4…` | ❌ **D 单独不够** |
| 挂 + 固定 `mac_address` | 两次均 `900624a1691ef74b879ea0e4ffb7a366` | ✅ 稳定 |
| 仅 machine-id 参与计算（不含 mac） | 两次均 `4d0e04e04f1d098c11a6fcbec1eabd1b` | ✅ 稳定 |

⇒ 根因在 `build_fingerprint`：**所有组件排序拼接**，只要 mac 在集合里且变化，fp 就变。

**F-P6Y-3（附带发现）：实现与 ADR §2.1 原文不一致**

- ADR §2.1（`fingerprint.py` docstring 第 6 行）：「`/etc/machine-id` 优先 …… **取不到再回落到 MAC**」；
- 实现 `collect_components()`：只要 mac 非空就**无条件 append**，与 machine-id 是否存在无关。

⇒ **按 ADR 原文实现**（machine-id 存在时不再附加 MAC）+ 交付 compose 只读挂 `/etc/machine-id`
⇒ 容器形态下 fp = **宿主** machine-id，重建容器不再变；且它比"绑容器 MAC"**更贴合**
「绑机器」的原意 —— 绑的是宿主机，不是那个随时会被重建的容器。

**F-P6X-3（实测）**

- `neo4j-admin database load` → `Done: 42 files, 264.7MiB` 成功；
- 随后 `cypher-shell` → `Unable to get a routing table ... database is unavailable`；
- `neo4j stop` / `neo4j start` → `Neo4j is already running (pid:7)`；
- `START DATABASE neo4j` → `Unsupported administration command`（Community 不支持）；
- 唯一有效动作：`docker compose restart neo4j` ⇒ `nodes=7308` 可读。

---

## 1. Non-goals（**9 条** —— 改任何一条之前先按本文 §5 升级）

1. **不改 License 的密码学方案**：Ed25519 / 留空即拒绝 / 时钟漂移容忍一律不动
   （ADR-0006 §2.3 / §2.7）。本批只补**配置通路**，不碰验签语义。
2. **不做 License 服务端 / 在线激活 / 许可证签发系统**：重新签发仍走
   `backend/scripts/license_cli.py`（供应商离线签发），本批不引入任何网络依赖。
3. **不弱化 License 的强度**：不许为了让恢复演练变绿而把 `license_enforce` 改成 false，
   不许给某个函数调用「跳过指纹比对」的后门。
4. **不重做 P6-X 的演练留证**：本批产出 README / compose / 模板级别的修复，
   `docs/drills/restore-drill-*.md` 仍要到 P6-X 正式批次由**人工双人**产出，**AI 不代写一个字**。
5. **不动 `frontend/`**、**不改契约**：`export_openapi.py --check` 零 diff 为判据。
6. **不碰 backup / restore 脚本的业务逻辑**：`restore.py` 的 `SKIP` 分级与 §6.2 判据保持不变
   （F-P6X-2 记录的容器限制只登记，**不在本批改**）。
7. **不因为本批就把第 9 项改判据**：`install_acceptance.py` 第 9 项仍只看
   `docs/drills/restore-drill-*.md` 是否存在；不许加一行让它在没留证时也变绿。
8. **不顺手清理本批范围之外的其他发现**：本批只处理 F-P6X-1 / F-P6Y-1 / F-P6X-3，
   其余发现（如 §9.1 环境独立度、F-P6X-2 的 `restore.py` 容器限制）仍在
   P6-D1b 登记处原地排队，**不许夹带**。
9. **AI 不得代填 `correct` 值、不得代签任何署名**：失败码要实跑拿到，
   留证要真人双人署；缺位就写缺位，不许编。

> ⚠️ 实现中若发现必须触碰某条 Non-goal ⇒ **先缩范围再报告**
> （哪份文档哪一行 / 改什么 / 为什么绕不过 / 试过的替代方案）。

---

## 2. 决策表（**待你逐条拍板**）

| # | 决策 | 建议 |
|---|---|---|
| **Y1** ✅ | 是否开本批 | **已裁决 = 开**（2026-10-10 用户：「按你建议开吧」） |
| **Y2** 🆕 | `LICENSE_PUBLIC_KEY` 由谁提供 | **建议 = 走 `.env` 插值进 `backend.environment`**（与 `NEO4J_PASSWORD` 同款写法），并在 `deploy/.env.example` 补占位 + 说明；**内置到镜像**虽更省事，但会让「换密钥 = 重新出镜像」，也与既有「密钥不进镜像」的配置风格不一致 |
| **Y3** 🆕 | F-P6Y-1 怎么处置（**最关键**） | 三选一，见 §2.1；**先跑 §2.2 的判据再选** |
| **Y4** 🆕 | Y-c 的 README 落点 | ✅ 已定 = **`deploy/README.md`**。⚠️ **更正**：初稿写的 `docs/v1.1.0-deploy.md` **并不存在**（我未核实就落笔）；实际新建在 `deploy/README.md` 的「恢复（现场 / 演练）」一节 |
| **Y5** 🆕 | 本批要不要顺带补 §10 十项回归 | 建议**跑一次** `install_acceptance.py` 作回归（预期：第 9 项仍 SKIP，其余不倒退） |
| **Y6** 🆕 | 验证环境 | 建议沿用 P6-X 预演的同款：同 daemon `COMPOSE_PROJECT_NAME=graphrag-drill` + 独立 `.env`，演练窗口内 `docker stop graphrag-neo` |
| **Y7** 🆕 | 恢复演练的见证者 | **仍缺位**；本批不写留证，故不阻塞 —— 但正式 P6-X 开工前必须落实 |

### 2.1 Y3 的三个候选（**未决**）

| 候选 | 做法 | 代价 / 收益 |
|---|---|---|
| **A. 承认「恢复后须重新签发」** | 在 §6.1 / §6.4 写死：License **随机器绑定**，换机恢复后必须由供应商**重新签发**，冒烟第 3 条在新机上的判据改成「重新签发后 valid」 | 最诚实、改动最小；代价：DR 的 RTO 里要多算一次人工签发 |
| **B. 换个指纹锚点** | 指纹改为绑**客户 / 部署标识**而非机器（如 license 里的 `customer` + `max_seats`） | 换机可用；代价：**弱化反盗版强度**（一个 license 可到处拷），触 Non-goals 第 3 条之嫌 |
| **C. License 支持「DR 备用机」** | license 里允许登记 N 台机器的指纹（主 + 备） | 兼顾；代价：签发协议要扩字段，**属新量程**，须先扩 ADR-0006 |
| **D. 让指纹在容器形态下稳定** 🆕 | 让容器读到**宿主**的稳定标识（如只读挂载 `/etc/machine-id`），使三源不再只剩 MAC | 直击 F-P6Y-2：重建容器不再换指纹；代价：要动交付 compose（挂只读文件），且**不得**顺手削弱"机器绑定"语义，否则与 B 同型 |

### 2.2 Y-b 第一步：先把失败码区分开（**不许先写结论**）

```bash
# 在 drill 环境里，把公钥真正送进 backend 容器之后：
curl -s http://127.0.0.1:8000/api/v1/license/status   # 看 code 字段
docker compose -p graphrag-drill logs backend | grep -i "fingerprint\|public_key"
```

| 观测到的 `code` | 含义 | 后续走哪条路 |
|---|---|---|
| `LICENSE_INVALID` | 验签仍不过 ⇒ 公钥 / 签名有问题 | 继续查 Y-a（密钥与 file 配对） |
| **`LICENSE_FINGERPRINT_MISMATCH`** | 验签过了、机器不对 | **F-P6Y-1 成立** ⇒ 进 §2.1 三选一 |
| `has_license=true` | 都没问题 | F-P6Y-1 不成立，回到 Y-a 收口即可 |

> ✅ **T1 已跑（2026-10-10）**：实测 `code = LICENSE_FINGERPRINT_MISMATCH`
> ⇒ 排除 `LICENSE_INVALID`，**F-P6Y-1 成立**；同轮挖出 **F-P6Y-2**（见 §0.1）。
> ⇒ **Y3 的候选必须补一条 D，且 D 应最先讨论**：既然容器重建就换指纹，
> 「A. 恢复后重新签发」的代价就从"一次人工"放大成"**每次重启都要重签**"。

---

## 3. 判据（机器可跑的才算完成）

| # | 判据 | 期望 |
|---|---|---|
| J1 | 交付 compose `backend.environment` 含 `LICENSE_PUBLIC_KEY` | `docker compose config` 里可见该键 |
| J2 | `deploy/.env.example` 含 LICENSE 说明与占位 | 文件里有对应行 |
| J3 | 用 `.env.example` 起的干净环境里 `GET /api/v1/license/status` 的 `code` | 不是 `license_public_key_missing`（具体值按 §2.2 记录） |
| J4 | 若 J3 走到 `FINGERPRINT_MISMATCH` | §2.1 三选一已写入 §6.1 / §6.4 相应条款 |
| J5 | 交付 README 含「图库 load 后必须 restart」 | `grep -c restart` ≥ 1 且步骤能对得上实测 |
| J6 | `install_acceptance.py` 回归 | 第 9 项仍 SKIP，其余**不倒退**（基线：`PASS 1 / SKIP 9 / FAIL 0`） |
| J7 | `export_openapi.py --check` | 零 diff |

---

## 4. 任务拆分与进度（2026-10-10 更新）

| # | 任务 | 状态 |
|---|---|---|
| **T1** | drill 环境实跑 §2.2，区分失败码 | ✅ **已完成** ⇒ `LICENSE_FINGERPRINT_MISMATCH`（F-P6Y-1 成立），并挖出 F-P6Y-2 / F-P6Y-3 |
| **T2** | Y-a：交付 compose `backend.environment` 增补 `LICENSE_PUBLIC_KEY` + `deploy/.env.example` 补占位说明 | ✅ **已完成**（必填插值 `${LICENSE_PUBLIC_KEY:?…}`，缺键即解析阶段报错） |
| **T3** | Y-d：实现对齐 ADR §2.1（machine-id 取到则 MAC 不参与）+ 交付 compose 只读挂 `/etc/machine-id` | ✅ **已完成**（`fingerprint.py` 改 + compose 挂载 + 新增 4 条护栏用例） |
| **T4** | Y3 落地：把结论写进 `docs/deployment-spec.md` §6.1 / §6.4 | ✅ **已完成**（§6.1 约束 3 + §6.4 License 判据表） |
| **T5** | Y-c：交付 README 补「图库 load 后必须 `restart neo4j`」 | ✅ **已完成**（`deploy/README.md` 新增「恢复（现场 / 演练）」一节，另含 pg_restore 用超级用户、License 换机重签） |
| **T6** | 回归：跑 J6 / J7 | ✅ **已完成**：J7 `[OK] contracts/openapi.yaml 与后端模型一致`；J6 `PASS 1 / SKIP 9 / FAIL 0`（与基线一致、**未倒退**；第 9 项仍 SKIP —— 未造留证） |
| **T7** 🆕 | **重新出交付镜像 + 离线包**（`build_delivery_images.py --save` → `--verify`） | ✅ **已完成**（阻塞项解除，读数见 §6.3） |
| **T8** 🆕 | 端到端复验（**不带 override** 的交付 compose） | ✅ **已完成**（公钥进容器、重建容器 fp 不变，读数见 §6.3） |

---

## 6. 实现记录（2026-10-10）

### 6.1 改动清单

| 文件 | 改动 |
|---|---|
| `backend/app/services/license/fingerprint.py` | `collect_components()`：machine-id **取到**⇒ 不再回落 MAC（对齐 ADR §2.1 原文）；docstring 补容器形态说明 |
| `backend/tests/test_license_fingerprint.py`（新增） | 4 条护栏：MAC 被排除 / **换 MAC 不改指纹** / MAC 仅在回落时使用 / 主板标识照旧参与 |
| `deploy/docker-compose.delivery.yml` | `backend` 增补 `LICENSE_PUBLIC_KEY: ${LICENSE_PUBLIC_KEY:?…}`（必填插值）+ `volumes: /etc/machine-id:/etc/machine-id:ro` |
| `deploy/.env.example` | 必配由「四个」改「五个」，新增 `LICENSE_PUBLIC_KEY` 及整段说明（含 F-P6X-1 的三条坑） |

### 6.2 实测判据

| 判据 | 读数 |
|---|---|
| `compose config` 可见公钥与挂载 | `LICENSE_PUBLIC_KEY: …` / `source: /etc/machine-id` ✅ |
| **缺键时是否报错** | `error while interpolating … required variable LICENSE_PUBLIC_KEY is missing a value` ✅（不再静默） |
| 容器内（挂载 + 新代码） | `components = {'machine-id': '208c9ebe…'}`，`fp = 4d0e04e04f1d098c11a6fcbec1eabd1b` ✅ MAC 不再参与 |
| 交叉印证 | 该 fp 与 §0.1「仅 machine-id 参与计算」的模拟值**逐字一致** ✅ |
| 对照（旧镜像、不挂载） | `components = {'mac': '22:82:83:ff:0a:17'}` ⇒ 只剩 MAC（缺陷原状） |
| pytest 回归 | `tests/test_license_fingerprint.py` **4 passed**；`-k "fingerprint or license"` **6 passed** ✅ |

### 6.3 重出包 + 端到端复验（阻塞项已解除）

交付 compose 用的是 `graphrag-agent/backend:1.6.0` **镜像**，代码改动不重出镜像就进不了客户的包。
经用户批准重出（2026-10-10）：

| 步 | 读数 |
|---|---|
| `--save` | backend / frontend 两个镜像重建 + `docker save` 成功 |
| **新代码确实进了镜像** | 挂载 `machine-id` 跑两次 ⇒ `components={'machine-id':…}`、`fp=4d0e04e04f1d098c11a6fcbec1eabd1b` **两次一致**；不挂载 ⇒ 回落 `{'mac':…}`（符合 ADR 回落语义） |
| `--verify` | `tar SHA-256 校验通过（496,529,920 字节）` / `tag 与交付 compose 逐字节一致` / 两枚 image id 一致 / 第三方不入包 ⇒ **7 项全 PASS** |
| 体积旁证 | tar 由 `496,524,288` → `496,529,920` 字节（**+5,632**）⇒ 镜像内容确实变了 |

**端到端复验（不带 override，只用交付 compose 自身）**：

| 判据 | 读数 |
|---|---|
| 公钥是否进容器 | `env \| grep -c LICENSE_PUBLIC_KEY` = **1** ⇒ **F-P6X-1 修复由交付 compose 自身完成**，不再依赖任何外部 override |
| 重建容器 fp 是否变 | 重建前后均 `fp=4d0e04e04f1d098c11a6fcbec1eabd1b` ⇒ **F-P6Y-2 修复在镜像 + compose 上生效** |
| License 状态 | `LICENSE_MISSING`（新栈未放 License 文件，属预期；非空断言） |

### 6.4 ⚠️ 新发现（未解决）：换机重新签发**没有工具支撑**

按 §6.1 约束 3，换机恢复后必须由供应商重新签发 License。但实测发现：

- `backend/scripts/license_cli.py` **只有 `fingerprint` 一个子命令**，`build_parser()` 里没有签发 / 生成子命令；
- 开发环境 `.env` 里只有 `LICENSE_PUBLIC_KEY`，**没有私钥**（无私钥也无从签发）。

⇒ 因此本轮**做不了正向验证**（"签发一份匹配当前指纹的 License ⇒ `has_license=true`"），
也意味着：**「换机须重新签发」这条流程目前缺少工具与密钥管理的落地方案。**
⇒ 建议下一批立项：签发工具（含私钥保管方式）+ 用一条端到端的正向用例把它钉住。

---

## 5. 升级路径

出现下列任一情形 ⇒ 停下找用户，**不自行放宽**：

1. 要改 License 的验签语义 / 指纹算法（触 Non-goals 第 1、3 条）；
2. 要引入服务端激活或签发协议扩字段（触 Non-goals 第 2 条，属新量程，须先扩 ADR-0006）；
3. 为了让第 9 项变绿而写 `docs/drills/`（永久红线）；
4. 实证出现第三个失败码，与本文列出的两种都不符 ⇒ 先补给用例，不许当作边角略过。
