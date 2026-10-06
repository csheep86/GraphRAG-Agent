"""`GET /api/v1/license/status`——ADR-0006 §2.6 要求的**自检端点**。

**它的意义**：离线部署的客户拿到一份无效 License 时，最贵的是"不知道为什么不能用"。
所以这个端点与 ``/health`` 一样被 :class:`LicenseMiddleware` **豁免** ——
即使 License 全量拒绝，它也必须可访问。

**它不返回什么**：不返回 ``raw_payload`` / ``signature`` / 公钥。
前端拿到这些没有合法用途，只会变成泄漏面（契约纯净纪律）。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import TraceId
from app.core.config import get_settings
from app.schemas.license import LicenseLimits, LicenseStatusResponse
from app.services.license.provider import get_license_provider

router = APIRouter(tags=["license"])


@router.get(
    "/license/status",
    response_model=LicenseStatusResponse,
    operation_id="getLicenseStatus",
    summary="License 状态自检（豁免 License 拦截）",
    description=(
        "返回当前License 的加载状态与授权维度，**不返回**签名 / 正文 / 公钥。\n\n"
        "**为什么它必须豁免**：无有效 License 时全站已拒绝受保护端点；"
        "若自检端点也被拦，客户现场就无法判断是 License 过期还是系统故障，"
        "排障会被彻底误导。\n\n"
        "`has_license=false` 时看 `code` 字段即可定位原因"
        "（`LICENSE_MISSING` / `LICENSE_INVALID` / `LICENSE_FINGERPRINT_MISMATCH` "
        "/ `LICENSE_EXPIRED` / `LICENSE_LIMIT_EXCEEDED` / `LICENSE_MODULE_DISABLED`）。"
    ),
)
async def get_license_status(trace_id: TraceId) -> LicenseStatusResponse:
    settings = get_settings()
    state = get_license_provider().current_state()
    return LicenseStatusResponse(
        has_license=state.ok,
        enforced=settings.license_enforce,
        code=state.code,
        license_id=state.license_id,
        status=state.status,
        in_grace=state.in_grace,
        not_before=state.not_before,
        not_after=state.not_after,
        grace_days=state.grace_days,
        limits=LicenseLimits(max_orgs=state.max_orgs, max_seats=state.max_seats),
        modules=sorted(state.modules),
        trace_id=trace_id,
    )
