"""**防第二真源**（D5）：`data/eval/controlled-qset-v3.json` 必须
与 `scripts/eval_controlled_qset.py::QUESTIONS` **逐题一致**。

为什么需要这条测试：受控问题集一旦有两份，改一份忘另一份，
结论就会在两处漂移（qset v1→v2→v3 三次换版都是这么栽的）。
本批**不改**原脚本（改它 = 动既有行为），改为用测试把两份钉在一起：
任一侧变了 ⇒ 测试红 ⇒ 由人决定谁改。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from app.evaluation.dataset import load_question_set

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND_DIR / "scripts" / "eval_controlled_qset.py"


def _load_legacy_questions() -> list[tuple[str, bool]]:
    """按路径加载既有脚本（它带 `sys.stdout.reconfigure`，import 无害）。"""
    spec = importlib.util.spec_from_file_location("legacy_eval_qset", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["legacy_eval_qset"] = module
    spec.loader.exec_module(module)
    return list(module.QUESTIONS)  # type: ignore[attr-defined]


def test_question_count_matches_legacy_script() -> None:
    assert len(load_question_set()) == len(_load_legacy_questions()) == 14


def test_every_question_and_refusal_flag_matches() -> None:
    """逐题比对**题面 + 是否预期拒答**（顺序也必须一致）。"""
    dataset = load_question_set()
    legacy = _load_legacy_questions()
    for item, (question, should_refuse) in zip(dataset, legacy, strict=True):
        assert item.question == question, f"Q{item.index} 题面不一致"
        assert item.should_refuse is should_refuse, f"Q{item.index} 拒答标注不一致"


def test_kg_version_matches_legacy_script() -> None:
    """冻结口径（`kg_version`）也必须一致——题对了但语料版本不对 = 全拒答的假结论。"""
    spec = importlib.util.spec_from_file_location("legacy_eval_qset_kv", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["legacy_eval_qset_kv"] = module
    spec.loader.exec_module(module)

    from app.evaluation.dataset import load_manifest

    assert load_manifest()["corpus"]["attendance"]["kg_version"] == (
        module.QSET_KG_VERSION  # type: ignore[attr-defined]
    )
