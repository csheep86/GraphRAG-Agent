"""机器指纹的**组件策略**护栏（F-P6Y-2 / F-P6Y-3）。

这两条是在 P6-Y 的 T1 实跑里挖出来的，此前**没有任何用例盯住**：

- **F-P6Y-2**：容器化交付下，容器内 `/etc/machine-id` 与 `product_uuid` 都取不到
  ⇒ 组件集合退化成**只剩容器网卡 MAC**，而容器每次重建都换 MAC ⇒ **指纹变**
  ⇒ 客户每次 `docker compose up -d` 之后 License 都要重新签发。
- **F-P6Y-3**：ADR §2.1 原文是「machine-id 优先，取不到**再回落**到 MAC」，
  旧实现却把 MAC **无条件计入** ⇒ 与 ADR 不一致，且直接导致 F-P6Y-2。

⇒ 本文件只钉住**组件策略**这一件事（不碰验签、不碰有效期）：

1. machine-id 取得到 ⇒ MAC **不参与** ⇒ 换 MAC 不改指纹（容器重建不失效）；
2. machine-id 取不到 ⇒ MAC 才作为回落参与（ADR §2.1 原文口径）。

判据全部用 `monkeypatch` 换掉采集源，**不依赖真实机器**，可在 CI 稳定复现。
"""

from __future__ import annotations

import pytest

from app.services.license import fingerprint as fp_module
from app.services.license.fingerprint import (
    collect_components,
    compute_fingerprint,
)

_MACHINE_ID = "208c9ebe76b44a14b97149e300502066"


@pytest.fixture
def with_machine_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """容器**挂了宿主 machine-id** 的形态：machine-id 取得到、主板标识取不到。"""
    monkeypatch.setattr(fp_module, "_read_machine_id", lambda: _MACHINE_ID)
    monkeypatch.setattr(fp_module, "_stable_board_or_cpu", lambda: "")


def test_mac_is_excluded_when_machine_id_is_available(
    with_machine_id: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR §2.1：MAC 是 machine-id 的**回落**，不是并列项。

    旧实现无条件 append MAC ⇒ 容器内只剩 MAC ⇒ 重建容器即换指纹（F-P6Y-2）。
    """
    monkeypatch.setattr(fp_module, "_primary_mac", lambda: "fe:f1:1f:8a:79:e9")

    assert collect_components() == (f"machine-id:{_MACHINE_ID}",)


def test_fingerprint_survives_container_recreate(
    with_machine_id: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """**F-P6Y-2 的核心判据**：容器重建只换 MAC，指纹必须**不变**。

    实测（2026-10-10）重建前后 mac 由 `fe:f1:1f:8a:79:e9` 变成 `32:f6:e8:3f:9a:1e`；
    在旧实现下 fp 随之从 `9bc9c9c2…` 变成 `5c125f42…` ⇒ License 失效。
    """
    macs = iter(["fe:f1:1f:8a:79:e9", "32:f6:e8:3f:9a:1e"])
    monkeypatch.setattr(fp_module, "_primary_mac", lambda: next(macs))

    before = compute_fingerprint()
    after = compute_fingerprint()

    assert before == after, "容器重建换了 MAC 就换指纹 ⇒ 每次 up -d 都要重签 License"


def test_mac_is_the_fallback_when_machine_id_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """machine-id 取不到 ⇒ 才用 MAC 兜底（ADR §2.1 原文口径，不许反向改宽）。"""
    monkeypatch.setattr(fp_module, "_read_machine_id", lambda: "")
    monkeypatch.setattr(fp_module, "_stable_board_or_cpu", lambda: "")
    monkeypatch.setattr(fp_module, "_primary_mac", lambda: "aa:bb:cc:dd:ee:ff")

    assert collect_components() == ("mac:aa:bb:cc:dd:ee:ff",)


def test_board_component_is_collected_alongside_machine_id(
    with_machine_id: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """主板 / CPU 标识（宿主机可读时）照旧参与 —— 本批**只**改 MAC 的定位。"""
    monkeypatch.setattr(fp_module, "_stable_board_or_cpu", lambda: "board-uuid-0001")

    components = collect_components()

    assert components == (f"machine-id:{_MACHINE_ID}", "host:board-uuid-0001")
