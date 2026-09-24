"""``JSON/CSV`` 实现（ADR-0004 §2.1 第 6 行登记的**唯一**实现）。"""

from __future__ import annotations

import csv
import io
import json

from app.services.export.base import (
    EXPORT_FORMATS,
    ExportFormatError,
    ExportPayload,
    ExportResult,
    ExportSink,
)

_MEDIA_TYPES = {"json": "application/json", "csv": "text/csv"}


class JsonCsvExportSink(ExportSink):
    """同时提供 JSON 与 CSV 两种渲染的实现（**一个**类，不是两个）。

    为什么合在一个类里：ADR 登记的是「一个 JSON/CSV 实现」，拆成
    ``JsonExportSink`` + ``CsvExportSink`` 会让实现类变成 2 个，撞上
    ``check_seams.py`` 的 ``max_impls = 1``——多一个即越界（ADR-0004 §3 第 4 条）。
    """

    def render(self, payload: ExportPayload, fmt: str) -> ExportResult:
        if fmt not in EXPORT_FORMATS:
            raise ExportFormatError(fmt)

        # 按 columns 取齐：行里多出的键丢弃（CSV 无表头容纳），缺的键补 None
        rows = [
            {column: row.get(column) for column in payload.columns}
            for row in payload.rows
        ]

        if fmt == "json":
            content = json.dumps(
                {
                    "dataset": payload.dataset,
                    "columns": payload.columns,
                    "rows": rows,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        else:
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(
                buffer, fieldnames=payload.columns, extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(rows)
            content = buffer.getvalue()

        return ExportResult(
            filename=f"{payload.dataset}.{fmt}",
            media_type=_MEDIA_TYPES[fmt],
            content=content,
        )
