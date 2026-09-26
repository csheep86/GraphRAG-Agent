"""数据输出接缝 `ExportSink`（ADR-0004 §2.1 第 6 行；Sprint 8 批次 E）。

企业侧要接的是审计底稿系统 / 报表 BI / 数仓 / Office 插件——本阶段**一个都不接**。
这里只落：接口 + 恰好**一个** JSON/CSV 实现（:class:`JsonCsvExportSink`）；实现
集合「不多不少」由 ``scripts/check_seams.py`` 接缝 6 判据机械校验（min = max = 1）。

**不提供 HTTP 端点**：导出是"把数据给出去"，走端点就要进契约、要做鉴权与审计——
那是**集成**不是**预留**（ADR-0004 §3 第 1 条）。因此本模块由脚本 / 未来调用方
直接构造使用，不注册路由、不改契约（`export_openapi.py --check` 保持零漂移）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from app.core.errors import AppError, ErrorCode

#: 登记支持的格式。"一个 JSON/CSV 实现" = 同一个实现类同时提供这两种格式。
EXPORT_FORMATS: tuple[str, ...] = ("json", "csv")


class ExportFormatError(AppError):
    """请求了未登记的格式：**显式报错**，绝不静默回落到某个默认格式。"""

    def __init__(self, fmt: str) -> None:
        super().__init__(
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            detail={"fmt": fmt, "supported": list(EXPORT_FORMATS)},
        )


class ExportPayload(BaseModel):
    """一次导出的数据体。

    ``columns`` **显式给定列顺序**：CSV 表头顺序必须稳定可预期，靠 dict 的插入
    顺序隐式决定只是"碰巧对"，换数据源就乱。
    """

    dataset: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)


class ExportResult(BaseModel):
    """渲染结果：调用方据此落盘 / 回传 / 打包。"""

    filename: str
    media_type: str
    content: str


class ExportSink(ABC):
    """数据输出接口（接缝 6）。"""

    @abstractmethod
    def render(self, payload: ExportPayload, fmt: str) -> ExportResult:
        """把 :class:`ExportPayload` 渲染成目标格式的文本。"""
