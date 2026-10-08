"""日志配置：统一 loguru + JSON 输出（CODEBUDDY.md「日志与可观测性规则」）。

日志中禁止输出密钥 / Token / 密码，以及 M1 / M2 / M3 标注为敏感的字段
（`filename` 原文、`error_detail`、`pii_flags`、提问原文）。

**P5-E 起多了第二道防线**：本模块给 loguru 装上 :func:`app.core.masking.mask_log_record`
这个 patcher —— 所有 ``logger.bind(...)`` 带进来的 ``extra`` 字段在**序列化之前**
按登记表脱敏（M5 §3 验收 3「写入日志前自动脱敏」）。

为什么是 patcher 而不是「每个调用点自己调 ``mask()``」：全仓 ``logger.bind``
**144+ 处**，靠调用方自觉必然漏，而漏埋比多写更难发现（审计模块的 A1 决策同一条
理由）。登记在 `changes/P5-E/integration-log.md`。

⚠️ **它不覆盖**日志 ``message`` 正文里的原文——那里要脱敏就只能"猜值"
（批次 Non-goal 10）⇒ 已知缺口，不许外推。
"""

from __future__ import annotations

import sys

from loguru import logger

from app.core.errors import AppError, ErrorCode
from app.core.masking import mask_log_record

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
    # 脱敏器装在**全局**而不是某个 sink 上：换 sink（含测试捕获 sink）不该换掉
    # 脱敏语义——"换个写法就绕过"正是这类防线的典型失效方式。
    logger.configure(patcher=mask_log_record)
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
