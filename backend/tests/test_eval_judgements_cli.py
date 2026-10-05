"""**P6-F**：判分文件的解析与「两侧不许共用一张表」的守卫。

这几条在拦什么：

1. **判分表必须能自解释**（``_rubric`` / ``_judged_by`` / ``_note`` 允许存在）——
   判分表直接决定 C1 的数字，一份裸的 ``{"5": false}`` 三个月后**无人能复核**：
   不知道用的哪套 rubric、谁判的、为什么判错；
2. **非题号键必须报错** —— 若静默放行，某道题其实从未被判分却看不出来（等价于无声抽样）；
3. **两侧判分表不得是同一个文件**（A1 裁决 3）—— 共用一张表 = 用图侧答案
   替基线预先判卷 ⇒ 增益失真，且**外表看不出来**。

全部用例不需要 LLM / 后端 / Neo4j。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval_acceptance.py"


def _load_module():  # type: ignore[no-untyped-def]
    """按需加载 CLI 脚本（``scripts/`` 不是包，与既有做法一致）。"""
    spec = importlib.util.spec_from_file_location("_eval_acceptance_mod", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_eval_acceptance_mod"] = module
    spec.loader.exec_module(module)
    return module


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_meta_keys_are_ignored(tmp_path: Path) -> None:
    """判分文件**允许**自带 rubric 说明 ⇒ 判分可复核；且不影响判分结果。"""
    module = _load_module()
    path = _write(
        tmp_path,
        "judge.json",
        {
            "_rubric": "rubric-v1",
            "_judged_by": "architect",
            "1": True,
            "2": False,
        },
    )
    assert module._load_judgements(path) == {1: True, 2: False}


def test_non_numeric_key_is_rejected(tmp_path: Path) -> None:
    """非题号键**不许**静默通过：那通常意味着某题从未被判分却无人知晓。"""
    module = _load_module()
    path = _write(tmp_path, "bad.json", {"1": True, "题号写错了": True})
    with pytest.raises(ValueError, match="必须是题号"):
        module._load_judgements(path)


def test_same_file_for_both_sides_is_rejected(tmp_path: Path) -> None:
    """A1 裁决 3：两侧共用一张表 = 替基线预设答案 ⇒ 直接拒绝执行。"""
    module = _load_module()
    path = _write(tmp_path, "both.json", {"1": True})
    with pytest.raises(ValueError, match="同一个文件"):
        module.distinct_judgement_tables(path, path)


def test_distinct_files_are_accepted(tmp_path: Path) -> None:
    """反向：确实是两份表 ⇒ 必须放行（否则守卫过度拦截，评测根本跑不了）。"""
    module = _load_module()
    graph = _write(tmp_path, "graph.json", {"1": True})
    baseline = _write(tmp_path, "baseline.json", {"1": False})
    module.distinct_judgement_tables(graph, baseline)  # 不抛异常
