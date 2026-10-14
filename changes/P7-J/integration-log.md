# P7-J · 集成日志（License 签发私钥处置 · B5）

> **状态：用户裁决 —— 本批不执行（延期，触发条件已登记）**
> **裁决时间**：2026-10-14 ｜ **裁决人**：william（用户本人）
> **后果**：本批次**不满足** `docs/release-readiness-audit-2026-10-13.md` §7 序 8 的原出口判据，
> 也不满足 `changes/P8-Release/proposal.md` §1 前置第 6 条 ⇒ **P8-Release 终审时必须显式引用本文件作为豁免依据**。

---

## 1. 裁决内容

| 项 | 结论 |
|---|---|
| 私钥是否迁移出开发机 | **不迁移**（维持现状：`%USERPROFILE%\.graphrag-license\private.pem`） |
| 本机私钥是否抹除 | **不抹除** |
| 签发人 / 签发环境是否登记于 `tools/license/README.md` | **不登记** |
| 是否认定开发机存在安全暴露风险 | **否**——用户明确表示「不用考虑我的电脑安全问题，我的电脑非常安全」 |

执行模式仍按 `new-session-prompt.md` §1（**人做主体**）：本批所有涉及私钥的动作（迁移 / 抹除 / 签名）
本就只能由人执行；本次的决定是**由人决定不做**，AI 未执行任何删除、搬运或写入密钥内容的动作。

---

## 2. ¥0 已核实的事实（2026-10-14，全部来自本机命令输出，非推断）

| # | 事实 | 命令 / 出处 |
|---|---|---|
| 1 | `private.pem` 存在，**119 B**，最后写入 2026-10-11 18:26（**全程未读取文件内容**） | `Get-Item \| Select-Object Length,LastWriteTime` |
| 2 | 本机 `public.b64`（46 B）与代码内置公钥 `app/services/license/public_key.py:28` **逐字相等** = `R5Q6Ab4q6cylp3RXRPBd/vbeIoCXvaOGEGdQFkiLyG4=` | `python -c "…BUILTIN_LICENSE_PUBLIC_KEY_B64…"` + `Get-Content public.b64` |
| 3 | ⇒ 本机私钥即出厂内置公钥的签发私钥 ⇒ 若「轮换」而非「迁移」，本机 `app.lic` 立即验签失败 | 由上条机械推导 |
| 4 | ACL 仅 `SYSTEM` / `Administrators` / `WILLIAM\william` 三者可读（均 `(F)`） | `icacls private.pem` |
| 5 | 家目录为 `C:\Users\william`，**不在 OneDrive 等云同步路径内**；家目录下的 `OneDrive` 文件夹不含 `.graphrag-license` | `$env:USERPROFILE` + `Get-ChildItem -Filter OneDrive*` |
| 6 | 全仓无任何 Dockerfile / 构建脚本引用 `.graphrag-license` 或 `.pem` ⇒ **私钥与签发能力均未进交付镜像 / 离线包** | 全仓 `search_content("graphrag-license\|private\.pem")` 命中 8 处，全为文档与 `issue_license.py:47` 的默认路径常量 |
| 7 | `git ls-files \| grep -E "\.pem$\|\.lic$"` ⇒ **0 个**（无密钥入库痕迹） | `git ls-files` |
| 8 | 已签发证件**仅一份**：`deploy/license/app.lic`，`customer=local-dev`，指纹 `0d531a1f913adc481d84db4e19b703da`，未入库（`!!` 已忽略） | `git status --porcelain --ignored=matching` + 前批登记 |
| 9 | **无任何外部持证方** | 由上条 + 交付物排查 |
| 10 | License 护栏：`test_license_guardrails.py` + `test_license_fingerprint.py` = **12 passed**；`-k license` 全仓 **16 passed** | `uv run pytest -q` |

---

## 3. 为什么可以延期（技术理由，供日后复审）

审计 §4 把 B5 归入 **B 类「生产硬阻断」**，与 B1~B4 / B6 并列。但 B1~B4 / B6 的共同点是
「客户今天装上去就会撞到」；B5 的后果链（私钥泄露 ⇒ 攻击者可自签 License ⇒ 机器绑定失效）
**成立前提是存在外部持证方**。当前事实 8 / 9 表明该前提**不成立**。

且 ADR-0006 §5 **R-L5** 原文为「私钥不出**签发环境**（离线 / KMS）」——
当前这台开发机**就是**签发环境，故严格讲**现状未违背 R-L5**；
真正未满足的是一条更强的 hygiene 要求（签发环境独立于日常联网开发机），那是量产期要求。

⇒ 结论：**延期的依据成立，但必须在出现第一位外部持证方之前回到本批**。

---

## 4. 触发条件（**满足任一必须重做本批**）

1. **出现第一位外部持证方**（向本机以外的机器签发第一份 `.lic`）之前；
2. 私钥文件被复制到本目录以外的任何位置 / 任何机器 / 任何云端；
3. 开始做他人可见的 beta / POC 交付之前；
4. ADR-0006 R-L5 被修订得更严（如要求 KMS）。

---

## 5. 下游影响（`P8-Release` 必读）

`changes/P8-Release/proposal.md` §1 前置清单第 6 条写「**P7-J 完成（私钥离线处置）**」。
本裁决生效后，该条**不再以原判据满足**，P8-Release 收口时须：

- 在 §4 出口判据 1 的「🟠 / 🟡 / 🔵 逐条有解释与处置登记」里**显式引用本文件**；
- 不得把本条写成「已完成」或悄悄跳过（违反 `P8-Release` §3 第 3 条「每条 claim 都要能贴机器输出」）；
- 是否接受该豁免，属 **P8-Release 的用户裁决范围**，非本批可代决。

---

## 6. 本批有没有动代码 / 动文件

| 类别 | 结论 |
|---|---|
| 产品代码 | **零改动**（未碰 `provider.py` / `fingerprint.py` / `public_key.py`） |
| 既有 License 测试 | **零改动**（仍是 12 passed / 16 passed） |
| 密钥相关写入动作 | **零**（未创建、未复制、未删除、未打印任何密钥内容） |
| 仓库改动 | **仅本文件**（`changes/P7-J/integration-log.md`） |

> 「没有 diff 就等于没有本批」是本批的正确形态：它是一次**裁决登记**，不是一次施工。

---

## 7. CI

本批只有一处 `.md` 新增，不触发后端 / 前端 / 契约 job 的任何判据变更 ⇒ **期望：四 job 全绿、计数持平**。
推送后回填 run 号。
