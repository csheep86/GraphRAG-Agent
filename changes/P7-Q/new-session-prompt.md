# 下一批开工提示词 · **P7-J（B5：License 签发私钥离线处置）**｜**纯人工批次**

> 本文件写在 `changes/P7-Q/` 下（**当前批次目录，写给下一批**）。
> 上一批 **P7-Q** 已交付（F-P7H-1 关闭，本地 3 个提交已推送）：
> `7b57378`（P7-H 见证者签名）/ `de369f3`（首次部署建表改走迁移）/ `3fbff6b`（演练留证 + 集成日志）。
> **下一批 = P7-J**，出处 [`docs/release-readiness-audit-2026-10-13.md`](../../docs/release-readiness-audit-2026-10-13.md) §4 **B5** / §7 序 **8**，
> 提案 [`changes/P7-J/proposal.md`](../P7-J/proposal.md)（已立批，**尚未开工**）。

---

## 1. 执行模式（**人做主体**，本行不许改写）

| 角色 | 能做什么 | **不能**做什么 |
|---|---|---|
| **人（你）** | 决定迁移到哪、执行迁移、**执行抹除**、在登记文件里签签发人真名 | — |
| **AI（我）** | 出搬运清单 / 跑校验命令 / 读机器输出 / 把结论回登进 `changes/P7-J/integration-log.md` / 提交推送 | **不得**执行删除动作、**不得**代填签发人姓名与签发环境描述、**不得**代做"已抹除"的结论 |

> ⚠️ 这与 `delivery-plan.md` §9.3「三条只能由人完成的事」同源：**判分 / 演练见证者 / 裁决**都不许脚本代做。
> 本批的"抹除 + 签发登记"属同一类：**动作与署名都只能是人**，AI 只做搬运与留证。
> 判据 1「给出检索命令的输出」= 人跑完命令、把输出贴进集成日志；**AI 不得自己造那段输出**。

---

## 2. 确认起点 + 为什么是它（**三条机械理由，全部 ¥0 实测**）

### 2.1 B 类（生产硬阻断）只剩这一条

| B 项 | 归哪个批次 | 状态（HEAD 上可核） |
|---|---|---|
| B1 dev 身份兜底 | P7-C | ✅ `ef62188` |
| B2 前端 Mock 静默回落 / B3 契约说谎 | P7-D | ✅ `0c2b0d9` |
| B4 前端 Base URL 硬编码 / B6 根 README 无部署章节 | P7-E | ✅ `4944a0b` |
| **B5 签发私钥仍在开发机** | **P7-J** | ❌ **未动**：`%USERPROFILE%\.graphrag-license\private.pem` 仍在（**119 B**，最后写入 **2026-10-11 18:26**，¥0 实测，未读内容） |

审计 §1 建议②原文：**「先修 B 类生产硬阻断，再补 A 类流程项（按暴露风险排，不按队列编号排）」** ⇒ B5 是 B 类唯一遗留，排在最前。

### 2.2 它是唯一"暴露即不可逆、且没有任何护栏兜得住"的一条

P6-Z 已**实证**：「换公钥 + 自签」**四步**即可绕过机器绑定（`changes/P6-Z/proposal.md` §0.2.1）。
已做的防护是 `app/services/license/provider.py:187-194`（公钥内置、无 env 覆盖）——它只防**换公钥**，
**对私钥泄露零防护**：私钥一旦出开发机 ⇒ DR-C1（License 体系）**整体失效**，且没有任何 G 护栏会红。

### 2.3 零前置依赖 + ¥0 + 半天，且本批不产生代码改动

| 候选 | 为什么排在 J 后面 |
|---|---|
| P7-F（A3 阈值回填） | **卡在用户裁决**：阈值来源必须是你拍的数，AI 不得代填 ⇒ 随时可插队，但不构成"能开工" |
| P7-I（A4 L2 端到端） | 工量 **2~4 人天 + 要烧 LLM 重跑** C2-a / C2-b |
| P7-K（A8 评测可复现性） | 修法③「独立评测环境」要新建 org / 图库，**可能产生 LLM 费用 ⇒ 须你批准**（P7-K §5） |
| P8-Release（A6 终审） | 依赖 0~10 **全完成** |

⇒ J 是唯一「今天就能闭合、不依赖他人、不烧钱、且不碰产品代码」的一条。本批改动只在**文档 / 登记**
⇒ CI 只需**持平不降**（见 §7 基线），风险最低。

---

## 3. 开工自检（**动手前先跑，结论只认机器输出**）

```powershell
# ① 护栏真实状态（🟢 / 🔵 / 🟠 / 🟡 四档，不看文档表格）
cd backend && uv run python scripts/check_startup_readiness.py

# ② License 护栏基线（本批不改它们，只要求全绿）
uv run pytest -q tests/test_license_guardrails.py tests/test_license_fingerprint.py   # 期望 12 passed
uv run pytest -q -k license                                                           # 期望 16 passed（含他处 4 条）

# ③ ¥0 同源核对 —— **这一条决定"迁移"还是"轮换"，不许跳过**
uv run python -c "from app.services.license.public_key import BUILTIN_LICENSE_PUBLIC_KEY_B64 as k; print(k)"
(Get-Content "$env:USERPROFILE\.graphrag-license\public.b64" -Raw).Trim()

# ④ 私钥存在性（**只看属性，不读内容、不打印内容**）
Get-Item "$env:USERPROFILE\.graphrag-license\private.pem" | Select-Object Length, LastWriteTime
```

**③ 的实测结论（2026-10-14，已核）**：

```
BUILTIN_LICENSE_PUBLIC_KEY_B64 (public_key.py:28) = R5Q6Ab4q6cylp3RXRPBd/vbeIoCXvaOGEGdQFkiLyG4=
%USERPROFILE%\.graphrag-license\public.b64        = R5Q6Ab4q6cylp3RXRPBd/vbeIoCXvaOGEGdQFkiLyG4=
⇒ 逐字相等
```

⇒ **本机 `private.pem` 就是出厂内置公钥对应的签发私钥** ⇒
**处置方式是「迁移 + 本机抹除」，不是「重新生成密钥对」**：
一旦轮换，本机 `deploy/license/app.lic`（指纹 `0d531a1f913adc481d84db4e19b703da`）和任何已签发证件
**立刻验签失败**，那要牵动 P6-Z / 已发证件重签，属 P7-J §5 情况 3（**先报告，别动**）。

---

## 4. 边界纪律：**Non-goals 共 5 条**（改一条都要先回来登记理由）

照抄 `changes/P7-J/proposal.md` §3，逐条照做：

1. **不重签已发出的 license**（先确认有没有已发证件——本机那一份 `app.lic` 就是）。
2. **不改验签逻辑 / 不弱化机器指纹**。
3. **不把私钥放进仓库任何位置**（含加密压缩包 / base64 片段）。
4. **不做 KMS / HSM 接入**（量产阶段的事）。
5. **AI 不执行删除、不代填签发人姓名**。

> 另外两条**本批之外**的红线（别顺手做）：
> - 不顺手补 **P7-F / P7-I / P7-K**；
> - 不顺手改 `test_license_guardrails.py` / `test_license_fingerprint.py`/ `provider.py` / `fingerprint.py` 一行。

---

## 5. 已查证坐标表（**都是本机实测，不是读文档得来的**）

| 项 | 坐标 | 实测 |
|---|---|---|
| 私钥 | `%USERPROFILE%\.graphrag-license\private.pem` | 存在，**119 B**，2026-10-11 18:26（**未读内容**） |
| 公钥（本机副本） | 同目录 `public.b64`，**46 B** | 与内置公钥**逐字相等** |
| 内置公钥 | `backend/app/services/license/public_key.py:28` `BUILTIN_LICENSE_PUBLIC_KEY_B64` | `R5Q6Ab4q6cylp3RXRPBd/vbeIoCXvaOGEGdQFkiLyG4=` |
| 防绕过（已做部分） | `backend/app/services/license/provider.py:187-194` | 公钥内置，无 env 覆盖开关 |
| 签发工具 | `tools/license/issue_license.py`（`genkey` / `issue` / `pubkey`） | **刻意不进镜像** |
| 入库红线 | `.gitignore:58` 忽略 `deploy/license/app.lic` | `git ls-files` 里 **0 个** `.lic` ⇒ 私钥与 seed license **均未入主仓** ✅ |
| 本机已签证件 | `deploy/license/app.lic` | 存在且**未入库**（`git status --ignored` ⇒ `!!`）；指纹 `0d531a1f913adc481d84db4e19b703da`，`customer=local-dev`，`not_after=2036-12-31` |
| 护栏 | `tests/test_license_guardrails.py`（8）+ `tests/test_license_fingerprint.py`（4） | **12 passed**（`-k license` 全仓 **16 passed**） |
| 队列 / 缺陷出处 | `docs/release-readiness-audit-2026-10-13.md` §4 B5 / §7 序 8；`changes/P6-Z/proposal.md:191-197`（T6）、`:241-251` | — |

> ⚠️ **口径提醒**：P7-J §4.3 写「8 条 + 4 条全绿」——**条数与实测一致（12）**，但 `-k license` 全仓是 **16**
> （另有 4 条 keyword 命中在他处）⇒ 判据照旧成立，**引用时写清楚是哪个口径**，别混写。

---

## 6. 决策表（**都要你拍，AI 不填**）

| # | 决策 | 选项 / 现状 | 谁定 |
|---|---|---|---|
| D1 | **迁移到哪** | 离线机 / 密码管理器 / 加密盘（P7-J §2.1 给了三类） | **你** |
| D2 | **迁移 ≠ 轮换** | 已由 §3 ③ 机械裁定：内置公钥与本机公钥同源 ⇒ **只迁移、不重新生成密钥对** | 机械已定（若你坚持轮换 ⇒ 走 §8 情况 3） |
| D3 | **抹除方式** | 安全擦除 vs 删除 + 清空回收站 / 备份检查（判据要"回收站里也没有"） | **你执行** |
| D4 | **登记落点** | `tools/license/README.md` vs `docs/adr/0006-*.md` §证据节（P7-J §2.3 两个候选） | **你 / 架构师** |
| D5 | **登记内容** | 签发人 / 签发环境描述 / 迁移日期；⚠️ **联系方式不得进仓库** | **你签名** |

---

## 7. 基线（**先记住，收口时逐项核销**）

| 项 | 基线读数 |
|---|---|
| 本地 pytest（P7-Q 交付后） | **1278 passed / 46 skipped / 0 failed**（改动前 1274，+4 = 本批新增用例） |
| License 护栏 | 两文件 **12 passed**；`-k license` **16 passed** |
| ruff / format | `All checks passed!` ／ `301 files already formatted` |
| 契约零漂移 / 接缝纪律 | `[OK]` / `[OK]`（ERROR 0 / WARN 0 / OK 12） |
| CI（上批 P7-P） | run **`38503380019`**，后端 job **1313 passed / 7 skipped** |
| **本批（P7-Q）推送后** | 新增 4 条 ⇒ 后端 job **期望 1317**（= 1313 + 4）⇒ **实际 run 号与读数待回填** |

> **核销规则**：P7-J **不新增用例** ⇒ CI 计数应当**持平 1317**（不是上升）。
> 若下降 ⇒ 说明有既有用例因本批文档/登记改动而红，**先查是不是批次摊太大，而不是先改测试让它绿**（R-10）。

---

## 8. 验收判据（照 `changes/P7-J/proposal.md` §4，四条全过）

1. **开发机 `private.pem` 已不存在** —— 给出检索命令的**真实输出**（人跑、人贴）。
2. **签发环境可被指定的人复现**，且鉴别能力不依赖当前登录会话。
3. `tests/test_license_guardrails.py` + `tests/test_license_fingerprint.py` **12 条全绿**（本批不改它们）。
4. **`git status` 无密钥相关痕迹**；CI 四 job 全绿。

> 判据 4 的"无痕迹"要连 `--ignored` 一起看：`git status --porcelain --ignored=matching`。
> 本机 `deploy/license/app.lic` 本来就是 `!!`（已忽略、未入库）——**那是既有状态，不是本批造成的**，
> 别把它当成"密钥痕迹"去删（删了会让本机 License 失效）。

---

## 9. 升级用户的四种情况（**触发任一条就停下报告，不许自己往下走**）

照抄 `changes/P7-J/proposal.md` §5：

1. **私钥文件已不存在**（历史已处置）⇒ 报告 + 登记核实结论，本批可直接结案。
2. **发现私钥曾进入某一版镜像 / 离线包** ⇒ **立刻升级**：那是**安全事件**，可能要重出镜像
   （核查入口：`build_delivery_images.py` 的产物清单 + `docker save` 出的 tar；**¥0 可查**）。
3. **存在已签发 license** ⇒ 先确认换私钥对它们的影响再动
   （本机那份 `app.lic` 就是；若你对**外部**客户已发过证件 ⇒ 重签影响面要先摆出来）。
4. **迁移路径需要你提供设备 / 介质** ⇒ 停下等你安排。

> 补充第 5 条（本批特有）：**③ 同源核对若不相等** ⇒ 说明内置公钥另有其主 ⇒
> **先查清"另一个签发环境是谁"再谈抹除**，否则可能把唯一能签这把公钥的私钥弄丢。

---

## 10. 提交推送纪律

1. Conventional Commits：`docs(license)` / `chore(security)` 之类；**一个动作一个提交**。
2. **人做的抹除动作与 AI 做的回登提交分开**：抹除发生在你的机器上（不产生提交）；
   回登只写 `changes/P7-J/integration-log.md` + §6 D4 选定的登记文件。
3. 提交前：`git status --porcelain` 里**不得出现** `.pem` / `.lic` / 密钥片段（见 §8 判据 4）。
4. 推送后回填 **CI run 号 + 后端 job 读数**到 `changes/P7-J/integration-log.md`，单独一个
   `docs(changes): P7-J 回填 CI 读数` 提交（前几批都这么做，好回溯）。
5. ⚠️ **本机已知问题**：2026-10-14 会话里 `github.com:443` 出现过**连接被重置**（无代理）
   ⇒ 推送失败**不要反复重试**，直接报告；推送成功与否以 `git status -sb` 的 `ahead N` 为准。
6. 每写完一个子任务就跑 `uv run python scripts/check_session_drift.py`（S1 会读出本批 5 条 Non-goals），
   **别攒到最后**。

---

## 11. 不许外推（**这些坑都是踩过的**）

1. **不许**因为"私钥只有 119 B、只有本机在用"就跳过——P6-Z 的实证就是"小东西也能掀翻整套 DR-C1"。
2. **不许** AI 代删 / 代填签发人 / 代写"已抹除"的结论（§1 红线）。
3. **不许**把"轮换密钥对"当成"迁移"——§3 ③ 已机械裁定，轮换会让本机 `app.lic` 立刻失效。
4. **不许**顺手补 P7-F / P7-I / P7-K，也不许顺手改验签逻辑（§4）。
5. **不许**把 `-k license` 的 16 与两个文件的 12 混写成一个数（§5 口径提醒）。
6. **不许**在 PR / 提交信息 / 日志里贴私钥内容或路径以外的密钥信息（CODEBUDDY「日志禁止输出密钥」）。

---

## 12. 相邻的人做小尾巴（**不在 P7-J 判据内，别混进它的提交**）

- `docs/drills/upgrade-drill-20261014-p7q.md` 的**见证者**一栏仍为「待签真名」
  （P7-Q 的演练留证，纪律要求**执行者 ≠ 见证者**）。
  若同一个半天顺手签掉 ⇒ **单独一个提交**，不要并进 P7-J 的登记提交。
- `docs/release-readiness-audit-2026-10-13.md` §7 队列**没有 P7-Q 行**（P7-Q 是本日新增批次）。
  本批**不负责**补（属 §4 之外的红线）；但 P8-Release 逐行对账前必须补，已在 §13 登记。

---

## 13. 下一批指针（**J 之后的顺序与理由**）

```
P7-J（B5，本批） → P7-K（A8 评测可复现性） → P7-I（A4 L2 端到端） → P7-F（A3 阈值回填，插队） → P8-Release（A6 终审）
```

| 下一批 | 为什么排这个位置 |
|---|---|
| **P7-K** | 审计 §7 序 9 明写**「阻塞 P8-Release」**：没有可复现的 C1，终审无从复核，86 道判分就只是一次性快照。修法③（独立评测环境）**已由你裁决**（2026-10-13）⇒ 只剩执行。⚠️ 可能产生 LLM 费用 ⇒ 开工前先报批（P7-K §5）。 |
| **P7-I** | A4 L2 端到端，工量最大（2~4 人天 + LLM 重跑 C2-a / C2-b）⇒ 放在 K 之后，避免"数字不可复现时白跑一轮贵的"。 |
| **P7-F** | 只等你拍 TBD-7 那个数（0.1 人天）⇒ **随时可插队**；拍完即可回填，不与上面两条抢顺序。 |
| **P8-Release** | 依赖 0~10 全完成；对账前必须先把 §12 的两条尾巴（P7-Q 队列行、演练见证者）清掉。 |

> 顺序的总依据仍是审计 §1 三条建议：① 判分（✅ 已完成 86/86）② **先 B 后 A**（本批收尾 B 类）
> ③ **冻结新增能力**——治理的边际收益已低于核平既有数字。
