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


def _manifest_current_qset() -> dict:
    """从 **MANIFEST** 读当前题集的题数与配额（**题数的单一真源，不写死**）。

    P6-H 把 14 → 40 题时，仓库里有**三处**写死的题数副本（本文件、parity 测试、
    test_evaluation_dataset），前两处都改了、第三处忘了 ⇒ 测试红。
    那是哨兵该响的时候，但更该做的是**让它不再需要人改**：现在全部改为读 MANIFEST。
    """
    import json

    from app.evaluation.dataset import DATA_DIR

    manifest = json.loads((DATA_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
    for entry in manifest["datasets"]:
        if entry["id"] == "controlled-qset-v4":
            return entry
    raise AssertionError("MANIFEST 里找不到 controlled-qset-v4 条目")


def test_questions_structure_matches_manifest_quota() -> None:
    """题库配额必须与 MANIFEST 登记一致（36 库内 + 4 库外）。

    为什么库外题**必须存在**：库外题是拒答出口的反面证据 —— 没有它，
    「模型全答 refusenone ⇒ 覆盖率 100%」这种刷绿也能过（F3 反面用例）。
    """
    refuses = [flag for _, flag in QSET.QUESTIONS]
    entry = _manifest_current_qset()
    assert len(QSET.QUESTIONS) == int(entry["items"])
    assert refuses.count(False) == int(entry["in_corpus"])
    assert refuses.count(True) == int(entry["out_of_corpus"])
    # 库外问必须排在**末尾**（读代码时的口径约定）。
    # 注意这只约束「结尾」：v3 遗留的 Q13/Q14 位于序列中间——换版不许改动旧题顺序，
    # 因此库外问在 v4 里并非全部连续聚集于末尾，此处沿用原有的「末尾两问」约定。
    assert refuses[-2:] == [True, True]


def test_questions_non_empty_and_unique() -> None:
    texts = [text for text, _ in QSET.QUESTIONS]
    assert all(isinstance(text, str) and len(text.strip()) >= 6 for text in texts)
    assert len(set(texts)) == len(texts), "问题重复会让覆盖率统计虚高"


def test_qset_version_and_frozen_corpus_registered() -> None:
    """换版必须同步改版本常量与冻结的 `kg_version`——否则实测结论无法归因到语料。

    v3（2026-09-30 换版）：v2 冻结的 ``v-s71a-fe1c4dc3`` **在 Neo4j 上已无 chunk**
    （仅剩 SQLite 一行 ``ready``），题集与其不同源 ⇒ 换到当前 active 语料
    ``attendance-demo-v1``（换版依据见 ``eval_controlled_qset.py`` docstring）。
    注意：active 版本名是**语义名**（``attendance-demo-v1``）而非 ``v-`` 前缀，
    故这里钉「== 冻结值」，**不**再钉 ``v-`` 前缀——钉前缀会把合法换版误判为破坏。

    **v4（2026-10-05，P6-H）**：14 → 40 题（旧 14 题一字未改，追加 26 道）。
    换版原因是**灵敏度**：14 题 ⇒ 单题翻转 ±7.14pp，而 C1 离 10% 阈值只差 0.9pp
    ⇒ 那种分母上校准阈值没有意义。40 题 ⇒ ±2.5pp。
    """
    assert QSET.QSET_VERSION == "v4-2026-10-05"
    assert QSET.QSET_KG_VERSION == "attendance-demo-v1"
