"""S10 批次 A 真机探针：span「抽取产物 → 入图 → 证据回查 → 引用换算」闭环。

**刻意不依赖 PG**（本机无 PG 服务）：数据源是本地存储里的抽取产物（真实数据，
非构造），写入目标是真 Neo4j。用一个**独立 probe version**，跑完即清理，
不污染 active 版本。

验证四件事（对应 proposal §5 验收）：

1. 写侧：`:Entity.char_start` / `char_end` 是否真的落库（c0 探针时是 0 非空）
2. 读侧：`fetch_evidence_chunks` 是否带出 `entity_spans`
3. 换算：真 chunk + 真 span ⇒ `_to_citation` 给出的 `char_offset` 是否落在
   `(0, len(text))` 区间内（即"不再恒 0"）
4. 回退：不带提及的条目 ⇒ `[0, len(text)]`（整段），不是空白
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from uuid import UUID  # noqa: E402

from app.services.agents import _to_citation  # noqa: E402
from app.services.graphs import GraphService  # noqa: E402
from app.services.kg import ThreeStageKgBuilder  # noqa: E402
from app.services.kg.builder import KgBuildRequest, KgDocumentRef  # noqa: E402
from app.storage import build_extract_artifact_key, get_storage  # noqa: E402

PROBE_VERSION = f"probe-span-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _load_artifact(
    *, org_id: UUID, doc_id: UUID, filename: str
) -> list[dict] | None:
    """读抽取产物；不存在返回 ``None``（CSV 派生的文档没有抽取段，是**正常**的）。"""
    key = build_extract_artifact_key(org_id=org_id, doc_id=doc_id, filename=filename)
    try:
        raw = get_storage().get(key, org_id=org_id)
    except Exception:  # noqa: BLE001 - 探针只挑"有产物"的文档
        return None
    return json.loads(raw.decode("utf-8")) if isinstance(raw, bytes) else json.loads(raw)


def main() -> None:
    graphs = GraphService.instance()
    builder = ThreeStageKgBuilder()

    # ---- 0. 挑一份**有抽取产物**的真实文档 ---------------------------------
    # CSV 派生的文档（考勤域）没有 extract 段——它们本来就没有 span（裁决 D-D），
    # 拿它们验证 span 落库是拿错样本，故逐个试读，取第一个有 `entities.json` 的。
    doc_id = org_id = None
    entities = relations = chunks = None
    with graphs._session() as session:  # noqa: SLF001 - 探针脚本，读真库
        rows = list(
            session.run("MATCH (d:Document) RETURN d.id AS doc_id, d.org_id AS org_id")
        )
    for row in rows:
        candidate_doc = UUID(str(row["doc_id"]))
        candidate_org = UUID(str(row["org_id"]))
        found = _load_artifact(
            org_id=candidate_org, doc_id=candidate_doc, filename="entities.json"
        )
        if not found:
            continue
        doc_id, org_id = candidate_doc, candidate_org
        entities = found
        relations = _load_artifact(
            org_id=org_id, doc_id=doc_id, filename="relations.json"
        )
        chunks = _load_artifact(org_id=org_id, doc_id=doc_id, filename="chunks.json")
        break
    if entities is None or chunks is None or relations is None:
        print(f"没有任何文档带完整抽取产物（共 {len(rows)} 个 :Document）")
        return
    print(f"样本文档: doc_id={doc_id} org_id={org_id}")
    with_span = sum(1 for e in entities if e.get("char_start") is not None)
    print(
        f"产物: entities={len(entities)}（含 span {with_span}）"
        f" relations={len(relations)} chunks={len(chunks)}"
    )

    try:
        # ---- 1. 写侧：真实 builder 写入 probe version -----------------------
        stats = builder.build(
            KgBuildRequest(
                org_id=org_id,
                version=PROBE_VERSION,
                entities=entities,
                relations=relations,
                trace_id=uuid.uuid4(),
                chunks=chunks,
                document=KgDocumentRef(doc_id=doc_id, acl_scope=None),
            )
        )
        print(f"写入: {stats}")

        # ---- 2. 落库核对 ---------------------------------------------------
        with graphs._session() as session:  # noqa: SLF001
            row = session.run(
                "MATCH (e:Entity {kg_version: $v}) "
                "RETURN count(e) AS n, count(e.char_start) AS cs, count(e.char_end) AS ce",
                v=PROBE_VERSION,
            ).single()
        print(f"写侧核对: :Entity 总数={row['n']} char_start 非空={row['cs']} "
              f"char_end 非空={row['ce']}")

        # ---- 3. 读侧：证据回查是否带出 span --------------------------------
        evidence = graphs.fetch_evidence_chunks(
            kg_version=PROBE_VERSION, org_id=org_id, doc_id=doc_id
        )
        with_spans = [c for c in evidence if c.entity_spans]
        print(
            f"读侧核对: chunks={len(evidence)} 带 span 的片段={len(with_spans)} "
            f"span 总数={sum(len(c.entity_spans) for c in evidence)}"
        )

        # ---- 4. 换算：真 chunk + 真 span ⇒ char_offset 不再恒 0 -------------
        index = {c.chunk_id: c for c in evidence}
        hits = 0
        for chunk in with_spans[:5]:
            span = chunk.entity_spans[0]
            citation = _to_citation(f"{chunk.chunk_id}#{span.mention}", index)
            if citation is None:
                print(f"  [MISS] {chunk.chunk_id}#{span.mention}")
                continue
            precise = 0 < citation.char_offset < citation.char_end <= len(chunk.text)
            hits += 1 if precise else 0
            print(
                f"  span 级: {chunk.chunk_id}#{span.mention} → "
                f"[{citation.char_offset}, {citation.char_end}) / len={len(chunk.text)} "
                f"精确命中={precise}"
            )
            # 回退档对照：不带提及
            fallback = _to_citation(chunk.chunk_id, index)
            print(
                f"  回退档: {chunk.chunk_id} → "
                f"[{fallback.char_offset if fallback else None}, "
                f"{fallback.char_end if fallback else None})"
            )
        print(f"结论: span 级精确命中 {hits} / {min(5, len(with_spans))}")
    finally:
        # ---- 5. 清理 probe version（不污染 active）--------------------------
        with graphs._session() as session:  # noqa: SLF001
            session.run(
                "MATCH (n) WHERE n.kg_version = $v DETACH DELETE n", v=PROBE_VERSION
            )
            session.run(
                "MATCH (v:KgVersionMirror {version: $v}) DETACH DELETE v",
                v=PROBE_VERSION,
            )
        print(f"已清理 probe version: {PROBE_VERSION}")


if __name__ == "__main__":
    main()
