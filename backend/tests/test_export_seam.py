"""接缝 6（`ExportSink`）的回归锁（Sprint 8 批次 E）。

锁的是三件事：① 渲染结果对（json / csv）；② **未登记格式显式报错**（不静默回落）；
③ `settings.log_export` 这个合规占位**置 true 必须显式报未实现**（ADR-0004 §3 第 5 条
例外登记：占位不等于假做）。实现集合「恰好 1 个」由 `check_seams.py` 机械校验，
这里只锁构造函数的返回类型。
"""

from __future__ import annotations

import json

import pytest

import app.core.logging as logging_module
from app.core.errors import AppError, ErrorCode
from app.services.export import (
    JsonCsvExportSink,
    build_export_sink,
)
from app.services.export.base import (
    ExportFormatError,
    ExportPayload,
)


def _payload() -> ExportPayload:
    return ExportPayload(
        dataset="suspicions",
        columns=["id", "type", "status"],
        rows=[
            {
                "id": "s1",
                "type": "same_legal_person",
                "status": "open",
                "extra": "丢弃",
            },
            {"id": "s2", "type": "same_address", "status": "confirmed"},
        ],
    )


def test_render_json_keeps_columns_and_drops_extra_keys() -> None:
    result = build_export_sink().render(_payload(), "json")

    assert result.filename == "suspicions.json"
    assert result.media_type == "application/json"
    body = json.loads(result.content)
    assert body["dataset"] == "suspicions"
    assert body["columns"] == ["id", "type", "status"]
    assert "extra" not in body["rows"][0]
    assert body["rows"][1]["status"] == "confirmed"


def test_render_csv_header_and_row_count() -> None:
    result = build_export_sink().render(_payload(), "csv")

    assert result.filename == "suspicions.csv"
    assert result.media_type == "text/csv"
    lines = result.content.strip().splitlines()
    assert lines[0] == "id,type,status"
    assert len(lines) == 3  # 表头 + 2 行
    assert lines[2].startswith("s2,same_address,confirmed")


def test_unknown_format_raises_explicit_error() -> None:
    """未登记格式必须显式报错：静默回落到 json 会产出"看起来成功"的错误产物。"""
    with pytest.raises(ExportFormatError) as excinfo:
        build_export_sink().render(_payload(), "xlsx")

    error = excinfo.value
    assert error.code is ErrorCode.UNSUPPORTED_MEDIA_TYPE
    assert error.http_status == 415
    assert error.detail is not None and error.detail["fmt"] == "xlsx"


def test_build_returns_the_single_registered_implementation() -> None:
    """登记集合是「一个 JSON/CSV 实现」：两类格式同属 `JsonCsvExportSink`。"""
    assert isinstance(build_export_sink(), JsonCsvExportSink)


def test_log_export_placeholder_fails_loud_not_silent() -> None:
    """合规占位：置 true 时显式报 NOT_IMPLEMENTED，而不是"开关存在却不生效"。"""
    logging_module._CONFIGURED = False
    try:
        with pytest.raises(AppError) as excinfo:
            logging_module.setup_logging(log_export=True)
        assert excinfo.value.code is ErrorCode.NOT_IMPLEMENTED
    finally:
        logging_module._CONFIGURED = False
