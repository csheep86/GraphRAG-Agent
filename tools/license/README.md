# 供应商侧 License 签发工具（`issue_license.py`）

> 🔒 **本目录属于内部签发，禁止随任何交付物分发。**
>
> 原因记录在 [`changes/P6-Z/proposal.md`](../../changes/P6-Z/proposal.md) §0.2.1：
> 一旦客户同时拥有「签发能力」与「可替换的验签公钥」，
> 就可以为自己签一份 License —— **机器绑定随之失效**（实测已跑通：`has_license=true`、额度全开）。
> 而 `backend/Dockerfile:39` 的 `COPY backend/scripts ./scripts` 会把 `backend/scripts/`
> **整体打进交付镜像** ⇒ 本工具**绝不**放在那个目录下。

## 为什么在仓库根

| 要求 | 由什么保证 |
|---|---|
| 不进交付镜像 | 镜像构建只 COPY `backend/app`、`backend/scripts`、`backend/migrations`、`plugins`；本目录不在其中 |
| 不进离线 tar | `build_delivery_images.py` 只 `docker save` 自研镜像 |
| 不出现在 `deploy/` 交付模板 | `deploy/` 没有任何私钥 / 签发配置项 |
| 上述三条**不被改回去** | `backend/tests/test_license_guardrails.py` 的机械断言（See below） |

## 运行方式

依赖 `cryptography`（后端已装）。用后端的虚拟环境跑最省事：

```bash
# Windows
backend\.venv\Scripts\python.exe tools\license\issue_license.py --help

# POSIX
backend/.venv/bin/python tools/license/issue_license.py --help
```

## 标准流程（离线）

```text
① 客户装好之后运行：license-cli fingerprint        → 得到本机指纹
② 客户把指纹通过离线渠道（邮件 / 工单）发给供应商
③ 供应商在**签发环境**跑本工具：genkey（仅首次）/ issue
④ 供应商把 .lic 回传给客户
⑤ 客户放入 LICENSE_FILE_PATH 指向的路径 → 重载生效
```

> **换机 / 重装 ⇒ 必须重走一遍 ①-⑤**（`docs/deployment-spec.md` §6.1 约束 3）：
> 指纹锚定宿主机，机器换了指纹就变了。

## 命令

```bash
# 生成密钥对（**只做一次**）。私钥落到 ~/.graphrag-license/private.pem（Unix 下 600）
python tools/license/issue_license.py genkey

# 导出公钥 base64（用于核对配置；本工具在任何子命令下都不会输出私钥）
python tools/license/issue_license.py pubkey --private-key-file ~/.graphrag-license/private.pem

# 签发
python tools/license/issue_license.py issue \
  --private-key-file ~/.graphrag-license/private.pem \
  --fingerprint <客户指纹> \
  --customer "客户名称" \
  --not-after 2027-12-31T00:00:00Z \
  --max-orgs 5 --max-seats 50 \
  --out <客户名>.lic
```

`--fingerprint` **不允许为空** —— 空指纹会签出一份到处可用的万能 License。

## 私钥保管（ADR-0006 R-L5）

- 私钥**不出签发环境**（离线机 / KMS）；本仓库内**不允许**出现私钥文件（测试用的
  `backend/tests/conftest.py` 是**进程内临时生成**的例外，不入磁盘也不入库）；
- 泄露 ⇒ 只能轮换公钥，而按 R-L5 的约定，**轮换公钥 = 发新版**（公钥是内置进代码的）。
