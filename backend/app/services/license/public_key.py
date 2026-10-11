"""内置验签公钥（ADR-0006 **R-L5**：「私钥不出签发环境，**公钥内置**」）。

⚠️ **本值是唯一的验签公钥来源，且刻意不预留任何对外覆盖口** —— 不可由 `.env` / 环境变量覆盖。

**为什么不可覆盖**（不是洁癖，是 2026-10-11 实测得出的）：
过去公钥走 `.env`（`LICENSE_PUBLIC_KEY`），于是客户只要做四步就能给自己发一张 License：

    ① `license-cli fingerprint` 取本机指纹（CLI 的既定用途，不是漏洞）
    ② 自己生成一对 Ed25519 密钥
    ③ 用自己的私钥签一份「fingerprint == ①」的 License
    ④ 把②的公钥填进 `.env` ⇒ 验签通过、指纹也对 ⇒ `has_license=true`

实测返回值：`status=active` / `not_after=2099-12-31` / `max_orgs=100` / `max_seats=100` /
**全部 7 个模块** ⇒ 机器绑定与整套 License 管控对能改 `.env` 的客户而言形同虚设。
完整记录在 [`changes/P6-Z/proposal.md`](../../../../changes/P6-Z/proposal.md) §0.2.1。

⇒ 因此：**公钥内置，轮换 = 发新版**（这正是 R-L5 原文写明的处置方式）。

**唯一的替换接缝**：测试需要"用另一把公钥"来验证验签本身真的在验。
那是**进程内**替换本模块的常量（`monkeypatch` / 直接赋值），
环境变量与交付配置里**不存在**任何对应开关 —— 见 `tests/conftest.py` 的用法。
"""

from __future__ import annotations

#: Ed25519 验签公钥（base64，``public_bytes_raw()``）。
#: 对应的私钥由供应商在签发环境保管，**不在本仓库、不在任何交付物内**。
BUILTIN_LICENSE_PUBLIC_KEY_B64 = "R5Q6Ab4q6cylp3RXRPBd/vbeIoCXvaOGEGdQFkiLyG4="
