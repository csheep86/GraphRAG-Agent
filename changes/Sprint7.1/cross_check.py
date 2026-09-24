"""Sprint 7.1 批次 A：**零成本**交叉核对（不调 LLM，只读抽取产物）。

回答 D6 前置卡口的那个问题：这批语料里到底有没有「**跨公司**共享法人 / 共享地址」？

M4 的两跳是 ``s1 -[:LEGAL_REP]-> X <-[:LEGAL_REP]- s2``，而本批次的
``:Subject`` / ``:LegalPerson`` / ``:Address`` id 由**规范化名称的 sha256** 决定
（同名跨文档合成同一节点）——所以：

- 同一 (公司, 法人) 对在**多份文档重复出现** ⇒ 合并成一条边 ⇒ **不产生疑点**；
- 只有**两个不同的公司**指向同一法人 / 同一地址才产生疑点。

本脚本把 6 片产物摊平后按「共享节点 → 主体集合」聚合，只打印**主体数 ≥ 2** 的组，
并列出每组的来源文档——这就是「疑点能不能成立」的**事前**证据（建图之前就能算）。

用法：``uv run python ../changes/Sprint7.1/cross_check.py --docs <id1,id2,...>``
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from uuid import UUID

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND_DIR))


def _load(document_id: str) -> tuple[list[dict], list[dict], str]:
    import uuid as _uuid

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.models import Document
    from app.storage import build_extract_artifact_key, get_storage

    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    storage = get_storage()
    with Session(engine) as db:
        document = db.get(Document, _uuid.UUID(document_id))
        if document is None:
            raise SystemExit(f"documents 不存在: {document_id}")
        org_id = document.org_id
        label = document_id[:8]

    prefix = build_extract_artifact_key(
        org_id=org_id, doc_id=UUID(document_id), filename="entities.json"
    ).rsplit("/", 1)[0]
    entities = json.loads(
        storage.get(f"{prefix}/entities.json", org_id=org_id).decode("utf-8")
    )
    relations = json.loads(
        storage.get(f"{prefix}/relations.json", org_id=org_id).decode("utf-8")
    )
    return entities, relations, label


def _utf8_console() -> None:
    """Windows 控制台默认 GBK，中文与 ⇒ 之类符号会 UnicodeEncodeError（真机踩到）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - 环境不支持就算了
            pass


def main() -> int:
    _utf8_console()
    parser = argparse.ArgumentParser(description="M4 跨文档交叉核对（只读产物）")
    parser.add_argument("--docs", required=True, help="逗号分隔的 document_id")
    args = parser.parse_args()

    # 共享节点名 → {主体名: [来源文档标签]}
    by_person: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    by_address: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    person_types: dict[str, int] = defaultdict(int)
    address_types: dict[str, int] = defaultdict(int)

    for doc_id in [item.strip() for item in args.docs.split(",") if item.strip()]:
        entities, relations, label = _load(doc_id)
        name_by_id = {
            str(e.get("id")): str(e.get("canonical_name") or "") for e in entities
        }
        type_by_id = {str(e.get("id")): str(e.get("entity_type")) for e in entities}
        for relation in relations:
            rel_type = relation.get("relation_type")
            if rel_type not in ("LEGAL_REP", "REGISTERED_AT"):
                continue
            source = name_by_id.get(str(relation.get("source_entity_id")), "")
            target = name_by_id.get(str(relation.get("target_entity_id")), "")
            target_type = type_by_id.get(str(relation.get("target_entity_id")), "")
            if not source or not target:
                continue
            # 与 builder 同口径：``build_affiliation_rows`` 只看 **关系类型**，
            # 不校验 target 的 entity_type（写成 PERSON 也会落成 :LegalPerson）——
            # 这里若筛类型就会比实际建图更严格，得出偏乐观的「没有交叉」。
            bucket = by_person if rel_type == "LEGAL_REP" else by_address
            bucket[target][source].append(label)
            if rel_type == "LEGAL_REP":
                person_types[target_type] += 1
            else:
                address_types[target_type] += 1

    for kind, bucket in (("共享法人 LEGAL_REP", by_person), ("共享地址 REGISTERED_AT", by_address)):
        print(f"\n===== {kind}：共享节点 → 主体数（只列 ≥2 的组）=====")
        hits = 0
        for shared, subjects in sorted(bucket.items(), key=lambda kv: -len(kv[1])):
            if len(subjects) < 2:
                continue
            hits += 1
            print(f"  [可成疑点] {shared}")
            for subject, labels in subjects.items():
                print(f"      ← {subject}  docs={sorted(set(labels))}")
        if hits == 0:
            print("  （无：所有共享节点都只有 1 个主体 ⇒ 两跳不成立 ⇒ 0 条疑点）")
        print(f"  合计可成疑点的共享节点 = {hits}")

    print("\n===== 全部共享节点（含单主体，供判断「为什么没有」）=====")
    for kind, bucket, types in (
        ("LEGAL_REP", by_person, person_types),
        ("REGISTERED_AT", by_address, address_types),
    ):
        print(f"  {kind}: 共享节点 {len(bucket)} 个，主体分布 "
              f"{sorted({len(v) for v in bucket.values()})}")
        print(f"      target entity_type 分布 {dict(types)}")

    # ---- 诊断：是不是「有共享，但写法不一致」？（只诊断，不改变建图口径）----
    print("\n===== 诊断：地址**归一化**后会不会出现交叉？=====")
    print("  （仅去空白 + 全角空格；用于区分「数据里没有」与「写法不一致」）")
    normalized: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for raw, subjects in by_address.items():
        key = "".join(raw.split()).replace("\u3000", "")
        normalized[key][raw] = []  # 占位：下面按 raw 归并
    merged: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for raw, subjects in by_address.items():
        key = "".join(raw.split()).replace("\u3000", "")
        for subject, labels in subjects.items():
            merged[key][subject].extend(labels)
    found = 0
    for key, subjects in sorted(merged.items(), key=lambda kv: -len(kv[1])):
        if len(subjects) < 2:
            continue
        found += 1
        raws = [r for r in by_address if "".join(r.split()).replace("\u3000", "") == key]
        print(f"  [归一化后可成疑点] 主体数={len(subjects)}")
        for subject in subjects:
            print(f"      ← {subject}")
        for raw in raws:
            print(f"      原文写法: {raw!r}")
    if found == 0:
        print("  （归一化后仍无 ⇒ 这批语料里**确实没有**跨公司共享地址）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
