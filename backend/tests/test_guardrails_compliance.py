"""DR-C1 / DR-B9 护栏：**G-23** / **G-24**。

两条都属于"整套子系统的存在性 + 行为"判据：

- **G-23**（DR-C1 License）：`licenses` 表 / `LicenseProvider` / **纯 ASGI** `LicenseMiddleware`
  / 6 个 `LICENSE_*` 错误码进契约 / `GET /license/status` / `license-cli fingerprint`，
  以及行为围栏——**移除 license 文件 ⇒ 受保护端点 403 `LICENSE_MISSING` 且拒绝落审计**。
- **G-24**（DR-B9 RBAC 三粒度）：**角色 × 资源 × 操作**矩阵 + 端点强制校验。

> ⚠️ **当前两者均零代码** ⇒ 断言必然失败 ⇒ XFAIL。ADR-0006（License）尚未落地、
> RBAC 又以前置的 `users` 表（DR-B13 / G-18）为先决条件。
> 骨架先就位的价值：把**验收判据钉死**，避免开工时把"写了点东西"当成"做完了"。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent

APP_ROOT = BACKEND_ROOT / "app"
SCRIPTS_ROOT = BACKEND_ROOT / "scripts"
MODELS = APP_ROOT / "db" / "models.py"
CONTRACT = REPO_ROOT / "contracts" / "openapi.yaml"

#: 遍历时必须跳过——``backend/.venv`` 有几千个文件，不排会拖垮整轮测试。
SKIP_DIRS = {
    ".venv",
    "__pycache__",
    "node_modules",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
}


def _load_tree(root: Path, suffix: str = ".py") -> dict[Path, str]:
    """读取目录下的全部源码，排开虚拟环境与缓存。"""
    sources: dict[Path, str] = {}
    for path in sorted(root.rglob(f"*{suffix}")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            sources[path] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return sources


def _any_match(sources: dict[Path, str], pattern: str) -> bool:
    rx = re.compile(pattern)
    return any(rx.search(text) for text in sources.values())


# --------------------------------------------------------------------------- #
# G-23：License 控制（DR-C1）
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason="G-23 / DR-C1：License 子系统零代码（ADR-0006 未落地），六项资产均不存在",
)
def test_g23_license_assets_exist() -> None:
    """DR-C1 完成判据的**静态侧**：六项资产必须齐备。

    六项缺一不可——缺 `LICENSE_*` 契约码前端就无法区分错误，缺 CLI 客户无法取指纹，
    缺 `LicenseProvider` 抽象就谈不上"可替换实现"。
    """
    app_sources = _load_tree(APP_ROOT)
    script_sources = _load_tree(SCRIPTS_ROOT)
    models_src = MODELS.read_text(encoding="utf-8")
    contract_src = CONTRACT.read_text(encoding="utf-8")

    missing: list[str] = []

    if not re.search(r"class\s+License\b", models_src):
        missing.append("`licenses` 表（models.py 无 class License）")

    if not _any_match(app_sources, r"class\s+\w*LicenseProvider\b"):
        missing.append("`LicenseProvider` 抽象与其实现")

    if _any_match(app_sources, r"LicenseMiddleware\s*\(\s*BaseHTTPMiddleware"):
        missing.append(
            "`LicenseMiddleware` 继承了 BaseHTTPMiddleware——"
            "ADR-0006 要求**纯 ASGI**（P95 增量 < 1ms 的前提）"
        )
    elif not _any_match(app_sources, r"class\s+LicenseMiddleware\b"):
        missing.append("`LicenseMiddleware`（纯 ASGI，每请求校验）")

    codes = set(re.findall(r"\bLICENSE_[A-Z_]+\b", contract_src))
    if len(codes) < 6:
        missing.append(f"契约中的 LICENSE_* 错误码不足 6 个（当前 {len(codes)} 个）")

    if "/license/status" not in contract_src and not _any_match(
        app_sources, r"/license/status"
    ):
        missing.append("`GET /license/status` 端点")

    if not _any_match(script_sources, r"\bfingerprint\b"):
        missing.append("`license-cli fingerprint`（客户侧取机器指纹）")

    assert not missing, (
        "License 子系统资产不齐（DR-C1 / ADR-0006）：\n  - " + "\n  - ".join(missing)
    )


@pytest.mark.xfail(
    strict=True,
    reason="G-23 / DR-C1：License 子系统零代码，移除 license 后的行为围栏无从建立",
)
def test_g23_missing_license_blocks_requests() -> None:
    """DR-C1 完成判据的**行为侧**：移除 license 文件 ⇒ 受保护端点 **403 `LICENSE_MISSING`**。

    同时要求**拒绝必须落审计**——否则客户到期后打不开系统，而我们拿不出证据说明是
    License 到期而非系统故障（排障会被误导）。
    """
    try:
        from app.core.middleware import LicenseMiddleware  # noqa: F401
    except ImportError as exc:  # pragma: no cover - 有实现后不再走到这里
        pytest.fail(f"LicenseMiddleware 不存在：{exc}")

    pytest.fail(
        "已存在 LicenseMiddleware 类，但尚未接入移除 license 后的 403 / 审计断言占位——"
        "请在本条补全端到端行为断言并摘掉 xfail"
    )


# --------------------------------------------------------------------------- #
# G-24：RBAC 三粒度（DR-B9）
# --------------------------------------------------------------------------- #


@pytest.mark.xfail(
    strict=True,
    reason=("G-24 / DR-B9：RBAC 未落地，且前置的 `users` 表（DR-B13 / G-18）尚未建立"),
)
def test_g24_rbac_three_granularity_matrix() -> None:
    """角色 × 资源 × 操作 三粒度矩阵必须**存在且端点强制校验**。

    只建角色表不算 RBAC——**端点不强制校验**的话，权限就只是数据库里的一列装饰。
    因此本条同时断言：存在矩阵定义，且路由层有**统一的强制入口**（依赖 / 中间件）。
    """
    app_sources = _load_tree(APP_ROOT)
    models_src = MODELS.read_text(encoding="utf-8")

    missing: list[str] = []

    if not re.search(r"class\s+User\b", models_src):
        missing.append(
            "`users` 表（DR-B13 / G-18 前置，SSO / RBAC / License 席位三者共同依赖）"
        )

    if not _any_match(app_sources, r"(class|enum)\s+\w*Role\w*\b"):
        missing.append("角色定义（Role 枚举 / 常量）")

    if not _any_match(app_sources, r"(permission|Permission|PERMISSION)"):
        missing.append("权限定义（permission）")

    # 「资源 × 操作」矩阵：至少要有成对的 {(subject|resource), (action|operation)} 表述
    if not _any_match(
        app_sources, r"(?=.*\b(resource|subject)\b)(?=.*\b(action|operation)\b)"
    ):
        missing.append("资源 × 操作 维度（缺一格就不是三粒度）")

    if not _any_match(app_sources, r"(Depends\(|require_perm|enforce_rbac)"):
        missing.append("路由层的**强制校验入口**（依赖 / 中间件）——否则矩阵形同虚设")

    assert not missing, "RBAC 三粒度未达标（DR-B9）：\n  - " + "\n  - ".join(missing)
