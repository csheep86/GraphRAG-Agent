"""G-15 补丁期契约冻结：版本判定逻辑。

``scripts/check_patch_contract_freeze.py`` 的 git 部分只能在真实 CI 的 PR 场景
下验证，这里只测**纯逻辑**（版本解析 + PATCH 判定）——它们是整条判据的地基：
判错了"什么算补丁"，后面全部结论都是错的。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "check_patch_contract_freeze.py"
)


def _load_module() -> object:
    """按文件路径加载脚本——``scripts/`` 不是包，无法直接 import。"""
    spec = importlib.util.spec_from_file_location("check_patch_contract_freeze", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def freeze() -> object:
    return _load_module()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.6.0", (1, 6, 0)),
        ("1.6.1", (1, 6, 1)),
        ("2.0.0", (2, 0, 0)),
        ("1.6", None),  # 两段式 ⇒ 判不出 PATCH
        ("v1.6.0", None),  # 带前缀
        ("1.6.0-beta", None),  # 预发布后缀
        ("", None),
        (None, None),
    ],
)
def test_parse_version(freeze: object, raw: str | None, expected: tuple | None) -> None:
    assert freeze.parse_version(raw) == expected  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ((1, 6, 0), (1, 6, 1), True),  # 标准补丁
        ((1, 6, 0), (1, 7, 0), False),  # MINOR：允许改契约
        ((1, 6, 0), (2, 0, 0), False),  # MAJOR：插件重做，不适用本条
        ((1, 6, 0), (1, 6, 0), False),  # 没 bump ⇒ 不是补丁变更
        ((1, 6, 1), (1, 6, 0), False),  # PATCH 回退，不是"递增"
        ((1, 9, 0), (2, 0, 0), False),
        (None, (1, 6, 1), False),  # 取不到基准版本 ⇒ 不适用
        ((1, 6, 0), None, False),
    ],
)
def test_is_patch_bump(
    freeze: object, old: tuple | None, new: tuple | None, expected: bool
) -> None:
    assert freeze.is_patch_bump(old, new) is expected  # type: ignore[attr-defined]


def test_app_version_regex_matches_real_config(freeze: object) -> None:
    """**防假护栏**：正则必须从真实的 ``config.py`` 里取出版本号。

    首版正则写作 ``^app_version``（要求顶格），而该字段是 ``Settings`` 的**类内**
    字段、必然带缩进 ⇒ 取不到值 ⇒ 脚本恒判"不适用"退 0 ⇒ **整条 G-15 从未生效过**。
    这与 G-2 那条教训同款：门禁悄悄退化成恒绿，比没有门禁更危险。
    """
    raw = freeze.app_version_at("HEAD")  # type: ignore[attr-defined]
    assert raw, (
        "从 HEAD 的 backend/app/core/config.py 取不到 app_version ——"
        "脚本会恒判「不适用」而退 0，G-15 等于没在拦"
    )
    assert freeze.parse_version(raw) is not None  # type: ignore[attr-defined]


def test_current_app_version_is_three_segment(freeze: object) -> None:
    """当前版本必须是三段式——否则 G-11 / G-15 都无从比对。

    这是 §7 版本语义的可执行投影：`base_version` = MAJOR 段。
    """
    from app.core.config import get_settings

    parsed = freeze.parse_version(get_settings().app_version)  # type: ignore[attr-defined]
    assert parsed is not None, (
        f"app_version={get_settings().app_version!r} 不是 MAJOR.MINOR.PATCH，"
        "版本语义（需求基线 §7）无法落地，G-11 / G-15 均无从比对"
    )
    assert parsed[0] >= 1, "MAJOR 段（= base_version）必须 ≥ 1"
