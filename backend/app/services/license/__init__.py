"""接缝 9：License 控制（**DR-C1** / **G-23** / ADR-0006）。

**职责边界**（ADR-0006 §4）：本包是 ``LicenseProvider`` 的**唯一收口点**，
当前**唯一实现** :class:`app.services.license.provider.DevLicenseProvider`
（``max_impls = 1``，登记真源在 ADR-0006 §4，由 ``scripts/check_seams.py`` 机械核对）。

⚠️ **这不是安全边界**：ADR-0006 §2.8 / §6 R-L2 明写 —— **不承诺防破解**。
指纹可被克隆镜像或篡改绕过；真正的隔离边界是 **ADR-0003 的 RLS**。
License 是**合规门槛**。凡是“靠 License 防攻击”的说法都不成立。
"""

from __future__ import annotations

from app.services.license.provider import DevLicenseProvider, LicenseProvider

__all__ = ["DevLicenseProvider", "LicenseProvider"]
