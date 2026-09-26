"""数据输出接缝（ADR-0004 §2.1 接缝 6；Sprint 8 批次 E）。

用法（无端点、不进契约，由脚本 / 未来调用方直接构造）：

    sink = build_export_sink()
    result = sink.render(
        ExportPayload(dataset="suspicions", columns=[...], rows=[...]), "csv"
    )
"""

from __future__ import annotations

from app.services.export.base import (
    EXPORT_FORMATS,
    ExportFormatError,
    ExportPayload,
    ExportResult,
    ExportSink,
)
from app.services.export.json_csv import JsonCsvExportSink


def build_export_sink() -> ExportSink:
    """构造导出 sink（登记集合恰好一个实现：:class:`JsonCsvExportSink`）。"""
    return JsonCsvExportSink()


__all__ = [
    "EXPORT_FORMATS",
    "ExportFormatError",
    "ExportPayload",
    "ExportResult",
    "ExportSink",
    "JsonCsvExportSink",
    "build_export_sink",
]
