"""**P6-S**：C1 两侧答卷导出物的护栏。

它拦的是三件事（都是「脚本看起来跑通了，其实 C1 的分母已经废了」那一类）：

1. ** exported 的必须带题干与 rubric 锚点** —— 只有答案原文，人没法定对错（A3：判分由人做）；
2. **产物绝不能含 `correct` 值** —— 含了就是脚本代判分（A3 / Non-goal 2 的红线）；
3. **缺任一侧 ⇒ 报错** —— 半侧的卷子判完也是无分母。

用例不依赖 LLM / 后端 / Neo4j（只读本地数据集）。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_judging_sheets.py"


def _load_module():  # type: ignore[no-untyped-def]
    """按需加载 CLI 脚本（``scripts/`` 不是包，与既有做法一致）。"""
    spec = importlib.util.spec_from_file_location("_export_sheets_mod", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_export_sheets_mod"] = module
    spec.loader.exec_module(module)
    return module


def _report(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "criteria": [
            {
                "criterion": "c1_graph_gain",
                "status": "unknown",
                "value": None,
                "provenance": {
                    "git_hash": "deadbeef",
                    "dataset_version": "controlled-qset-v4",
                    "kg_version": "attendance-demo-v1",
                },
                "blocked_by": "A3：图侧没有一题被人工判分",
                "detail": detail,
            }
        ]
    }


def _row(index: int) -> dict[str, Any]:
    return {"index": index, "refused": False, "citations": 1, "answer": "原文"}


def test_sheets_carry_question_and_rubric_anchors(tmp_path: Path) -> None:
    module = _load_module()
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            _report(
                {
                    "awaiting_graph": [_row(1), _row(2)],
                    "awaiting_baseline": [_row(1), _row(2)],
                    "graph_spec": {"retriever": "graph_mentions+lexical_rerank"},
                    "baseline_spec": {"retriever": "dense_top_k"},
                }
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sheet, filename = module.build_sheets(path)

    assert filename.startswith("c1-sheets-")
    for side in ("graph", "baseline"):
        rows = sheet[side]
        assert [row["index"] for row in rows] == [1, 2]
        #: **判分所必需**：题干 + rubric 锚点一个都不能少
        assert all(row["question"] for row in rows)
        assert all(isinstance(row["expected_points"], list) for row in rows)
        assert all(isinstance(row["should_refuse"], bool) for row in rows)
    #: 两侧同一批产物 ⇒ 题号必须逐位对齐
    assert [r["index"] for r in sheet["graph"]] == [
        r["index"] for r in sheet["baseline"]
    ]
    assert sheet["_blocked_by"] == "A3：图侧没有一题被人工判分"


def test_sheets_never_carry_correct(tmp_path: Path) -> None:
    """**Non-goal 2 的机器守卫**：产物里出现 `correct` 就是脚本代判分。"""
    module = _load_module()
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            _report({"awaiting_graph": [_row(1)], "awaiting_baseline": [_row(1)]}),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sheet, _filename = module.build_sheets(path)
    #: 只查**字段名**（判分值藏在多深的层级都不放过），不查正文——
    #: `_notice` 里本就要写"不含 correct 值"这句话，按子串扫会误伤。
    keys = set(_all_keys(sheet))
    assert "correct" not in keys
    assert "judged_by" not in keys


def test_missing_side_is_rejected(tmp_path: Path) -> None:
    """只有一侧 ⇒ **报错**（半张卷判完也凑不出分母）。"""
    module = _load_module()
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(_report({"awaiting_graph": [_row(1)]}), ensure_ascii=False),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="awaiting_baseline"):
        module.build_sheets(path)


def _all_keys(node: Any):  # type: ignore[no-untyped-def]
    """递归取所有字段名（判分值藏在多深的层级都不放过）。"""
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _all_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _all_keys(item)


def test_index_outside_question_set_is_rejected(tmp_path: Path) -> None:
    """题集里没有的题号 ⇒ **不许**静默留空题面（空题面 = 无从判分却看不出来）。"""
    module = _load_module()
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            _report(
                {"awaiting_graph": [_row(9999)], "awaiting_baseline": [_row(9999)]}
            ),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="没有第 9999 题"):
        module.build_sheets(path)
