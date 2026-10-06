"""License CLI（ADR-0006 §2.1：客户侧取机器指纹）。

离线签发流程的第 ① 步就是它：

```text
1. 客户装机 → 运行 license-cli fingerprint → 得到指纹（+ 组件明细）
2. 客户把指纹发给供应商（邮件 / 工单 —— **离线渠道**）
3. 供应商用【私钥】签发 .lic（含四维度 limits）
4. 供应商回传 .lic 文件
5. 客户放入 LICENSE_FILE_PATH 指向的路径 → 重载生效
```

⚠️ **本 CLI 刻意不提供"签发"子命令**：私钥只存在于签发环境（离线机器 / KMS），
**不出内网**（ADR-0006 §2.2 / R-L5）。把它做进交付物等于把签发能力交给客户。
"""

from __future__ import annotations

import argparse
import json

from app.services.license.fingerprint import component_detail, compute_fingerprint


def _cmd_fingerprint(args: argparse.Namespace) -> int:
    value = compute_fingerprint()
    if args.json:
        print(
            json.dumps(
                {"fingerprint": value, "components": component_detail()},
                ensure_ascii=False,
            )
        )
        return 0
    print(f"fingerprint: {value}")
    print("components:")
    for name, detail in component_detail().items():
        print(f"  - {name}: {detail}")
    print("\n把上面的 fingerprint 交给供应商签发 .lic；")
    print("组件明细用于核对「换了网卡要不要重签」。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="license-cli",
        description="License 离线运维工具（ADR-0006）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fingerprint = sub.add_parser(
        "fingerprint", help="输出本机机器指纹与组件明细（发给供应商签发 .lic）"
    )
    fingerprint.add_argument("--json", action="store_true", help="机器可读输出")
    fingerprint.set_defaults(func=_cmd_fingerprint)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
