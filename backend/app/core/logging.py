"""日志配置：统一 loguru + JSON 输出（CODEBUDDY.md「日志与可观测性规则」）。

日志中禁止输出密钥 / Token / 密码，以及 M1 / M2 / M3 标注为敏感的字段
（`filename` 原文、`error_detail`、`pii_flags`、提问原文）。
"""

from __future__ import annotations

import sys

from loguru import logger

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """幂等地把 loguru 配置为单 sink JSON 输出。"""
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
