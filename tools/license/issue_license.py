"""供应商侧 License 签发工具（**内部专用，禁止随交付物分发**）。

> ⚠️ **为什么它不放在 `backend/scripts/`**：`backend/Dockerfile:39` 有一行
> `COPY backend/scripts ./scripts` ⇒ 那个目录会**整体进交付镜像**。
> 把签发能力交给客户，等于让他可以为自己签一份 License（配合可替换的验签公钥，
> 整套机器绑定即告失效）。实验记录见 `changes/P6-Z/proposal.md` **§0.2.1**。
>
> ⇒ 因此本工具放在仓库根的 `tools/license/`，**不参与任何镜像构建**，
> 并由 `backend/tests/test_license_guardrails.py` 机械断言"交付物内不含签发能力"。

ADR-0006 **R-L5**：「私钥不出签发环境（离线 / KMS），**公钥内置**；泄露需轮换公钥（= 发新版）」
⇒ 私钥**只以文件路径**喂给本工具，不读环境变量、不打印、不入日志、不入库。

用法（依赖 `cryptography`，可用后端的虚拟环境）::

    # 1) 生成密钥对：私钥落到 ~/.graphrag-license/private.pem（600），公钥打印到 stdout
    python tools/license/issue_license.py genkey

    # 2) 查看某把私钥对应的公钥（只输出公钥，绝不出私钥）
    python tools/license/issue_license.py pubkey --private-key-file <path>

    # 3) 为客户机器签发：指纹由客户侧 `license-cli fingerprint` 取回后提供
    python tools/license/issue_license.py issue \\
        --private-key-file <path> \\
        --fingerprint <客户机器指纹> \\
        --customer "客户名称" \\
        --not-after 2027-12-31T00:00:00Z \\
        --max-orgs 5 --max-seats 50 \\
        --out <客户名>.lic
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import stat
import sys
import uuid
from pathlib import Path
from typing import Any, Sequence

PRODUCT = "graphrag-agent"
SCHEMA_VERSION = 1
DEFAULT_KEY_DIR = Path.home() / ".graphrag-license"
DEFAULT_MODULES: tuple[str, ...] = (
    "connectors",
    "m1_ingest",
    "m2_extract",
    "m3_graphqa",
    "m4_affiliation",
    "m5_permission",
    "m6_ontology",
)


# --------------------------------------------------------------------------- #
# 密钥
# --------------------------------------------------------------------------- #
def _import_ed25519() -> Any:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "缺少 cryptography 依赖。可用后端虚拟环境运行：\n"
            "  backend/.venv/Scripts/python.exe tools/license/issue_license.py ..."
        ) from exc
    return ed25519, serialization


def _write_private_key(path: Path, pem: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pem)
    # POSIX 上收紧权限；Windows 无 chmod 语义，故做 best-effort 并提示手工处理。
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except (NotImplementedError, PermissionError):
        print(f"[warn] 无法收紧 {path} 的权限，请手工限制为仅本人可读", file=sys.stderr)


def cmd_genkey(args: argparse.Namespace) -> int:
    ed25519, serialization = _import_ed25519()
    private_key = ed25519.Ed25519PrivateKey.generate()

    priv_path = args.private_key_file
    _write_private_key(
        priv_path,
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
    pub_b64 = base64.b64encode(private_key.public_key().public_bytes_raw()).decode()
    pub_path = args.public_key_file
    pub_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.write_text(pub_b64 + "\n", encoding="utf-8")

    print(f"private_key_file={priv_path}")
    print(f"public_key_file={pub_path}")
    print(f"public_key_b64={pub_b64}")
    print()
    print("⚠️ 私钥**必须**离线保管（密码管理器 / KMS）；它一旦泄露，")
    print("   攻击者就能签发任意 License，届时只能轮换公钥（= 发新版）。")
    return 0


def cmd_pubkey(args: argparse.Namespace) -> int:
    ed25519, serialization = _import_ed25519()
    private_key = serialization.load_pem_private_key(
        args.private_key_file.read_bytes(), password=None
    )
    if not isinstance(private_key, ed25519.Ed25519PrivateKey):
        raise SystemExit("私钥不是 Ed25519")
    print(base64.b64encode(private_key.public_key().public_bytes_raw()).decode())
    return 0


# --------------------------------------------------------------------------- #
# 签发
# --------------------------------------------------------------------------- #
def canonical(body: dict[str, Any]) -> bytes:
    """与 `provider._verify` / `conftest.py` **逐字一致**的确定性序列化。

    改这里 = 所有已签发 License 立即失效 ⇒ 属于 `changes/P6-Z/proposal.md` §1 第 1 条禁止事项。
    """
    return json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def cmd_issue(args: argparse.Namespace) -> int:
    ed25519, serialization = _import_ed25519()

    if not args.fingerprint.strip():
        raise SystemExit(
            "--fingerprint 不可为空：License 必须绑定到**具体机器**；\n"
            "空白指纹会签出一份到处可用的万能 License。"
        )

    private_key = serialization.load_pem_private_key(
        args.private_key_file.read_bytes(), password=None
    )
    if not isinstance(private_key, ed25519.Ed25519PrivateKey):
        raise SystemExit("私钥不是 Ed25519")

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    body: dict[str, Any] = {
        "license_id": args.license_id or str(uuid.uuid4()),
        "schema_version": SCHEMA_VERSION,
        "product": PRODUCT,
        "customer": args.customer,
        "fingerprint": args.fingerprint.strip(),
        "issued_at": args.issued_at or now.replace("+00:00", "Z"),
        "not_before": args.not_before or now.replace("+00:00", "Z"),
        "not_after": args.not_after,
        "grace_days": args.grace_days,
        "limits": {"max_orgs": args.max_orgs, "max_seats": args.max_seats},
        "modules": args.modules,
    }
    signature = base64.b64encode(private_key.sign(canonical(body))).decode()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({**body, "signature": signature}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"issued={args.out}")
    print(f"license_id={body['license_id']}")
    print(f"fingerprint={body['fingerprint']}")
    print(f"not_after={body['not_after']}")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="issue-license",
        description="供应商侧 License 签发工具（内部专用，禁止交付）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    genkey = sub.add_parser("genkey", help="生成 Ed25519 密钥对")
    genkey.add_argument(
        "--private-key-file",
        type=Path,
        default=DEFAULT_KEY_DIR / "private.pem",
        help=f"私钥 PEM 落点（默认 {DEFAULT_KEY_DIR / 'private.pem'}）",
    )
    genkey.add_argument(
        "--public-key-file",
        type=Path,
        default=DEFAULT_KEY_DIR / "public.b64",
        help="公钥 base64 落点",
    )
    genkey.set_defaults(func=cmd_genkey)

    pubkey = sub.add_parser("pubkey", help="从私钥导出公钥 base64（绝不出私钥）")
    pubkey.add_argument("--private-key-file", type=Path, required=True)
    pubkey.set_defaults(func=cmd_pubkey)

    issue = sub.add_parser("issue", help="签发一份 License")
    issue.add_argument("--private-key-file", type=Path, required=True)
    issue.add_argument(
        "--fingerprint",
        required=True,
        help="客户机器的指纹（由客户侧 license-cli fingerprint 提供）",
    )
    issue.add_argument("--customer", required=True, help="客户名称")
    issue.add_argument(
        "--not-after", required=True, help="到期时间，ISO-8601，如 2027-12-31T00:00:00Z"
    )
    issue.add_argument("--max-orgs", type=int, default=5)
    issue.add_argument("--max-seats", type=int, default=50)
    issue.add_argument(
        "--modules",
        nargs="+",
        default=list(DEFAULT_MODULES),
        help="授权的模块清单",
    )
    issue.add_argument("--license-id", help="不填则自动生成 UUID")
    issue.add_argument("--issued-at")
    issue.add_argument("--not-before")
    issue.add_argument("--grace-days", type=int, default=30)
    issue.add_argument("--out", type=Path, required=True, help="输出 .lic 路径")
    issue.set_defaults(func=cmd_issue)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
