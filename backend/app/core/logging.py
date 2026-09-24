"""日志配置：统一 loguru + JSON 输出（CODEBUDDY.md「日志与可观测性规则」）。

日志中禁止输出密钥 / Token / 密码，以及 M1 / M2 / M3 标注为敏感的字段
（`filename` 原文、`error_detail`、`pii_flags`、提问原文）。
"""

from __future__ import annotations

import sys

from loguru import logger

from app.core.errors import AppError, ErrorCode

_CONFIGURED = False


def setup_logging(level: str = "INFO", *, log_export: bool = False) -> None:
    """幂等地把 loguru 配置为单 sink JSON 输出。

    :param log_export: ADR-0004 §3 第 5 条**已登记的合规占位**（统一日志平台 /
        OTLP 导出）。Demo-MVP 阶段不实现：置 true 时**显式报错**
        （``NOT_IMPLEMENTED``），而不是"开关存在却没效果"——后者就是假做。
    """
    if log_export:
        raise AppError(
            ErrorCode.NOT_IMPLEMENTED,
            "统一日志平台 / OTLP 导出尚未实现（ADR-0004 §3 第 5 条例外登记的占位"
            "开关）；请先关闭 settings.log_export 再启动服务",
        )
    global _CONFIGURED
    if _CONFIGURED:
        return
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        serialize=True,
        backtrace=False,
        diagnose=False,
        enqueue=False,
    )
    _CONFIGURED = True


__all__ = ["logger", "setup_logging"]
