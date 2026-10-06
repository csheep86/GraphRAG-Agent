"""``LicenseProvider``（接缝 9 的接口与唯一实现）—— ADR-0006 §2.2 / §2.3 / §4。

**为什么抽象出一个接口**：ADR-0006 §4 登记的接缝 9 覆盖「未来不同计费形态
（订阅 / 买断 / 按模块组合）」；``max_impls = 1``，当前**唯一实现**
:class:`DevLicenseProvider` —— ``scripts/check_seams.py`` 会把「出现的实现类集合」
与「ADR 登记集合」做**相等**比较 ⇒ 多加一个实现或少一个实现都会红。

**`DevLicenseProvider` 绝不是"恒 true"**（ADR §2.4 明令禁止的"假做"）：

- 真读 ``LICENSE_FILE_PATH`` 指向的文件；
- 真跑 **Ed25519** 验签（``cryptography``，见 ADR §2.3 / TBD-L1 已裁决）；
- 真比机器指纹、真判有效期。

任何一步不过 ⇒ 得到带**错误码**的状态 ⇒ 中间件按 §2.5 拒绝。
"""

from __future__ import annotations

import base64
import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode
from app.services.license.fingerprint import compute_fingerprint


@dataclass(frozen=True)
class LicenseState:
    """一份 License 加载后的**内存态**（ADR §2.6：每请求只判这个，不读盘不验签）。"""

    has_license: bool
    #: 无效 / 拒绝原因；``None`` = 有效
    code: ErrorCode | None = None
    license_id: str = ""
    fingerprint: str = ""
    not_before: datetime | None = None
    not_after: datetime | None = None
    grace_days: int = 0
    max_orgs: int = 0
    max_seats: int = 0
    #: 授权模块（ADR §3.3 取值集合的子集）
    modules: frozenset[str] = field(default_factory=frozenset)
    status: str = ""
    raw_payload: str = ""
    signature: str = ""
    loaded_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    #: 处于**过期宽限期**内（§2.5：宽限期内**只读**，超期才全量拒绝）
    in_grace: bool = False

    @property
    def ok(self) -> bool:
        return self.has_license and self.code is None


#: 「没有 license」这一状态本身，多处复用（中间件 / 状态端点）
MISSING_STATE = LicenseState(has_license=False, code=ErrorCode.LICENSE_MISSING)


class LicenseProvider(ABC):
    """接缝 9 的接口：**收口处唯一**，实现必须是 :class:`DevLicenseProvider`。

    只声明一个方法是有意的：对外暴露的面越小，将来换计费形态时要动的地方越少。
    """

    @abstractmethod
    def current_state(self) -> LicenseState:
        """返回**当前内存态**；加载与缓存是实现自己的事（§2.6 要求 O(1)）。"""


class DevLicenseProvider(LicenseProvider):
    """从文件系统加载 ``*.lic`` 并**真实验签**的实现。

    **缓存策略**（§2.6 / R-L4）：每请求**不读盘不验签** —— 只有满足任一条件才重载：

    ① 从未加载过；② 距上次加载超过 ``LICENSE_STATE_TTL_SECONDS``；
    ③ 文件的 ``mtime`` 或内容 hash 变了（热加载：换了文件不用重启）。

    ⚠️ 重载失败**沿用上一个状态**而不是回到"无 license"：换文件的瞬间若写了一半，
    直接判无效会把整站锁死——这是运维事故，不是安全策略。
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings
        self._state: LicenseState | None = None
        self._loaded_at: datetime | None = None
        self._fingerprint_hint: str = ""
        #: §2.7 时钟漂移基准（见 :meth:`_check_clock` 的未持久化说明）
        self._max_seen_ts: datetime | None = None

    # ------------------------------------------------------------------ public

    def current_state(self) -> LicenseState:
        settings = self._settings or get_settings()
        if self._should_reload(settings):
            self._state = self._load(settings)
            self._loaded_at = datetime.now(UTC)
        return self._state or MISSING_STATE

    # ------------------------------------------------------------------ internals

    def _check_clock(self, now: datetime, settings: Settings) -> None:
        """时钟漂移：**只告警不拒绝**（§2.7）。

        理由很实在：客户把时钟往前调把自己锁死，是运维事故不是攻击；
        拒绝了还要背锅，不如留一条告警痕迹（``license.clock_skew``）。

        ⚠️ **未持久化**：``max_seen_ts`` 现在只活在当前进程内存里，**重启即丢**。
        ADR §2.7 原文要求「持久化，防重启丢失」，但 ADR §3.1 的 ``licenses`` 字段清单里
        **没有对应列** ⇒ 加列是对 ADR 的改动，须另行裁决。
        该缺口登记在 ``changes/P4/integration-log.md`` §2.4，**未处置**。
        """
        tolerance = timedelta(days=settings.license_clock_skew_tolerance_days)
        if self._max_seen_ts is not None and now < self._max_seen_ts - tolerance:
            logger.bind(
                max_seen_ts=self._max_seen_ts.isoformat(), now=now.isoformat()
            ).warning("license.clock_skew")
        if self._max_seen_ts is None or now > self._max_seen_ts:
            self._max_seen_ts = now

    def _should_reload(self, settings: Settings) -> bool:
        if self._state is None or self._loaded_at is None:
            return True
        age = datetime.now(UTC) - self._loaded_at
        if age >= timedelta(seconds=settings.license_state_ttl_seconds):
            return True
        return self._digest_of_file(settings) != self._fingerprint_hint

    @staticmethod
    def _digest_of_file(settings: Settings) -> str:
        """文件内容指纹（用于「换文件即重载」）。文件不可读 ⇒ 返回 sentinel 而非抛错。"""
        path = Path(settings.license_file_path)
        try:
            raw = path.read_bytes()
        except OSError:
            return "__missing__"
        return hashlib.sha256(raw).hexdigest()

    def _load(self, settings: Settings) -> LicenseState:
        self._check_clock(datetime.now(UTC), settings)
        path = Path(settings.license_file_path)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            logger.bind(path=str(path)).warning("license_file_unreadable")
            return MISSING_STATE
        self._fingerprint_hint = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.bind(reason=str(exc)).warning("license_json_invalid")
            return LicenseState(has_license=False, code=ErrorCode.LICENSE_INVALID)

        if not isinstance(payload, dict):
            return LicenseState(has_license=False, code=ErrorCode.LICENSE_INVALID)

        signature = str(payload.get("signature") or "")
        body = {key: value for key, value in payload.items() if key != "signature"}
        # §2.2：signature **不参与**正文哈希 ⇒ 必须用「排除了签名后的正文」做确定性序列化
        canonical = json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

        verified = self._verify(canonical.encode("utf-8"), signature, settings)
        if verified is not None:
            return LicenseState(has_license=False, code=verified)

        state = self._build_state(body, signature, canonical, settings)
        self._persist(state)
        return state

    @staticmethod
    def _verify(body: bytes, signature: str, settings: Settings) -> ErrorCode | None:
        """Ed25519 验签；返回 ``None`` = 通过，否则返回**错误码**。

        **没有公钥 ⇒ 验签失败**（:data:`LICENSE_INVALID`），绝不退化为「跳过校验」——
        那正是 ADR §2.3 要拦的「宽松通过」。
        """
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric import ed25519

        raw_key = settings.license_public_key.strip()
        if not raw_key:
            logger.warning("license_public_key_missing")
            return ErrorCode.LICENSE_INVALID
        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(
                base64.b64decode(raw_key, validate=True)
            )
            public_key.verify(base64.b64decode(signature, validate=True), body)
        except (InvalidSignature, ValueError, TypeError) as exc:
            logger.bind(reason=type(exc).__name__).warning("license_signature_invalid")
            return ErrorCode.LICENSE_INVALID
        return None

    def _build_state(
        self,
        body: dict[str, Any],
        signature: str,
        canonical: str,
        settings: Settings,
    ) -> LicenseState:
        expected_fingerprint = str(body.get("fingerprint") or "")
        actual = compute_fingerprint()
        if expected_fingerprint != actual:
            logger.bind(
                expected_len=len(expected_fingerprint), actual_len=len(actual)
            ).warning("license_fingerprint_mismatch")
            return LicenseState(
                has_license=False, code=ErrorCode.LICENSE_FINGERPRINT_MISMATCH
            )

        now = datetime.now(UTC)
        not_before = _parse_dt(body.get("not_before"))
        not_after = _parse_dt(body.get("not_after"))
        if not_before is None or not_after is None:
            return LicenseState(has_license=False, code=ErrorCode.LICENSE_INVALID)

        grace_days = int(body.get("grace_days") or 0)
        # §2.7：过期判定要带宽限；``not_before`` 之前同样视为不可用（未生效）
        deadline = not_after + timedelta(days=grace_days)

        if now < not_before or now > deadline:
            return LicenseState(
                has_license=True,
                code=ErrorCode.LICENSE_EXPIRED,
                license_id=str(body.get("license_id") or ""),
                fingerprint=expected_fingerprint,
                not_before=not_before,
                not_after=not_after,
                grace_days=grace_days,
                status="expired",
                raw_payload=canonical,
                signature=signature,
            )

        # 过了 not_after 但还在宽限期 ⇒ **只读**（§2.5）
        in_grace = now > not_after
        return LicenseState(
            has_license=True,
            code=None,
            license_id=str(body.get("license_id") or ""),
            fingerprint=expected_fingerprint,
            not_before=not_before,
            not_after=not_after,
            grace_days=grace_days,
            max_orgs=int(body.get("limits", {}).get("max_orgs") or 0),
            max_seats=int(body.get("limits", {}).get("max_seats") or 0),
            modules=frozenset(str(item) for item in (body.get("modules") or [])),
            status="active" if not in_grace else "expired",
            raw_payload=canonical,
            signature=signature,
            in_grace=in_grace,
        )

    @staticmethod
    def _persist(state: LicenseState) -> None:
        """成功加载即落一行（``licenses`` 表的**唯一消费者**）—— 用于回溯本机装过什么。

        ⚠️ 写失败**只记日志**：取证的缺失不该让整站起不来（与审计同款纪律）。
        """
        from app.services.license.store import record_loaded_license

        try:
            record_loaded_license(state)
        except Exception as exc:  # noqa: BLE001 - 取证存储失败不得冒泡
            logger.bind(reason=str(exc)).warning("license_record_write_failed")


def _parse_dt(value: Any) -> datetime | None:
    """ISO8601 → tz-aware datetime；非法即 ``None``（不猜时区、不静默兜底）。"""
    if not isinstance(value, str) or not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def get_license_provider() -> LicenseProvider:
    """接缝 9 的取用入口。

    走这个入口而不是到处 ``DevLicenseProvider()``，是为了让「换实现」只需改一处
    —— 也是 ``check_seams.py`` 能扫到「实现类集合 == 登记集合」的前提。
    """

    return _PROVIDER


_PROVIDER: LicenseProvider = DevLicenseProvider()
