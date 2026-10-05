"""**防第二真源**（D5）：`data/eval/controlled-qset-v3.json` 必须
与 `scripts/eval_controlled_qset.py::QUESTIONS` **逐题一致**。

为什么需要这条测试：受控问题集一旦有两份，改一份忘另一份，
结论就会在两处漂移（qset v1→v2→v3 三次换版都是这么栽的）。
本批**不改**原脚本（改它 = 动既有行为），改为用测试把两份钉在一起：
任一侧变了 ⇒ 测试红 ⇒ 由人决定谁改。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from app.evaluation.dataset import DATA_DIR as _DATA_DIR
from app.evaluation.dataset import (
    QSET_FILE,
    load_manifest,
    load_question_set,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND_DIR / "scripts" / "eval_controlled_qset.py"
QSET_FILE_PATH = _DATA_DIR / QSET_FILE


def _load_legacy_questions() -> list[tuple[str, bool]]:
    """按路径加载既有脚本（它带 `sys.stdout.reconfigure`，import 无害）。"""
    spec = importlib.util.spec_from_file_location("legacy_eval_qset", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["legacy_eval_qset"] = module
    spec.loader.exec_module(module)
    return list(module.QUESTIONS)  # type: ignore[attr-defined]


def _manifest_v4_items() -> int:
    """**当前**生效题集的题数（从 MANIFEST 读，不写死）。

    为什么改成读 MANIFEST：这里原本写死 ``== 14``，等于把题数**第三处**手工副本
    （副本一在脚本 QUESTIONS、副本二在 JSON、副本三在此）。P6-H 扩到 40 题时，
    前两处都改了、唯独这处忘了 ⇒ 测试会红——那是它该响的时候，但**更该做的是让它不再需要人改**。
    现在题数的单一真源是 MANIFEST 里 v4 条目的 ``items``。
    """
    manifest = load_manifest()
    for entry in manifest.get("datasets", []):
        if entry.get("id") == "controlled-qset-v4":
            assert entry.get("status") != "historical", "v4 是当前版本，不应标 historic"
            return int(entry["items"])
    raise AssertionError("MANIFEST 里找不到 controlled-qset-v4 条目")


def test_question_count_matches_legacy_script() -> None:
    expected = _manifest_v4_items()
    assert len(load_question_set()) == len(_load_legacy_questions()) == expected


def test_manifest_items_matches_v4_json() -> None:
    """MANIFEST 的 ``items`` 必须与 **v4 JSON 自己声明的** ``question_count`` 一致。

    否则出题脚本 / JSON / MANIFEST 三处又开始各自漂移（这正是 DATASET_DRIFT 的老病）。
    """
    payload = json.loads(QSET_FILE_PATH.read_text(encoding="utf-8"))
    assert int(payload["question_count"]) == _manifest_v4_items()


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
