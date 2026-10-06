"""``licenses`` 表的**唯一写入点**（ADR-0006 §3.1：回溯「这台机器上装过什么」）。

**这张表为什么存在**：License 是离线签发的文件，现场排障时最常被问的是
「这台机器现在 / 曾经装的是哪一份」。``raw_payload``（**不含签名**）就是取证用的原文。

⚠️ **实例级 + RLS 豁免**：本表**没有租户维度**（无 ``org_id``），与 ``roles`` 同理。
这里传 :data:`DEFAULT_ORG_ID` 给 ``open_session`` 只是**技术需要**（它要求显式 org，
且要用它设置 RLS 的 GUC），**不代表本表属于某个租户**。
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.config import DEFAULT_ORG_ID
from app.db.models import License
from app.db.session import open_session
from app.services.license.provider import LicenseState


def record_loaded_license(state: LicenseState) -> None:
    """加载成功即登记一行（**按 ``license_id`` 幂等**）；无效状态直接返回。

    调用方（``DevLicenseProvider._persist``）已包了 try/except：
    取证的缺失不该让整站起不来 —— 与审计「写失败只记日志」同款纪律。
    """
    if not state.ok or not state.license_id:
        return

    with open_session(org_id=DEFAULT_ORG_ID) as session:
        exists = (
            session.scalars(
                select(License.id).where(License.license_id == state.license_id)
            ).first()
            is not None
        )
        if exists:
            return
        session.add(
            License(
                license_id=state.license_id,
                fingerprint=state.fingerprint,
                not_before=state.not_before,
                not_after=state.not_after,
                grace_days=state.grace_days,
                max_orgs=state.max_orgs,
                max_seats=state.max_seats,
                modules=sorted(state.modules),
                raw_payload=state.raw_payload,
                signature=state.signature,
                activated_at=state.loaded_at,
                status=state.status or "active",
            )
        )
        session.commit()
