"""`scripts/eval_controlled_qset.py` 受控问题集的结构守卫。

为什么需要：问题集是「引用覆盖率 100% / 拒答 0 误伤」这条 M3 验收判据的**被测对象**，
它**换过版**（v1 Sprint 6 语料 → v2 种子集同源语料，见 notes §7.2）。被测对象若被
悄悄改动（少一题、拒答标注写反、版本常量没跟着改），历史结论就不可比。这里只守
**结构与版本登记**，不碰真实链路（真跑要烧 LLM 额度，不进 CI）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str) -> Any:
    """按文件路径加载 `scripts/` 下的脚本（该目录不是包，不能 import）。"""
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


QSET = _load("eval_controlled_qset")


def test_questions_structure_12_in_corpus_plus_2_out() -> None:
    """12 库内 + 2 库外：与 v1 同规模，换版前后结论才可比。"""
    refuses = [flag for _, flag in QSET.QUESTIONS]
    assert len(QSET.QUESTIONS) == 14
    assert refuses.count(False) == 12
    assert refuses.count(True) == 2
    # 库外两问必须排在末尾（读代码时的口径约定）
    assert refuses[-2:] == [True, True]


def test_questions_non_empty_and_unique() -> None:
    texts = [text for text, _ in QSET.QUESTIONS]
    assert all(isinstance(text, str) and len(text.strip()) >= 6 for text in texts)
    assert len(set(texts)) == len(texts), "问题重复会让覆盖率统计虚高"


def test_qset_version_and_frozen_corpus_registered() -> None:
    """换版必须同步改版本常量与冻结的 `kg_version`——否则实测结论无法归因到语料。"""
    assert QSET.QSET_VERSION.startswith("v")
    assert QSET.QSET_KG_VERSION.startswith("v-")
    assert QSET.QSET_KG_VERSION == "v-s71a-fe1c4dc3"
