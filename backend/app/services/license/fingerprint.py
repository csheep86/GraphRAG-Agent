"""机器指纹（ADR-0006 §2.1）。

三条硬性要求决定了这里的实现形态：

1. **采集源只取稳定硬件信息** —— OS 机器标识 / 主板 / CPU 稳定标识 / 主网卡 MAC；
   ``/etc/machine-id`` 优先，Windows 走注册表 ``MachineGuid``，取不到再回落到 MAC。
2. **明令禁止采集** IP 地址（易变）、磁盘序列号（云主机 / 虚拟盘易变）、
   **任何个人信息**（合规）⇒ 这里**不读**主机名以外的账号类信息。
3. 归一化后**排序拼接** + salt → ``SHA-256`` → 截断 **32 位 hex**。

⚠️ **已知能力缺口（如实登记，不粉饰）**：ADR §2.1 的「组件交集 ≥ 2/3 视为同一台机器」
是**换网卡 / 重装不误拒**的关键，但它要求 license 里保存**每个组件**的明细；
而 ADR §2.2 的字段清单里 ``fingerprint`` **只有一个聚合值**（无 components）。
⇒ 本实现只能做**全等比较**：断口多云 massacre 的实时容忍度**当前无法落地**，
只能靠重新签发 + ``LICENSE_FP_OVERRIDE`` 兜底（ADR R-L1 的缓解路径之一）。
该缺口不由此批声称解决。
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from app.core.config import get_settings

#: 指纹长度（hex 字符数）—— ADR §2.1 定为 32
FINGERPRINT_LEN = 32

#: 本机 Windows 注册表路径（Linux 走 /etc/machine-id）
_WIN_MACHINE_GUID_KEY = r"SOFTWARE\Microsoft\Cryptography"
_WIN_MACHINE_GUID_VALUE = "MachineGuid"


def collect_components() -> tuple[str, ...]:
    """采集稳定的机器标识组件（**去重后返回**，顺序不定 ⇒ 调用方负责排序）。

    采集**不做网络回调**（ADR §2.3 选型判据 ③），且**绝不采集 IP / 磁盘序列号 /
    个人信息**（§2.1「禁止采集」）。取不到就是取不到，**不编造**（否则换机就误拒）。
    """
    components: list[str] = []

    machine_id = _read_machine_id()
    if machine_id:
        components.append(f"machine-id:{machine_id}")

    mac = _primary_mac()
    if mac:
        components.append(f"mac:{mac}")

    board = _stable_board_or_cpu()
    if board:
        components.append(f"host:{board}")

    return tuple(dict.fromkeys(components))


def compute_fingerprint() -> str:
    """计算本机指纹（32 位 hex）。

    ⚠️ **刻意未实现**：ADR §2.1 允许的 ``LICENSE_FP_OVERRIDE`` 显式覆盖路径本批**不做** ——
    它附带的义务是「必须落 ``license.fp_override`` 审计」（§2.1 原文）。    提供一个**没有配套审计义务落实**的旋钮，就是典型的假做（预留纪律第 6 条）；
    该缺口及其必要性登记在 ``changes/P4/integration-log.md`` §2.4。
    """
    settings = get_settings()
    return build_fingerprint(collect_components(), salt=settings.license_fp_salt)


def build_fingerprint(components: tuple[str, ...], *, salt: str) -> str:
    """归一化：小写、去分隔符 → **排序拼接** → 加 salt → SHA-256 → 截断 32 位 hex。

    ``components`` 是传来的一项日本地位的原始串；这里只做确定性归一化，不重新采集。
    """
    normalized = sorted(
        "".join(part for part in item.lower() if part.isalnum())
        for item in components
        if item
    )
    digest = hashlib.sha256(f"{salt}|{'|'.join(normalized)}".encode())
    return digest.hexdigest()[:FINGERPRINT_LEN]


def component_detail() -> dict[str, str]:
    """给 CLI 用的组件明细（供客户核对「换了网卡要不要重签」）。"""
    return {
        item.split(":", 1)[0]: item.split(":", 1)[1] for item in collect_components()
    }


# --------------------------------------------------------------------------- internals


def _read_machine_id() -> str:
    """Linux ``/etc/machine-id`` → Windows 注册表 ``MachineGuid``。"""
    machine_id_path = Path("/etc/machine-id")
    try:
        value = machine_id_path.read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    if value:
        return value
    return _windows_machine_guid()


def _windows_machine_guid() -> str:
    try:
        import winreg  # noqa: PLC0415 - 仅 Windows 可用
    except ImportError:
        return ""
    try:
        with winreg.OpenKey(  # type: ignore[attr-defined]
            winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
            _WIN_MACHINE_GUID_KEY,
        ) as key:
            value, _ = winreg.QueryValueEx(key, _WIN_MACHINE_GUID_VALUE)  # type: ignore[attr-defined]
    except OSError:
        return ""
    return str(value).strip()


def _primary_mac() -> str:
    """主网卡 MAC（``xx:xx:xx:xx:xx:xx``）；取不到 / 拿到的是随机值 ⇒ **返回空串**。

    刻意**不引入新依赖**：``uuid.getnode()`` 是 stdlib 里唯一稳定的取法。
    注意它在拿不到真实 MAC 时会**随机造一个**（首字节末位 = 多播位为 1），
    那种值必须判为「取不到」—— 否则同一份代码在不同机器上会算出**同一个指纹**，
    License 的机器绑定就彻底失效了。
    """
    mac_int = uuid.getnode()
    if (mac_int >> 40) & 0b1:  # 多播位为 1 ⇒ 是 stdlib 随机造的，不是真实网卡
        return ""
    mac = ":".join(f"{(mac_int >> shift) & 0xFF:02x}" for shift in range(40, -1, -8))
    return "" if mac == "00:00:00:00:00:00" else mac


def _stable_board_or_cpu() -> str:
    """主板 / CPU 稳定标识；取不到即空（不编造）。"""
    try:
        board = Path("/sys/class/dmi/id/product_uuid")
        if board.exists():
            value = board.read_text(encoding="utf-8").strip().lower()
            if value:
                return value
    except OSError:
        pass
    return ""
