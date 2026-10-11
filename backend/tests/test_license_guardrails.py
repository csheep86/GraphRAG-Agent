"""License 安全护栏（**P6-Z / F-P6Z-1**：公钥必须内置、签发能力不得交付）。

这些都是**静态可判**的不变量，为什么值得单独立一个文件：

- 它们不是"功能"，而是**曾经被违反过、并且当时没有任何东西拦住**的约束。
  P6-Y 为了让现场能装上而把公钥改成 `.env` 可配；P6-Z 实测发现那等于
  「客户换一把公钥 + 自签 ⇒ 拿到永久全量 License」（见 §0.2.1 的四步攻击）。
- 这些约束一旦被改回去，**症状是零**：系统照常跑、测试全绿，只是反盗版没了。
  ⇒ 只能靠机械断言盯住，**不能靠人记得**。

判据全部读文件 / 读模块，**不需要 docker、不需要起服务**。
"""

from __future__ import annotations

import base64
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

DELIVERY_COMPOSE = ROOT / "deploy" / "docker-compose.delivery.yml"
DELIVERY_ENV_EXAMPLE = ROOT / "deploy" / ".env.example"
BACKEND_ENV_EXAMPLE = ROOT / "backend" / ".env.example"
BACKEND_DOCKERFILE = ROOT / "backend" / "Dockerfile"
BACKEND_SCRIPTS = ROOT / "backend" / "scripts"
CONFIG_PY = ROOT / "backend" / "app" / "core" / "config.py"

#: 配置项形式的公钥（形如 ``KEY=``）：文档 / 注释里**允许**提到这个名字
#: （历史沿革要说清楚），但不允许存在一个**可被赋值的配置项**。
_CONFIG_ITEM_RE = re.compile(r"(?m)^\s*LICENSE_PUBLIC_KEY\s*=", re.MULTILINE)


def test_no_public_key_config_item_in_delivery_template() -> None:
    """现场模板里**不得**存在可赋值的 `LICENSE_PUBLIC_KEY` 配置项。"""
    for path in (DELIVERY_ENV_EXAMPLE, BACKEND_ENV_EXAMPLE):
        text = path.read_text(encoding="utf-8")
        assert not _CONFIG_ITEM_RE.search(text), (
            f"{path.name} 又出现了可配置的 `LICENSE_PUBLIC_KEY` —— "
            "一旦可配，客户就能换成自己的公钥并自签 License（P6-Z §0.2.1 实测四步走通）"
        )


def test_delivery_compose_injects_no_public_key() -> None:
    """交付 compose 的 `environment:` 里不得注入公钥。"""
    text = DELIVERY_COMPOSE.read_text(encoding="utf-8")
    assert "LICENSE_PUBLIC_KEY:" not in text, (
        "交付 compose 又在注入 `LICENSE_PUBLIC_KEY` ⇒ 等于把验签公钥交回给 `.env` "
        "（P6-Z §0.2.1 实测：可替换的公钥 + 自签 ⇒ 机器绑定失效）"
    )


def test_settings_has_no_public_key_field() -> None:
    """`Settings` 不得再有 `license_public_key` 字段（防止悄悄加回配置面）。"""
    text = CONFIG_PY.read_text(encoding="utf-8")
    assert "license_public_key" not in text, (
        "Settings 里又出现了 `license_public_key` —— 公钥必须只存在于 "
        "`app/services/license/public_key.py` 的常量（ADR-0006 R-L5「公钥内置」）"
    )


def test_builtin_public_key_is_a_valid_ed25519_key() -> None:
    """内置公钥必须**非空且可被 Ed25519 解析**（32 字节裸公钥）。"""
    from cryptography.hazmat.primitives.asymmetric import ed25519

    from app.services.license.public_key import BUILTIN_LICENSE_PUBLIC_KEY_B64

    raw = BUILTIN_LICENSE_PUBLIC_KEY_B64.strip()
    assert raw, "内置验签公钥为空 ⇒ 所有 License 一律验签失败（业务全 403）"

    key = ed25519.Ed25519PublicKey.from_public_bytes(
        base64.b64decode(raw, validate=True)
    )
    assert len(key.public_bytes_raw()) == 32, "不是合法的 Ed25519 裸公钥（应为 32 字节）"


def test_signing_capability_is_not_packaged() -> None:
    """签发能力不得随交付物分发：`tools/` 不进镜像，`backend/scripts/` 不得含签发实现。

    依据：`backend/Dockerfile` 有一行 `COPY backend/scripts ./scripts`
    ⇒ 那个目录**整体进交付镜像**；签发工具若落在其中，客户就同时拥有
    「可替换的公钥」与「签发能力」。
    """
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    copied = re.findall(r"(?m)^\s*COPY\s+(\S+)", dockerfile)
    assert not any(part.startswith("tools") for part in copied), (
        f"Dockerfile 开始 COPY tools/ 了：{copied} ⇒ 签发工具会随镜像交付给客户"
    )
    scripts = list(BACKEND_SCRIPTS.glob("*.py"))
    offenders = [
        p.name
        for p in scripts
        if re.search(r"(?i)\b(issue|genkey|sign)\b", p.stem)
        or "Ed25519PrivateKey.generate" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        f"`backend/scripts/` 出现了签发相关能力：{offenders}。"
        "该目录会被整体 COPY 进交付镜像 ⇒ 等于把签发能力交给客户。"
        "签发请走 `tools/license/`（不参与镜像构建）。"
    )


def test_no_private_key_material_in_repo() -> None:
    """仓库内不得出现私钥文件（测试用的**进程内**临时密钥是唯一例外）。"""
    offenders: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {"node_modules", ".venv", ".git"} for part in path.parts):
            continue
        if path.suffix.lower() in {".pem", ".key"} or (
            path.name.lower().startswith("private") and path.suffix == ""
        ):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"仓库内出现疑似私钥文件：{offenders}。"
        "私钥按 ADR-0006 R-L5 必须留在签发环境（离线 / KMS），不得入库。"
    )


@pytest.mark.parametrize(
    "relative",
    ["tools/license/issue_license.py", "tools/license/README.md"],
)
def test_supplier_tooling_exists_and_is_outside_image(relative: str) -> None:
    """供应商侧签发工具应当存在（否则换机重签无工具可执行），且在镜像之外。"""
    assert (ROOT / relative).is_file(), f"缺少 {relative}"
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "tools/license" not in dockerfile, (
        "Dockerfile 里出现了 tools/license ⇒ 签发工具会被打进交付镜像"
    )
