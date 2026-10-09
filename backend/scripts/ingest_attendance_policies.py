"""考勤制度文档 → M1 解析 + M2 抽取 → 入图（Sprint 9.5 批次 B2 / B3）。

用法（工作目录 = ``backend/``）::

    uv run python scripts/ingest_attendance_policies.py
    uv run python scripts/ingest_attendance_policies.py --only worktime-system-rules
    uv run python scripts/ingest_attendance_policies.py --force       # 清产物重跑
    uv run python scripts/ingest_attendance_policies.py --no-bridge   # 不建汇合边

设计要点：

1. **完全复用既有链路，不另起炉灶**：M1 走 ``document.parse``（MinerU 云，docx
   后缀——Sprint 9.5 B2 起支持）、M2 走 ``document.extract``（LangExtract +
   ``kg_extraction_v2``），末段 ``kg.build`` 三段式写 Neo4j。
   **不新增 Prompt 版本**：``entity_types`` / ``relation_types`` 已由 M6 §5.2
   参数化注入（``document.extract`` 读该 org 的 active 本体，见
   ``app/tasks/registry.py::_do_extract``）。
2. **与 CSV 落到同一个 ``kg_version``**（``attendance-demo-v1``）：
   ``ThreeStageKgBuilder`` 是 MERGE 追加语义（**不**先清版本），两条链路因此天然汇合；
   若各自新建版本，B3 那条「员工 → 岗位 → 工时制 → 条款」的跨源路径永远连不上。
3. **汇合规则是确定性的**：``WORK_TIME_SYSTEM -[GOVERNED_BY]-> POLICY_CLAUSE``
   按「条款正文出现该工时制名称」匹配，**不由 LLM 生成**——跨越关系是要被演示用例
   核查的结构事实，交给模型等于让 DEMO 结论不可复核。
4. **入图 ≠ 可查**（B1 的老教训）：每份文档的 ``kg.build`` 只登记**它自己**的计数，
   故全部跑完后必须按 Neo4j **真实计数**重新 ``mark_ready``，
   再回读 B3 验收路径 —— 只看脚本打印等于没验证。

运行次序：**先跑** ``ingest_attendance_csv.py`` 再跑本脚本。两者写入同一
``kg_version``：CSV 派生节点 id 形如 ``<ENTITY_TYPE>:<主键>``，本脚本产物为
``ent_*``，**互不覆盖**。

重跑 CSV 请用 ``--purge-csv``（**只**清 CSV 派生前缀，保留本脚本的 span 产物）；
``--purge`` 会清空整个版本（含本脚本产物），用过它之后**必须重跑本脚本**。

> 2026-09-28 修正：CSV 脚本的写入自检与失败补偿原先按**整个** ``kg_version``
> 计数 / 删除。在"CSV 与抽取结果同版本共存"的场景下这会在两方面出错：
> ① 自检把 span 实体算进实际计数 ⇒ 恒报"写入自检失败"；
> ② 失败补偿把 span 实体**连带删掉**（重跑本脚本要重烧 MinerU + LLM）。
> 现均已改为按**本次提交的 id** 计数与回滚。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 同 ``ingest_attendance_csv.py``：脚本方式跑时 ``scripts/`` 由解释器自动入路径，
# 被 pytest 以包路径导入时不在 ⇒ 必须显式补，否则 ``_bridge_window`` 解析失败。
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# 派生边窗口继承（ADR-0005 §4 增补）：与 CSV 脚本共用同一份口径与同一句 Cypher，
# 免得同形状的 GOVERNED_BY 一边有日期一边没有。
# 见 changes/P6-U/11-derived-window-inheritance.md
from _bridge_window import (  # noqa: E402
    DEFAULT_SCOPE_STORE,
    apply_clause_window,
    clause_windows,
    document_window,
    record_document_scope,
)

from app.core.config import get_settings  # noqa: E402
from app.db.models import Document  # noqa: E402
from app.db.session import init_db, open_session  # noqa: E402
from app.services.kg.versioning import KgVersioningService  # noqa: E402
from app.storage import (  # noqa: E402
    build_extract_artifact_key,
    build_parse_artifact_key,
    build_storage_key,
    get_storage,
)
from app.tasks.registry import (  # noqa: E402
    document_extract_executor,
    document_parse_executor,
    kg_build_executor,
)
from app.tasks.types import TaskSpec  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
CORPUS_DIR = REPO_ROOT / "demo" / "attendance" / "corpus"
EMPLOYEES_CSV = CORPUS_DIR / "employees.csv"

#: 制度文档（Demo 语料，**仿真**数据）
#:
#: 2026-09-30（Sprint 10.5）新增两份 **2025 版**：它们不是"多放两份文档"，
#: 而是知识的**历史态**——L2 的失效视觉语义与全生命周期 as-of 要求图上真有
#: ``valid_to`` 非空的边，而通用层拿不到 L1 仲裁（见 ``builder.py:1100`` 的注释），
#: ``valid_to`` 只能来自抽取；抽取的规则是「**只有文本明确写了失效日期才填**」
#: （``prompts/kg_extraction_v3.md`` 字段约束 5）⇒ 2025 版的附则必须明写
#: 「有效期至 2025 年 12 月 31 日」。差异点仅一处（外勤缺卡补卡由手工变自动），
#: 且这一处是 **2026 版自己宣称的**，不是这里替它编的。
POLICY_FILES: tuple[str, ...] = (
    "attendance-policy-2025.docx",
    "attendance-policy-2026.docx",
    "fieldwork-attendance-rules-2025.docx",
    "fieldwork-attendance-rules.docx",
    "overtime-and-comp-off.docx",
    "worktime-system-rules.docx",
)
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DEFAULT_KG_VERSION = "attendance-demo-v1"

#: 汇合边的任务名 / 事件（多段定义此，git diff 时一眼能看懂或缺了什么）
HEAD_ENTITY_TYPE = "WORK_TIME_SYSTEM"
TAIL_ENTITY_TYPE = "POLICY_CLAUSE"
BRIDGE_RELATION_TYPE = "GOVERNED_BY"
WORK_TIME_SYSTEM_KEY = "WORK_TIME_SYSTEM"

#: M2 抽取时的切片粒度（制度文档按"条"抽取，见 parse_and_extract 实测注释）
CLAUSE_CHARS_PER_CHUNK = 600


class IngestError(Exception):
    """制度文档入图流程的业务错误。"""


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _document_id(stem: str) -> uuid.UUID:
    """确定性文档 id：重跑脚本能复用同一行 / 同一批产物。

    用 uuid5 而非随机 uuid4——否则每跑一次就多一份孤儿 Document 行与存储产物，
    既污染 `/documents` 列表，也让"这份文档到底有没有抽成功"无法核对。
    """
    return uuid.uuid5(
        uuid.NAMESPACE_URL, f"urn:graphrag-agent:demo:attendance:policy-doc:{stem}"
    )


def _artifact_keys(
    *, org_id: uuid.UUID, doc_id: uuid.UUID, source_name: str
) -> list[str]:
    """该文档的全部阶段产物键（源文件 + parse + extract），供 ``--force`` 清理。"""
    return [
        build_storage_key(
            org_id=org_id,
            doc_id=doc_id,
            filename_hash=hashlib.sha256(source_name.encode("utf-8")).hexdigest(),
        ),
        build_parse_artifact_key(org_id=org_id, doc_id=doc_id, filename="full.md"),
        build_parse_artifact_key(
            org_id=org_id, doc_id=doc_id, filename="content_list.json"
        ),
        build_extract_artifact_key(
            org_id=org_id, doc_id=doc_id, filename="entities.json"
        ),
        build_extract_artifact_key(
            org_id=org_id, doc_id=doc_id, filename="relations.json"
        ),
        build_extract_artifact_key(
            org_id=org_id, doc_id=doc_id, filename="chunks.json"
        ),
    ]


def _read_json_artifact(*, org_id: uuid.UUID, doc_id: uuid.UUID, filename: str) -> Any:
    key = build_extract_artifact_key(org_id=org_id, doc_id=doc_id, filename=filename)
    return json.loads(get_storage().get(key, org_id=org_id).decode("utf-8"))


def _write_json_artifact(
    *, org_id: uuid.UUID, doc_id: uuid.UUID, filename: str, payload: Any
) -> None:
    key = build_extract_artifact_key(org_id=org_id, doc_id=doc_id, filename=filename)
    get_storage().put(key, json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def run_stage(
    executor: Any,
    *,
    task_type: str,
    doc_id: uuid.UUID,
    org_id: str,
    extra_payload: Mapping[str, Any] | None = None,
) -> None:
    """同步驱动一个管线段（执行体是 async，脚本侧用 ``asyncio.run`` 直接跑）。"""
    payload: dict[str, Any] = {"document_id": str(doc_id)}
    if extra_payload:
        payload.update(dict(extra_payload))
    asyncio.run(
        executor(
            TaskSpec(
                task_type=task_type,
                payload=payload,
                trace_id=str(uuid.uuid4()),
                #: **P6-D（2026-10-05）**：``org_id`` 现在是 ``TaskSpec`` 的**必填位**
                #: （G-26 判据 ⑩ + ADR：应用入口必须显式绑 org）。脚本此前没传 ⇒
                #: 一进来就 ``TypeError`` ⇒ L2 的 M1/M2 两段**根本跑不起来**
                #: （本批正是靠它定位到：该脚本从未在当前代码上跑通过）。
                org_id=str(org_id),
            )
        )
    )


# --------------------------------------------------------------------------- #
# 步骤 1：登记 Document 行 + 落源文件
# --------------------------------------------------------------------------- #
def prepare_document(
    *, db: Any, doc_id: uuid.UUID, source_path: Path, force: bool
) -> None:
    """确保 ``documents`` 行存在且源文件在存储层（幂等）。"""
    settings = get_settings()
    file_name = source_path.name
    filename_hash = hashlib.sha256(file_name.encode("utf-8")).hexdigest()
    content = source_path.read_bytes()

    if force:
        # 执行体对 completed 是"早 return"，不清产物等于重跑空转
        existing_row = db.get(Document, doc_id)
        if existing_row is not None:
            db.delete(existing_row)
            db.commit()
        for key in _artifact_keys(
            org_id=settings.default_org_id, doc_id=doc_id, source_name=file_name
        ):
            get_storage().delete(key)

    existing = db.get(Document, doc_id)
    if existing is None:
        db.add(
            Document(
                id=doc_id,
                filename_hash=filename_hash,
                mime_type=DOCX_MIME,
                size_bytes=len(content),
                status="pending",
                uploaded_by=settings.default_actor_id,
                org_id=settings.default_org_id,
                trace_id=uuid.uuid4(),
            )
        )
        db.commit()
        print(f"  [1/5] 新建 Document 行 {doc_id}（pending）")
    else:
        print(
            f"  [1/5] 复用 Document 行 {doc_id}"
            f"（status={existing.status} extract={existing.extract_status} "
            f"kg_build={existing.kg_build_status}）"
        )

    key = build_storage_key(
        org_id=settings.default_org_id,
        doc_id=doc_id,
        filename_hash=filename_hash,
    )
    get_storage().put(key, content)
    print(f"  [1/5] 源文件入存储层：{file_name}（{len(content)} bytes）")


def assert_stage_completed(
    *, db: Any, doc_id: uuid.UUID, status_field: str, expected: str
) -> None:
    """回读阶段列；执行体吞错后只改状态列，不回抛 ⇒ 必须自己读回来判定。"""
    db.expire_all()
    document = db.get(Document, doc_id)
    if document is None:
        raise IngestError(f"文档行丢失: {doc_id}")
    actual = getattr(document, status_field)
    if actual != expected:
        raise IngestError(
            f"{status_field} 期望 {expected!r}，实际 {actual!r}"
            f"（error_code={document.error_code}）"
        )


# --------------------------------------------------------------------------- #
# 步骤 2/3：M1 解析 → M2 抽取
# --------------------------------------------------------------------------- #
def parse_and_extract(*, db: Any, doc_id: uuid.UUID) -> str:
    """跑 ``document.parse`` → ``document.extract``，返回 full.md 原文。"""
    settings = get_settings()
    org_id = settings.default_org_id

    run_stage(
        document_parse_executor,
        task_type="document.parse",
        doc_id=doc_id,
        org_id=org_id,
    )
    assert_stage_completed(
        db=db, doc_id=doc_id, status_field="status", expected="completed"
    )

    md_key = build_parse_artifact_key(org_id=org_id, doc_id=doc_id, filename="full.md")
    try:
        markdown = get_storage().get(md_key, org_id=org_id).decode("utf-8")
    except Exception as exc:  # noqa: BLE001 - 缺产物是硬失败，不是降级
        raise IngestError(
            f"M1 未产出 full.md（key={md_key}）：{exc}"
            "——解析被跳过或产物未写入，绝不能当作“抽完了只是没实体”"
        ) from exc
    if not markdown.strip():
        raise IngestError(f"{doc_id} 的 full.md 为空")
    print(f"  [2/5] M1 解析产物 full.md（{len(markdown)} 字符）")

    run_stage(
        document_extract_executor,
        task_type="document.extract",
        doc_id=doc_id,
        org_id=org_id,
        # 沿条款切片（**实测**：同文档 4000 字切片只抽到 1 条 POLICY_CLAUSE，
        # 600 字切片抽到 16 条）——制度文档的抽取单元是"条"，不是"篇"
        extra_payload={"max_chars_per_chunk": CLAUSE_CHARS_PER_CHUNK},
    )
    assert_stage_completed(
        db=db, doc_id=doc_id, status_field="extract_status", expected="completed"
    )
    return markdown


def load_extraction(
    *, org_id: uuid.UUID, doc_id: uuid.UUID
) -> tuple[list[Any], list[Any]]:
    """读 entities.json / relations.json。"""
    entities = _read_json_artifact(
        org_id=org_id, doc_id=doc_id, filename="entities.json"
    )
    relations = _read_json_artifact(
        org_id=org_id, doc_id=doc_id, filename="relations.json"
    )
    if not isinstance(entities, list) or not isinstance(relations, list):
        raise IngestError(f"{doc_id} 抽取产物结构非法（应为 list）")
    return entities, relations


def _dedupe_relations(rows: Sequence[Mapping[str, Any]]) -> list[Any]:
    """按 ``id`` 去重（保序）。

    **为什么需要**：桥接边是确定性 id ⇒ 重复跑脚本会把同样的边**再追加一遍**，
    MERGE 虽会去重但 `relations.json` 会越来越长、打印的计数不再可信（实测曾由此
    出现"预期 91 条、实写 90 条"的凭空错位）。写回前先去重，计数才有意义。
    """
    seen: set[str] = set()
    out: list[Any] = []
    for row in rows:
        key = str(row.get("id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(dict(row))
    return out


def count_by_type(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "<none>")
        out[value] = out.get(value, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


# --------------------------------------------------------------------------- #
# 步骤 4：两链路汇合（确定性桥接）
# --------------------------------------------------------------------------- #
def load_work_time_systems(
    *, driver: Any, database: str, kg_version: str, org_id: uuid.UUID
) -> dict[str, str]:
    """从 Neo4j 读 CSV 侧已入图的 ``WORK_TIME_SYSTEM`` 节点：``{名称: 节点 id}``。

    **以图为准而不是读 CSV**：桥接的成败取决于"那条边能不能 MATCH 到节点"，
    图里有什么才是唯一裁决口径（读 CSV 会让人以为接上了、实际 MERGE 时静默丢边）。
    """
    cypher = (
        f"MATCH (n:Entity {{entity_type: '{WORK_TIME_SYSTEM_KEY}', "
        "kg_version: $kg_version, org_id: $org_id}) "
        "RETURN n.id AS id, n.canonical_name AS name ORDER BY n.id"
    )
    with driver.session(database=database) as session:
        records = list(session.run(cypher, kg_version=kg_version, org_id=str(org_id)))

    systems = {str(record["name"]): str(record["id"]) for record in records}
    if not systems:
        raise IngestError(
            f"kg_version={kg_version} 里没有 {WORK_TIME_SYSTEM_KEY} 节点——"
            "请先跑 scripts/ingest_attendance_csv.py（B1 未入图则本脚本无事可做）"
        )
    print(f"  [4/5] 图内工时制节点 {len(systems)} 个：{', '.join(systems)}")
    return systems


#: 判据文本的上下文上限（字符）：条款可能很长，但不至于把整章也算进来
_CONTEXT_LIMIT = 1200


def _clause_text(entity: Mapping[str, Any], markdown: str) -> str:
    """条款的判据文本：**mention 所在的那一段** + mention + canonical_name。

    **为什么必须带上下文**：M2 是 span 级抽取，``POLICY_CLAUSE`` 的 mention 常常
    只有「第十一条」三个字，凭它判不出这条条款讲的是哪个工时制；而条款正文里
    才有「标准工时制」这类关键词（``mapping.yaml`` §汇合 的匹配口径也是"条款正文"）。
    取**自然段**而非固定窗口，是为了边界确定、可复核——同一份语料多次跑必须同解。
    """
    parts = [
        str(entity.get("canonical_name") or ""),
        str(entity.get("mention") or ""),
    ]
    start, end = entity.get("char_start"), entity.get("char_end")
    if isinstance(start, int) and isinstance(end, int):
        if 0 <= start < end <= len(markdown):
            block_start = markdown.rfind("\n\n", max(start - _CONTEXT_LIMIT, 0), start)
            block_start = 0 if block_start < 0 else block_start + 2
            block_end = markdown.find(
                "\n\n", end, min(end + _CONTEXT_LIMIT, len(markdown))
            )
            block_end = len(markdown) if block_end < 0 else block_end
            parts.append(markdown[block_start:block_end])
    return " ".join(parts)


def bridge_governed_by(
    *,
    markdown: str,
    entities: Sequence[Mapping[str, Any]],
    systems: Mapping[str, str],
    windows: Mapping[str, tuple[str | None, str | None]] | None = None,
    fallback: tuple[str | None, str | None] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """给 ``POLICY_CLAUSE`` 加 ``WORK_TIME_SYSTEM -[GOVERNED_BY]-> POLICY_CLAUSE``。

    规则（确定性，非 LLM）：条款判据文本里出现某个工时制的名称即连一条边。
    边的 id 取 ``uuid5(head|tail)`` ⇒ **重跑幂等**（MERGE 同一条边）。

    :param windows: 条款窗口表（:func:`_bridge_window.clause_windows`）。本边是
        **派生边**：它的有效期定义上等于所指条款的有效期 ⇒ 继承条款窗口
        （ADR-0005 §4 增补）。条款窗口不唯一或缺失 ⇒ 不写，绝不补值。
    :param fallback: **文档窗口**（R4-b 兜底）：条款自身没有候选窗口时才轮到它，
        绝不覆盖条款自身的窗口（见 :func:`_bridge_window.apply_clause_window`）。
        文档自己没声明 ⇒ ``None`` ⇒ 该边保持无日期。
    """
    added: list[dict[str, Any]] = []
    per_system: dict[str, int] = {name: 0 for name in systems}
    unmatched = 0
    # 三态计数必须可见（可观测性规范）：继承 / 文档兜底 / 仍无窗口各有多少。
    # 静默地把 66 条里的绝大部分变成"有窗口"却不说来源，等于把口径变更藏起来。
    inherited = 0
    doc_scope = 0
    no_window = 0

    for entity in entities:
        if str(entity.get("entity_type")) != TAIL_ENTITY_TYPE:
            continue
        text = _clause_text(entity, markdown)
        hits = [name for name in systems if name and name in text]
        if not hits:
            unmatched += 1
            continue
        clause_id = str(entity.get("id") or "").strip()
        if not clause_id:
            continue
        for name in hits:
            head_id = systems[name]
            stable = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"urn:graphrag-agent:demo:attendance:goistby:{head_id}|{clause_id}",
            ).hex[:12]
            row = {
                # ``rel-bridge-`` 前缀标明**规则桥接**的来源：模型也会抽到
                # GOVERNED_BY（端点在文档内部），混在一起就无法回答
                # "这两条链路到底汇合了几条边"。
                "id": f"rel-bridge-{stable}",
                "source_entity_id": head_id,
                "target_entity_id": clause_id,
                "relation_type": BRIDGE_RELATION_TYPE,
                "evidence": text[:200],
                "confidence": 1.0,  # 确定性规则：命中即成立，非模型置信度
            }
            own = (windows or {}).get(clause_id)
            if own is not None:
                inherited += 1
            elif fallback is not None:
                doc_scope += 1
            else:
                no_window += 1
            added.append(
                apply_clause_window(
                    row,
                    windows=windows or {},
                    tail_id=clause_id,
                    fallback=fallback,
                )
            )
            per_system[name] += 1

    return added, {
        "unmatched": unmatched,
        "inherited": inherited,
        "doc_scope": doc_scope,
        "no_window": no_window,
        **per_system,
    }


# --------------------------------------------------------------------------- #
# Neo4j 回读（真机校验）
# --------------------------------------------------------------------------- #
_CYPHER_COUNT_GRAPH = """
MATCH (n:Entity {kg_version: $kg_version})
WITH count(n) AS entity_count
MATCH ()-[r:RELATION {kg_version: $kg_version}]->()
RETURN entity_count AS entity_count, count(r) AS relation_count
"""

_CYPHER_COUNT_TYPE = """
MATCH (n:Entity {entity_type: $entity_type, kg_version: $kg_version})
RETURN count(n) AS c
"""

_CYPHER_COUNT_RELATION = """
MATCH ()-[r:RELATION {relation_type: $relation_type, kg_version: $kg_version}]->()
RETURN count(r) AS c
"""

#: 按 id 逐个核对"本次预期写入的所有关系"（不限 relation_type）
_CYPHER_COUNT_RELATION_IDS = """
MATCH ()-[r:RELATION {kg_version: $kg_version}]->()
WHERE r.id IN $ids
RETURN count(DISTINCT r) AS c
"""

#: **只数本次桥接产生的边**（按 id 精确核对）
#: 为什么不是"按 relation_type 数全部"：模型自己也会抽到 GOVERNED_BY（端点在
#: 文档内部），把它们算进来就无法判断"这两条链路到底汇合了几条边"；而本次写入的
#: 边 id 是已知的 ⇒ 精确比对才能真正拦住静默丢失。
_CYPHER_COUNT_BRIDGE_EDGES = """
MATCH ()-[r:RELATION {kg_version: $kg_version}]->()
WHERE r.relation_type = $relation_type AND r.id IN $ids
RETURN count(DISTINCT r) AS c
"""

_CYPHER_B3_PATH = """
MATCH (e:Entity {entity_type: 'EMPLOYEE', kg_version: $kg_version})
      -[:RELATION {relation_type: 'HAS_POSITION'}]->
      (p:Entity {entity_type: 'POSITION'})
      -[:RELATION {relation_type: 'APPLIES_WORK_TIME'}]->
      (w:Entity {entity_type: 'WORK_TIME_SYSTEM'})
      -[:RELATION {relation_type: 'GOVERNED_BY'}]->
      (c:Entity {entity_type: 'POLICY_CLAUSE'})
RETURN count(*) AS paths,
       count(DISTINCT e) AS employees,
       count(DISTINCT w) AS systems,
       count(DISTINCT c) AS clauses
"""

_CYPHER_SAMPLE_PATHS = """
MATCH (e:Entity {entity_type: 'EMPLOYEE', kg_version: $kg_version})
      -[:RELATION {relation_type: 'HAS_POSITION'}]->
      (p:Entity {entity_type: 'POSITION'})
      -[:RELATION {relation_type: 'APPLIES_WORK_TIME'}]->
      (w:Entity {entity_type: 'WORK_TIME_SYSTEM'})
      -[:RELATION {relation_type: 'GOVERNED_BY'}]->
      (c:Entity {entity_type: 'POLICY_CLAUSE'})
RETURN DISTINCT e.canonical_name AS employee, w.canonical_name AS work_time,
       c.canonical_name AS clause
ORDER BY employee, clause
LIMIT 12
"""


def _scalar(session: Any, cypher: str, **params: Any) -> int:
    record = session.run(cypher, **params).single()
    value = record[0] if record else 0
    return int(value or 0)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def process_document(
    *,
    db: Any,
    driver: Any,
    database: str,
    kg_version: str,
    kg_version_id: uuid.UUID,
    org_id: uuid.UUID,
    source_path: Path,
    systems: Mapping[str, str],
    force: bool,
    with_bridge: bool,
) -> dict[str, Any]:
    """单份文档：登记 → M1 → M2 → 桥接 → kg.build。"""
    print(f"\n----- {source_path.name} -----")
    doc_id = _document_id(source_path.stem)
    prepare_document(db=db, doc_id=doc_id, source_path=source_path, force=force)

    markdown = parse_and_extract(db=db, doc_id=doc_id)
    entities, relations = load_extraction(org_id=org_id, doc_id=doc_id)
    entity_dist = count_by_type(entities, "entity_type")
    print(
        f"  [3/5] M2 抽取：实体 {len(entities)} / 关系 {len(relations)}"
        f" | 分布 {', '.join(f'{k}={v}' for k, v in entity_dist.items())}"
    )
    clause_count = entity_dist.get(TAIL_ENTITY_TYPE, 0)
    if clause_count == 0:
        raise IngestError(
            f"{source_path.name} 未抽出任何 {TAIL_ENTITY_TYPE}——"
            "本体词表注入后模型没产出该类型，属抽取失败，**不得**当成“这份文档没有条款”"
        )

    if with_bridge:
        # 派生边继承条款窗口（ADR-0005 §4 增补）：先算窗口表再连边。
        # 三项计数必须可见 —— 继承了多少、放弃了多少，不得静默。
        with driver.session(database=database) as bridge_session:
            windows, wstats = clause_windows(bridge_session, kg_version=kg_version)
        print(
            "  [4/5] 条款窗口：可继承 "
            f"{wstats['one']} / 多义弃用 {wstats['many']} / 无窗口 {wstats['none']}"
        )
        # **R4-b 文档级作用域继承**：只有这里知道"这批条款出自哪份文件"
        # （图里不存在 条款→文档 的链接，见 12 号口径记录 §1 的实测）。
        # 窗口两侧都读不出 ⇒ (None, None) ⇒ 该文档对无窗口条款不提供兜底，保持不猜。
        doc_window, doc_src = document_window(text=markdown)
        print(
            f"  [4/5] 文档窗口 {doc_src} ⇒ {doc_window[0]} ~ {doc_window[1]}"
            f"（来源：{source_path.name}）"
        )
        # 登记册：**CSV 入图器也要这份结论**，但它没有文档上下文，读这里即可。
        # 跨文档冲突在此剔除（歧义条款两版都留无日期，不猜用哪版）。
        clause_ids = [
            str(item.get("id") or "").strip()
            for item in entities
            if str(item.get("entity_type")) == TAIL_ENTITY_TYPE
        ]
        same, conflict, total = record_document_scope(
            store=DEFAULT_SCOPE_STORE, clause_ids=clause_ids, window=doc_window
        )
        print(
            f"  [4/5] 文档作用域登记：一致 {same} / 冲突剔除 {conflict}"
            f" / 累计 {total} 条"
        )
        added, bridge_stats = bridge_governed_by(
            markdown=markdown,
            entities=entities,
            systems=systems,
            windows=windows,
            fallback=doc_window,
        )
        if not added:
            # 单份文档零命中是**合法的**（例如考勤总纲条款讲的是打卡 / 补卡，
            # 并不点名任何工时制）。真正的阻塞是"全部文档都没连上"，那才是 B3 失败。
            print(
                f"  [warn] {source_path.name} 的 {clause_count} 条条款无一命中工时制"
                "（本份不参与汇合）"
            )
        # 桥接边每次重算 ⇒ 必须**替换**同 id 的旧行：``_dedupe_relations`` 保序留
        # **首次**出现的行（见其 docstring），直接 list+added 会让本轮带窗口的新行
        # 被 artifacts 里上一轮遗留的无窗口行盖掉 ⇒ 窗口继承静默失效。
        added_ids = {str(item.get("id")) for item in added if item.get("id")}
        relations = [row for row in relations if str(row.get("id")) not in added_ids]
        relations = _dedupe_relations(list(relations) + added)
        _write_json_artifact(
            org_id=org_id, doc_id=doc_id, filename="relations.json", payload=relations
        )
        print(
            f"  [4/5] 汇合边 {BRIDGE_RELATION_TYPE} +{len(added)}"
            f"（按工时制：{', '.join(f'{k}={v}' for k, v in bridge_stats.items())}）"
        )
    else:
        print("  [4/5] --no-bridge：跳过汇合边")

    expected_relations = len(relations)
    run_stage(
        kg_build_executor,
        task_type="kg.build",
        doc_id=doc_id,
        org_id=org_id,
        extra_payload={"kg_version_id": str(kg_version_id)},
    )
    assert_stage_completed(
        db=db, doc_id=doc_id, status_field="kg_build_status", expected="completed"
    )
    print(f"  [5/5] kg.build → {kg_version} completed（关系 {expected_relations} 条）")

    return {
        "file": source_path.name,
        "doc_id": doc_id,
        "entities": len(entities),
        "clauses": clause_count,
        "relations": len(relations),
        "relation_ids": [str(item["id"]) for item in relations if item.get("id")],
        "bridge_edges": len(added),
        "bridge_ids": [str(item["id"]) for item in added] if with_bridge else [],
        "markdown_chars": len(markdown),
    }


def ensure_kg_version(*, db: Any, org_id: uuid.UUID, version: str) -> uuid.UUID:
    """复用（无则新建）目标 kg_version 行；制度建设与 CSV 共用一个版本是 B3 的前提。"""
    svc = KgVersioningService(db)
    existing = svc.get_by_version(org_id=org_id, version=version)
    if existing is None:
        existing = svc.create_pending(
            org_id=org_id,
            version=version,
            source_doc_ids=[],
            trace_id=uuid.uuid4(),
        )
        print(f"[PG] 新建版本行 {version}（pending）")
    else:
        print(f"[PG] 复用版本行 {version}（status={existing.status}）")
    return uuid.UUID(str(existing.id))


def verify_and_close(
    *,
    db: Any,
    driver: Any,
    database: str,
    kg_version: str,
    kg_version_id: uuid.UUID,
    org_id: uuid.UUID,
    expected_bridge_ids: Sequence[str],
    expected_relation_ids: Sequence[str],
    reports: Sequence[Mapping[str, Any]],
) -> int:
    """重算真实计数 → mark_ready → 回读 B3 验收路径。"""
    print("\n===== 入图校验（Neo4j 实读） =====")
    with driver.session(database=database) as session:
        record = session.run(_CYPHER_COUNT_GRAPH, kg_version=kg_version).single()
        entity_count = int(record["entity_count"]) if record else 0
        relation_count = int(record["relation_count"]) if record else 0
        clause_nodes = _scalar(
            session,
            _CYPHER_COUNT_TYPE,
            entity_type=TAIL_ENTITY_TYPE,
            kg_version=kg_version,
        )
        # 两数都读：模型自己抽的 GOVERNED_BY（文档内部端点）与规则桥接边（跨源）
        bridge_all = _scalar(
            session,
            _CYPHER_COUNT_RELATION,
            relation_type=BRIDGE_RELATION_TYPE,
            kg_version=kg_version,
        )
        bridge_edges = _scalar(
            session,
            _CYPHER_COUNT_BRIDGE_EDGES,
            relation_type=BRIDGE_RELATION_TYPE,
            kg_version=kg_version,
            ids=list(expected_bridge_ids),
        )
        # 全部预期关系id 逐个核对：Cypher 对"端点不存在的边"是**静默跳过**
        # （不报错、不计数）⇒ 不按 id 查就会把丢失当成成功。
        written_relations = _scalar(
            session,
            _CYPHER_COUNT_RELATION_IDS,
            kg_version=kg_version,
            ids=list(expected_relation_ids),
        )
        path = session.run(_CYPHER_B3_PATH, kg_version=kg_version).single()
        paths = int(path["paths"]) if path else 0
        employees = int(path["employees"]) if path else 0
        systems_hit = int(path["systems"]) if path else 0
        clauses_hit = int(path["clauses"]) if path else 0

    expected_clauses = sum(int(item["clauses"]) for item in reports)

    print(f"  版本 {kg_version}：Entity={entity_count} / Relation={relation_count}")
    print(f"  {TAIL_ENTITY_TYPE} 节点：{clause_nodes}（抽取侧合计 {expected_clauses}）")
    print(
        f"  {BRIDGE_RELATION_TYPE} 边：共 {bridge_all} 条"
        f"（本次规则桥接 {bridge_edges}/{len(expected_bridge_ids)}"
        f" + 模型抽取 {bridge_all - bridge_edges}）"
    )
    ok_relations = written_relations == len(set(expected_relation_ids))
    ok_clauses = clause_nodes == expected_clauses
    ok_bridge = bridge_edges == len(expected_bridge_ids) and bridge_edges > 0
    print(
        f"  本次写入关系：{written_relations}/{len(set(expected_relation_ids))}"
        "（按 id 逐个核对）"
    )
    print(f"  [{'OK ' if ok_relations else 'FAIL'}] 关系无静默丢失")
    print(f"  [{'OK ' if ok_clauses else 'FAIL'}] 条款数一致（防止静默丢失）")
    print(f"  [{'OK ' if ok_bridge else 'FAIL'}] 汇合边数一致且非空")

    print(
        f"\n  B3 验收路径 EMPLOYEE→…→{TAIL_ENTITY_TYPE}："
        f"路径 {paths} 条 / 员工 {employees} 人 / 工时制 {systems_hit} 个 / "
        f"条款 {clauses_hit} 条"
    )
    ok_path = paths > 0 and employees > 0
    print(f"  [{'OK ' if ok_path else 'FAIL'}] 两链路汇合可查")

    if ok_path:
        with driver.session(database=database) as session:
            print("  样例路径（员工 / 工时制 / 条款）：")
            for row in session.run(_CYPHER_SAMPLE_PATHS, kg_version=kg_version):
                print(
                    f"    - {row['employee']} → {row['work_time']} → "
                    f"{str(row['clause'])[:40]}"
                )

    # 入图 ≠ 可查：PG 是 kg_version 真源，必须按**全版本真实计数**重新登记
    # 否则该行停留在最后一个文档的局部计数（读侧看到的是错的元数据）。
    svc = KgVersioningService(db)
    svc.mark_building(kg_version_id)
    svc.mark_ready(
        kg_version_id, entity_count=entity_count, relation_count=relation_count
    )
    print(
        f"\n  [PG] {kg_version} -> ready"
        f"（全版本真实计数：实体 {entity_count} / 关系 {relation_count}）"
    )

    return 0 if (ok_relations and ok_clauses and ok_bridge and ok_path) else 1


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if (
            stream
            and stream.encoding
            and stream.encoding.lower() not in ("utf-8", "utf8")
        ):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(
        description="考勤制度文档 → M1 解析 + M2 抽取 → 与 CSV 图谱汇合（批次 B2 / B3）"
    )
    parser.add_argument("--kg-version", default=DEFAULT_KG_VERSION)
    parser.add_argument("--only", help="只处理该文件名（不含扩展名）")
    parser.add_argument("--force", action="store_true", help="清产物后重跑全流程")
    parser.add_argument("--no-bridge", action="store_true", help="不建立汇合边")
    args = parser.parse_args(argv)

    settings = get_settings()
    org_id = settings.default_org_id
    init_db()

    files = [
        CORPUS_DIR / name
        for name in POLICY_FILES
        if (args.only is None or name == f"{args.only}.docx")
    ]
    if not files:
        print(f"[FAIL] 没有匹配的文件：--only {args.only}", file=sys.stderr)
        return 1
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        print(f"[FAIL] 语料缺失：{missing}", file=sys.stderr)
        return 1

    if not settings.neo4j_password:
        print("[FAIL] NEO4J_PASSWORD 未配置，请检查 backend/.env", file=sys.stderr)
        return 1

    print("===== ingest_attendance_policies =====")
    print(f"kg_version : {args.kg_version}")
    print(f"文档数量   : {len(files)}")

    from neo4j import GraphDatabase  # type: ignore[import-not-found]

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        connection_timeout=10.0,
    )
    bridge_ids: list[str] = []
    relation_ids: list[str] = []
    try:
        driver.verify_connectivity()
        # A4：入图/登记 PG 的 org 来自脚本入参（操作员显式给）
        with open_session(org_id=org_id) as db:
            kg_version_id = ensure_kg_version(
                db=db, org_id=org_id, version=args.kg_version
            )
            systems = load_work_time_systems(
                driver=driver,
                database=settings.neo4j_database,
                kg_version=args.kg_version,
                org_id=org_id,
            )
            reports: list[dict[str, Any]] = []
            for path in files:
                report = process_document(
                    db=db,
                    driver=driver,
                    database=settings.neo4j_database,
                    kg_version=args.kg_version,
                    kg_version_id=kg_version_id,
                    org_id=org_id,
                    source_path=path,
                    systems=systems,
                    force=args.force,
                    with_bridge=not args.no_bridge,
                )
                reports.append(report)
                bridge_ids.extend(list(report["bridge_ids"]))
                relation_ids.extend(list(report["relation_ids"]))
            return verify_and_close(
                db=db,
                driver=driver,
                database=settings.neo4j_database,
                kg_version=args.kg_version,
                kg_version_id=kg_version_id,
                org_id=org_id,
                expected_bridge_ids=bridge_ids,
                expected_relation_ids=relation_ids,
                reports=reports,
            )
    except Exception as exc:  # noqa: BLE001 - CLI 统一兜底
        print(f"[FAIL] 制度文档入图失败: {exc}", file=sys.stderr)
        return 1
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
