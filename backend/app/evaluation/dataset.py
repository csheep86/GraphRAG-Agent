"""版本化**受控问题集 / gold 标注**的加载与校验（E2）。

**为什么数据要单独成文件而不是写进代码**：数据集是**结论的归因**——
换版必须留痕（qset v1→v2→v3 三次换版的教训就是"题集变了但没人知道，结论照比"）。
写进代码 ⇒ 改一行代码就换了一版数据，且 `git diff` 看不出数据集变了。

**校验纪律**：缺字段 / 版本不匹配 / 重复题号 ⇒ **报错，不静默**。
静默兜底会让"数据集坏了"变成"指标变差"，归因就废了。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.evaluation.metrics import Finding

#: 数据集根目录（**唯一真源**）：`backend/data/eval/`。
#: 该目录**未被 .gitignore 忽略** ⇒ 会入库 ⇒ 换版有 git 痕迹（已实测核对 .gitignore）。
DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "eval"

MANIFEST_FILE = "MANIFEST.json"
QSET_FILE = "controlled-qset-v4.json"
MULTIHOP_FILE = "gold-multihop-v1.json"
AFFILIATION_FILE = "gold-affiliation-v1.json"
#: **A8（2026-10-04）**：gold 有了**第二版**（v2 = 扩标到 200/500/100/20）。
#: 默认仍是 v1 ⇒ 既有结论**不因新增文件而漂移**；要判达标必须显式选 v2。
AFFILIATION_FILES = {
    "v1": "gold-affiliation-v1.json",
    "v2": "gold-affiliation-v2.json",
}
DEFAULT_AFFILIATION_VERSION = "v1"
FIXTURE_BASELINE_FILE = "baselines/fixture-baseline-v1.json"


def _affiliation_file(version: str = DEFAULT_AFFILIATION_VERSION) -> str:
    if version not in AFFILIATION_FILES:
        raise DatasetError(
            f"未知 gold 版本 {version!r}（可选 {sorted(AFFILIATION_FILES)}）"
            "⇒ 换语料必须显式，不能靠默认值悄悄换"
        )
    return AFFILIATION_FILES[version]


class DatasetError(RuntimeError):
    """数据集结构错误（**显式抛**，不静默降级）。"""


@dataclass(frozen=True)
class Question:
    """受控问题集的一题。"""

    index: int
    question: str
    should_refuse: bool
    source_doc: str
    expected_points: tuple[str, ...]


@dataclass(frozen=True)
class MultiHopItem:
    """多跳问题集的一题（含跳数标注与人工判分槽位）。"""

    index: int
    question: str
    hops: int
    hop_path: str
    expected_points: tuple[str, ...]
    #: A3：`None` = 未判分 ⇒ **不入分母**（不是 0）。
    correct: bool | None
    judged_by: str | None


def _read(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    if not path.exists():
        raise DatasetError(f"数据集文件缺失: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        raise DatasetError(f"数据集文件不是合法 JSON: {path} ({exc})") from exc


def _require(payload: dict[str, Any], key: str, *, where: str) -> Any:
    if key not in payload or payload[key] is None:
        raise DatasetError(f"{where} 缺字段 `{key}`（数据集校验失败，不静默兜底）")
    return payload[key]


def load_manifest() -> dict[str, Any]:
    """加载 `MANIFEST.json`（版本 / 来源 / rubric / 脏数据处理口径）。"""
    return _read(MANIFEST_FILE)


def load_question_set() -> tuple[Question, ...]:
    """加载受控问题集（v3）；与 `eval_controlled_qset.QUESTIONS` 的一致性由
    `tests/test_eval_qset_parity.py` 钉住（**防第二真源**）。"""
    payload = _read(QSET_FILE)
    items: list[Question] = []
    seen: set[int] = set()
    for raw in _require(payload, "items", where=QSET_FILE):
        where = f"{QSET_FILE}#{raw.get('index')}"
        index = int(_require(raw, "index", where=where))
        if index in seen:
            raise DatasetError(f"{where} 题号重复（重复题会让覆盖率被同一题污染）")
        seen.add(index)
        items.append(
            Question(
                index=index,
                question=str(_require(raw, "question", where=where)),
                should_refuse=bool(_require(raw, "should_refuse", where=where)),
                source_doc=str(raw.get("source_doc", "")),
                expected_points=tuple(str(p) for p in raw.get("expected_points", ())),
            )
        )
    if not items:
        raise DatasetError(f"{QSET_FILE} 为空数据集（跑空集会得到「无分母」的假结论）")
    return tuple(items)


def load_multihop_set() -> tuple[MultiHopItem, ...]:
    """加载多跳问题集（含 `hops` 标注与人工判分槽位）。"""
    payload = _read(MULTIHOP_FILE)
    items: list[MultiHopItem] = []
    for raw in _require(payload, "items", where=MULTIHOP_FILE):
        where = f"{MULTIHOP_FILE}#{raw.get('index')}"
        hops = int(_require(raw, "hops", where=where))
        if hops < 2:
            raise DatasetError(f"{where} hops={hops} < 2 ⇒ 不是多跳题，不应进本集")
        correct = raw.get("correct")
        items.append(
            MultiHopItem(
                index=int(_require(raw, "index", where=where)),
                question=str(_require(raw, "question", where=where)),
                hops=hops,
                hop_path=str(raw.get("hop_path", "")),
                expected_points=tuple(str(p) for p in raw.get("expected_points", ())),
                correct=None if correct is None else bool(correct),
                judged_by=raw.get("judged_by"),
            )
        )
    return tuple(items)


def load_affiliation_meta(
    version: str = DEFAULT_AFFILIATION_VERSION,
) -> dict[str, Any]:
    """加载 gold-affiliation 的**元信息**（含实体 id 空间与是否已与真机核对）。

    这个标志位直接决定 C2-a / C2-b **出不出数**——未核对就比对会把"全不命中"
    读成"召回为 0"，误触发反证 F2。
    """
    return _read(_affiliation_file(version))


def _affiliation_member_key() -> str:
    """gold 用哪个字段做匹配键。

    **恒为 ``node_ids``**：真机疑点输出的成员是**图节点 id**
    （``SUBJECT:<税号>`` / ``CONTRACT:...``），而 ``entity_ids``（supplier_id）
    只是人工复核用的可读键 —— 拿 supplier_id 去比对真机输出 ⇒ **恒不命中**
    ⇒ 召回被读成 0 ⇒ 误触发反证 F2（本集初版正是踩了这条，故当时置
    ``verified_against_live_output=false`` 不出数）。
    """
    return "node_ids"


def load_affiliation_gold(
    version: str = DEFAULT_AFFILIATION_VERSION,
) -> tuple[Finding, ...]:
    """加载 M4 隐性关联 gold（**组**级 `Finding`，成员取真机 id 空间）。"""
    name = _affiliation_file(version)
    payload = _read(name)
    key = _affiliation_member_key()
    findings: list[Finding] = []
    for raw in _require(payload, "findings", where=name):
        where = f"{name}#{raw.get('type')}"
        members = tuple(str(m) for m in _require(raw, key, where=where))
        if not members:
            raise DatasetError(
                f"{where} {key} 为空（空成员疑点会让匹配键退化为只看类型）"
            )
        findings.append(
            Finding(type=str(_require(raw, "type", where=where)), entity_ids=members)
        )
    return tuple(findings)


def load_fixture_baseline() -> dict[str, Any]:
    """加载 fixture 基线（**非产品基线**，见该文件 warning）。"""
    return _read(FIXTURE_BASELINE_FILE)


def dataset_versions() -> dict[str, str]:
    """报告用的数据集版本清单（**结论可归因**的前提）。"""
    manifest = load_manifest()
    versions = {"manifest": str(manifest.get("manifest_version", "unknown"))}
    for entry in manifest.get("datasets", []):
        versions[str(entry["id"])] = str(entry.get("version", "unknown"))
    return versions
