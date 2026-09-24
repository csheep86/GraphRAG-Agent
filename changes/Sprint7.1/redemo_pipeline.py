"""Sprint 7.1 批次 A 第一步：重抽演示数据 + ADR-0002 重建 active 版本（**真机驱动**）。

背景（``changes/Sprint7.0/integration-log.md`` §5 第 3 条）：库内演示数据是**正则占位器**
产物（`complex_table.pdf` 一份，实体 6 个）。批次 A 的任何疑点结论都必须建立在
**真实 LLM 抽取**之上，因此第一步先把演示数据集换成三家招商系公司的真实材料：

1. 招商蛇口 2024 公司债（第一期）募集说明书；
2. 招商公路 2024 科创债（第一期）募集说明书；
3. 招商轮船 2025 年年度报告（控股股东章节含交叉，见 Sprint 7.0 §7.2）。

驱动方式（沿用 Sprint 6.1 §4 第 3 条的口径，**不臆造新入口**）：

- 上传走**真实 HTTP API**（``POST /api/v1/documents/upload``），由在线服务跑
  ``document.parse``（MinerU 云解析）；
- 在线链路不自串联（既有缺口），``document.extract`` / ``kg.build`` 由本脚本
  直接调 ``app.tasks.registry`` 里登记的执行体，payload 与 TaskSpec 契约一致；
- ``trace_id`` 复用 ``documents.trace_id``（H4：四段同一个 trace_id）；
- 三份文档写入**同一个 kg_version**（跨公司两跳算法的前提；``kg_version_strategy``
  文档口径是 ``per_org``，执行体默认却是「一文档一版本」，故显式传 ``kg_version_id``）。

用法（工作目录 = ``backend/``，服务需先起在 ``--base-url``）：

```powershell
uv run python ../changes/Sprint7.1/redemo_pipeline.py upload --pdf ../docs/annualreport/xxx.pdf
uv run python ../changes/Sprint7.1/redemo_pipeline.py wait-parse --doc <doc_id>
uv run python ../changes/Sprint7.1/redemo_pipeline.py status
uv run python ../changes/Sprint7.1/redemo_pipeline.py prepare --docs <id1>,<id2>,<id3>
uv run python ../changes/Sprint7.1/redemo_pipeline.py extract --doc <id>
uv run python ../changes/Sprint7.1/redemo_pipeline.py build --doc <id> --version <uuid>
uv run python ../changes/Sprint7.1/redemo_pipeline.py finalize --version <uuid>
uv run python ../changes/Sprint7.1/redemo_pipeline.py probe --doc <id>
```
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_BASE_URL = "http://127.0.0.1:8123"

#: 开发态认证兜底头（``ALLOW_DEV_ORG_HEADER=true``；值与 ``Settings.DEFAULT_ORG_ID``
#: / ``DEFAULT_ACTOR_ID`` 一致，保证与既有演示数据同租户）
DEV_HEADERS: dict[str, str] = {
    "X-Org-Id": "00000000-0000-4000-8000-000000000001",
    "X-Actor-Id": "00000000-0000-4000-8000-0000000000aa",
}

#: D6 关注点（Sprint 7.0 §7.2 真机核对过的交叉事实）
PROBE_KEYWORDS: tuple[str, ...] = (
    "缪建民",  # 招商局集团法定代表人（三家共享 → 共享法人疑点）
    "招商局集团有限公司",  # 控股股东
    "招商局轮船",  # 轮船年报的控股股东
    "建国路",  # 集团注册地址（仅蛇口募集说明书披露）
    "1986-10-14",  # 集团成立日期，同名消歧依据
    "东方广场",  # ⚠ 会计师事务所地址（伪交叉陷阱）
)


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream and getattr(stream, "encoding", "").lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


# --------------------------------------------------------------------------- #
# 上传 / 解析（真实 HTTP）
# --------------------------------------------------------------------------- #
def cmd_upload(args: argparse.Namespace) -> int:
    import httpx

    pdf: Path = args.pdf
    if not pdf.is_file():
        print(f"[FAIL] 文件不存在: {pdf}", file=sys.stderr)
        return 1
    url = f"{args.base_url}/api/v1/documents/upload"
    content = pdf.read_bytes()
    print(f"POST {url}  file={pdf.name}  bytes={len(content)}")
    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            url,
            files={"file": (pdf.name, content, "application/pdf")},
            headers=DEV_HEADERS,
        )
    print(f"HTTP {response.status_code}")
    print(response.text[:800])
    return 0 if response.status_code == 202 else 1


def cmd_wait_parse(args: argparse.Namespace) -> int:
    import httpx

    url = f"{args.base_url}/api/v1/documents/{args.doc}/status"
    deadline = time.time() + args.timeout
    last = ""
    with httpx.Client(timeout=30.0) as client:
        while time.time() < deadline:
            response = client.get(url)
            if response.status_code != 200:
                print(f"HTTP {response.status_code}: {response.text[:300]}")
                return 1
            payload = response.json()
            status = payload.get("status")
            if status != last:
                print(f"  [{time.strftime('%H:%M:%S')}] status={status} "
                      f"error={payload.get('error')}")
                last = status
            if status in ("completed", "failed"):
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return 0 if status == "completed" else 1
            time.sleep(args.interval)
    print(f"[FAIL] 等待解析超时（{args.timeout}s）", file=sys.stderr)
    return 1


def cmd_delete(args: argparse.Namespace) -> int:
    """删除一条 documents 记录及其存储对象（用于清掉超限失败的上传，保持语料干净）。

    **不**改写任何业务结论，只是把「上传即失败」的占位记录移除；失败原因已登记在
    ``integration-log.md``（MinerU 200 页上限）。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.models import Document
    from app.storage import build_storage_key, get_storage

    doc_id = uuid.UUID(args.doc)
    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    storage = get_storage()
    with Session(engine) as db:
        document = db.get(Document, doc_id)
        if document is None:
            print(f"[FAIL] documents 不存在: {doc_id}", file=sys.stderr)
            return 1
        status = document.status
        key = build_storage_key(
            org_id=document.org_id,
            doc_id=doc_id,
            filename_hash=document.filename_hash,
        )
        removed_file = True
        try:
            storage.delete(key)
        except Exception as exc:  # noqa: BLE001 - 文件缺失不影响 DB 清理
            removed_file = False
            print(f"  [warn] 源文件删除失败（忽略）: {exc}")
        db.delete(document)
        db.commit()
    print(f"deleted doc={doc_id} (status was {status}) storage_removed={removed_file}")
    return 0


# --------------------------------------------------------------------------- #
# 状态
# --------------------------------------------------------------------------- #
def cmd_status(args: argparse.Namespace) -> int:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.db.models import Document, KgVersion

    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    with Session(engine) as db:
        print("--- documents ---")
        for d in db.execute(select(Document).order_by(Document.created_at)).scalars():
            print(
                f"  id={d.id} status={d.status} parse_retry={d.retry_count} "
                f"extract={d.extract_status}(retry={d.extract_retry_count}) "
                f"kg_build={d.kg_build_status}(retry={d.kg_build_retry_count}) "
                f"kg_version_id={d.kg_version_id} size={d.size_bytes}"
            )
            if d.status == "failed":
                print(
                    f"      error_code={d.error_code} "
                    f"error_detail={str(d.error_detail)[:300]}"
                )
        print("--- kg_versions ---")
        for v in db.execute(select(KgVersion).order_by(KgVersion.created_at)).scalars():
            print(
                f"  id={v.id} version={v.version} status={v.status} "
                f"entity={v.entity_count} relation={v.relation_count} "
                f"source_doc_ids={v.source_doc_ids}"
            )
    return 0


# --------------------------------------------------------------------------- #
# 共享 kg_version
# --------------------------------------------------------------------------- #
def cmd_prepare(args: argparse.Namespace) -> int:
    """创建一个 pending 版本，``source_doc_ids`` 一次登记全部演示文档。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.models import Document
    from app.services.kg.versioning import KgVersioningService

    doc_ids = [uuid.UUID(item.strip()) for item in args.docs.split(",") if item.strip()]
    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    with Session(engine) as db:
        for doc_id in doc_ids:
            if db.get(Document, doc_id) is None:
                print(f"[FAIL] documents 不存在: {doc_id}", file=sys.stderr)
                return 1
        version_name = args.version or f"v-s71a-{uuid.uuid4().hex[:8]}"
        record = KgVersioningService(db).create_pending(
            org_id=uuid.UUID(args.org_id) if args.org_id else _default_org_id(db, doc_ids),
            version=version_name,
            source_doc_ids=doc_ids,
            trace_id=uuid.uuid4(),
        )
    print(f"kg_version_id={record.id}")
    print(f"version={record.version}")
    print(f"source_doc_ids={[str(i) for i in record.source_doc_ids]}")
    return 0


def _default_org_id(db, doc_ids: list[uuid.UUID]):  # noqa: ANN001 - SQLAlchemy Session
    from app.db.models import Document

    document = db.get(Document, doc_ids[0])
    return document.org_id


# --------------------------------------------------------------------------- #
# 抽取（真实 LLM）
# --------------------------------------------------------------------------- #
def _install_token_sink() -> dict[str, int]:
    """挂 loguru sink 累计 ``langextract_llm_call`` 的 token 与耗时（真实扣费口径）。"""
    from loguru import logger

    totals = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "elapsed_ms": 0}

    def _sink(message) -> None:  # noqa: ANN001 - loguru Message
        record = message.record
        if record["message"] != "langextract_llm_call":
            return
        extra = record["extra"]
        totals["calls"] += 1
        totals["prompt_tokens"] += int(extra.get("prompt_tokens") or 0)
        totals["completion_tokens"] += int(extra.get("completion_tokens") or 0)
        totals["elapsed_ms"] += int(extra.get("elapsed_ms") or 0)

    logger.remove()
    logger.add(_sink, level="INFO", format="")
    logger.add(sys.stderr, level="WARNING", format="{level.icon} {message}")
    return totals


def _apply_extraction_overrides(args: argparse.Namespace) -> None:
    """把抽取档位显式写进环境变量（**必须在导入 app.* 之前**，get_settings 有缓存）。

    为什么不让 .env 决定：本脚本常与「改 .env 切 v2」的动作并行跑，若档位隐式取自
    .env，同一次批量重抽里前后几份文档可能用上不同 prompt 版本 → **同库混档**，
    批次 A 的疑点就成伪数据。显式声明 = 可复跑的证据。
    """
    import os

    if getattr(args, "chunk_chars", None):
        os.environ["EXTRACTION_MAX_CHARS_PER_CHUNK"] = str(args.chunk_chars)
    if getattr(args, "prompt_version", None):
        os.environ["EXTRACTION_PROMPT_VERSION"] = args.prompt_version
    if getattr(args, "engine", None):
        os.environ["EXTRACTION_ENGINE"] = args.engine


def cmd_extract(args: argparse.Namespace) -> int:
    _apply_extraction_overrides(args)
    # 先加载 app.services 包：``app.tasks.__init__`` 会经 manager → registry 回头
    # 引 services，而 services.__init__ 又要拿 manager 的 TaskManager —— 入口顺序
    # 反了会撞循环导入（真机踩到，见 integration-log §4）。服务进程走 app.main 的
    # 导入顺序，天然先 services 后 tasks，本脚本必须复刻同一顺序。
    import app.services  # noqa: F401

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.models import Document
    from app.tasks.registry import document_extract_executor
    from app.tasks.types import TaskSpec

    doc_id = uuid.UUID(args.doc)
    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    with Session(engine) as db:
        document = db.get(Document, doc_id)
        if document is None:
            print(f"[FAIL] documents 不存在: {doc_id}", file=sys.stderr)
            return 1
        trace_id = str(document.trace_id)
        # 复位阶段状态（Sprint 6.1 §4 第 3 条：在线链路无可重跑入口）
        if args.reset and document.extract_status == "completed":
            document.extract_status = None
            db.commit()
            print("  [reset] extract_status: completed -> None")
        if document.extract_status == "completed" and not args.reset:
            print("  [skip] extract_status 已 completed（需重跑请加 --reset）")
            return 0

    totals = _install_token_sink()
    started = time.perf_counter()
    spec = TaskSpec(
        task_type="document.extract",
        payload={"document_id": str(doc_id), "trace_id": trace_id},
        trace_id=trace_id,
    )
    asyncio.run(document_extract_executor(spec))
    elapsed = time.perf_counter() - started

    with Session(engine) as db:
        document = db.get(Document, doc_id)
        status = document.extract_status if document else "unknown"
        error_detail = document.error_detail if document else None
    print(f"extract_status={status} elapsed={elapsed:.1f}s error={error_detail}")
    if totals["calls"]:
        cost = (
            totals["prompt_tokens"] * 2 + totals["completion_tokens"] * 8
        ) / 1_000_000
        print(
            f"llm_calls={totals['calls']} prompt_tokens={totals['prompt_tokens']} "
            f"completion_tokens={totals['completion_tokens']} "
            f"llm_time={totals['elapsed_ms'] / 1000:.1f}s estimated_cost=¥{cost:.4f}"
        )
    return 0 if status == "completed" else 1


# --------------------------------------------------------------------------- #
# 建图（共享版本）
# --------------------------------------------------------------------------- #
def cmd_extract_all(args: argparse.Namespace) -> int:
    """串行抽取多份文档（真实 LLM），统一累计 token 与成本。"""
    doc_ids = [item.strip() for item in args.docs.split(",") if item.strip()]
    _apply_extraction_overrides(args)
    print(
        f"engine={os.environ.get('EXTRACTION_ENGINE')} "
        f"prompt_version={os.environ.get('EXTRACTION_PROMPT_VERSION')} "
        f"chunk_chars={os.environ.get('EXTRACTION_MAX_CHARS_PER_CHUNK')}"
    )
    totals = _install_token_sink()
    started = time.perf_counter()
    failed: list[str] = []
    for doc_id in doc_ids:
        print(f"\n===== extract {doc_id} =====")
        sub = argparse.Namespace(
            doc=doc_id,
            reset=args.reset,
            chunk_chars=args.chunk_chars,
            prompt_version=args.prompt_version,
            engine=args.engine,
        )
        rc = cmd_extract(sub)
        if rc != 0:
            failed.append(doc_id)
    elapsed = time.perf_counter() - started
    print(f"\n===== extract-all done elapsed={elapsed:.1f}s failed={failed} =====")
    if totals["calls"]:
        cost = (
            totals["prompt_tokens"] * 2 + totals["completion_tokens"] * 8
        ) / 1_000_000
        print(
            f"llm_calls={totals['calls']} prompt_tokens={totals['prompt_tokens']} "
            f"completion_tokens={totals['completion_tokens']} "
            f"llm_time={totals['elapsed_ms'] / 1000:.1f}s estimated_cost=¥{cost:.4f}"
        )
    return 1 if failed else 0


def cmd_build_all(args: argparse.Namespace) -> int:
    doc_ids = [item.strip() for item in args.docs.split(",") if item.strip()]
    failed: list[str] = []
    started = time.perf_counter()
    for doc_id in doc_ids:
        print(f"\n===== build {doc_id} =====")
        rc = cmd_build(
            argparse.Namespace(doc=doc_id, version=args.version, reset=args.reset)
        )
        if rc != 0:
            failed.append(doc_id)
    print(f"\n===== build-all done elapsed={time.perf_counter() - started:.1f}s "
          f"failed={failed} =====")
    return 1 if failed else 0


def cmd_build(args: argparse.Namespace) -> int:
    import app.services  # noqa: F401 - 同 cmd_extract：先 services 后 tasks 的导入顺序

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.models import Document, KgVersion
    from app.tasks.registry import kg_build_executor
    from app.tasks.types import TaskSpec

    doc_id = uuid.UUID(args.doc)
    version_id = uuid.UUID(args.version)
    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    with Session(engine) as db:
        document = db.get(Document, doc_id)
        if document is None:
            print(f"[FAIL] documents 不存在: {doc_id}", file=sys.stderr)
            return 1
        version = db.get(KgVersion, version_id)
        if version is None:
            print(f"[FAIL] kg_versions 不存在: {version_id}", file=sys.stderr)
            return 1
        trace_id = str(document.trace_id)
        print(f"doc={doc_id} version={version.version} ({version_id}) trace_id={trace_id}")
        if args.reset and document.kg_build_status == "completed":
            document.kg_build_status = None
            db.commit()
            print("  [reset] kg_build_status: completed -> None")

    started = time.perf_counter()
    asyncio.run(
        kg_build_executor(
            TaskSpec(
                task_type="kg.build",
                payload={
                    "document_id": str(doc_id),
                    "kg_version_id": str(version_id),
                    "trace_id": trace_id,
                },
                trace_id=trace_id,
            )
        )
    )
    elapsed = time.perf_counter() - started

    with Session(engine) as db:
        document = db.get(Document, doc_id)
        print(
            f"kg_build_status={document.kg_build_status} status={document.status} "
            f"elapsed={elapsed:.1f}s error={document.error_detail}"
        )
        return 0 if document.kg_build_status == "completed" else 1


def cmd_finalize(args: argparse.Namespace) -> int:
    """把共享版本的统计值回填为**三份文档的累加值**（逐次 build 会互相覆盖）。"""
    import json

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.models import Document, KgVersion
    from app.services.kg.versioning import KgVersioningService
    from app.storage import build_extract_artifact_key, get_storage

    version_id = uuid.UUID(args.version)
    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    storage = get_storage()
    with Session(engine) as db:
        version = db.get(KgVersion, version_id)
        if version is None:
            print(f"[FAIL] kg_versions 不存在: {version_id}", file=sys.stderr)
            return 1
        doc_ids = [uuid.UUID(v) for v in (version.source_doc_ids or [])]
        entities_total = 0
        relations_total = 0
        chunks_total = 0
        for doc_id in doc_ids:
            document = db.get(Document, doc_id)
            if document is None:
                continue
            base = build_extract_artifact_key(
                org_id=document.org_id, doc_id=doc_id, filename="entities.json"
            )
            prefix = base.rsplit("/", 1)[0]
            e_key = f"{prefix}/entities.json"
            r_key = f"{prefix}/relations.json"
            c_key = f"{prefix}/chunks.json"
            entities = json.loads(storage.get(e_key, org_id=document.org_id).decode())
            relations = json.loads(storage.get(r_key, org_id=document.org_id).decode())
            chunks = json.loads(storage.get(c_key, org_id=document.org_id).decode())
            print(
                f"  doc={doc_id} entities={len(entities)} "
                f"relations={len(relations)} chunks={len(chunks)}"
            )
            entities_total += len(entities)
            relations_total += len(relations)
            chunks_total += len(chunks)

        record = KgVersioningService(db).mark_ready(
            version_id, entity_count=entities_total, relation_count=relations_total
        )
    print(
        f"version={record.version} status={record.status} "
        f"entity_count={record.entity_count} relation_count={record.relation_count} "
        f"chunk_total={chunks_total}"
    )
    return 0


# --------------------------------------------------------------------------- #
# 产物抽查（零成本，不调 LLM）
# --------------------------------------------------------------------------- #
def cmd_probe(args: argparse.Namespace) -> int:
    import json

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.db.models import Document
    from app.storage import build_extract_artifact_key, get_storage

    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    storage = get_storage()
    with Session(engine) as db:
        docs = (
            [db.get(Document, uuid.UUID(args.doc))]
            if args.doc
            else list(db.execute(select(Document)).scalars().all())
        )
        for document in docs:
            if document is None:
                continue
            key = build_extract_artifact_key(
                org_id=document.org_id, doc_id=document.id, filename="entities.json"
            )
            try:
                raw = storage.get(key, org_id=document.org_id)
            except Exception as exc:  # noqa: BLE001
                print(f"doc={document.id} 产物缺失: {exc}")
                continue
            entities = json.loads(raw.decode("utf-8"))
            types = Counter(e.get("entity_type") for e in entities)
            print(f"--- doc={document.id} entities={len(entities)} ---")
            print(f"  type_distribution={dict(types.most_common())}")
            haystack = "\n".join(
                f"{e.get('canonical_name')} {e.get('mention')}" for e in entities
            )
            for keyword in PROBE_KEYWORDS:
                hit_count = haystack.count(keyword)
                print(f"  probe {keyword:<12} hits={hit_count}")
            # M4 主体层（§2.2）要的两类：抽到了才谈得上两跳算法
            for wanted in ("LEGAL_PERSON", "ADDRESS"):
                sample = [
                    e.get("canonical_name")
                    for e in entities
                    if e.get("entity_type") == wanted
                ]
                print(f"  {wanted}: count={len(sample)} sample={sample[:6]}")

            # 关系侧：§2.2 的两条边靠 LEGAL_REP / REGISTERED_AT，光有实体不够
            rel_key = build_extract_artifact_key(
                org_id=document.org_id, doc_id=document.id, filename="relations.json"
            )
            raw_rel = storage.get(rel_key, org_id=document.org_id)
            relations = json.loads(raw_rel.decode("utf-8"))
            rel_types = Counter(r.get("relation_type") for r in relations)
            print(f"  relations={len(relations)} type_distribution={dict(rel_types.most_common())}")
            name_by_id = {e.get("id"): e.get("canonical_name") for e in entities}
            for wanted in ("LEGAL_REP", "REGISTERED_AT"):
                pairs = [
                    (
                        name_by_id.get(r.get("source_entity_id")),
                        name_by_id.get(r.get("target_entity_id")),
                    )
                    for r in relations
                    if r.get("relation_type") == wanted
                ]
                print(f"  {wanted}: count={len(pairs)} sample={pairs[:6]}")
            if args.top:
                print(f"  top{args.top} by confidence:")
                for e in sorted(
                    entities, key=lambda item: float(item.get("confidence") or 0),
                    reverse=True,
                )[: args.top]:
                    print(
                        f"    {float(e.get('confidence') or 0):.2f} "
                        f"{str(e.get('type')):<16} {str(e.get('canonical_name'))[:44]}"
                    )
    return 0


# --------------------------------------------------------------------------- #
# §2.3 / §2.4：M4 疑点检出（risk.detect 执行体，真机 Neo4j）
# --------------------------------------------------------------------------- #
def cmd_detect(args: argparse.Namespace) -> int:
    """跑 ``risk.detect`` 执行体并打印疑点清单（真机取证用）。"""
    import app.services  # noqa: F401 - 先 services 后 tasks 的导入顺序

    import json
    import time

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.models import Document
    from app.storage import build_kg_artifact_key, get_storage
    from app.tasks.registry import risk_detect_executor
    from app.tasks.types import TaskSpec

    doc_id = uuid.UUID(args.doc)
    engine = create_engine(f"sqlite:///{BACKEND_DIR / 'dev.db'}")
    with Session(engine) as db:
        document = db.get(Document, doc_id)
        if document is None:
            print(f"[FAIL] documents 不存在: {doc_id}", file=sys.stderr)
            return 1
        trace_id = str(document.trace_id)
        org_id = document.org_id
        print(f"doc={doc_id} kg_version_id={document.kg_version_id}")

    started = time.perf_counter()
    asyncio.run(
        risk_detect_executor(
            TaskSpec(
                task_type="risk.detect",
                payload={"document_id": str(doc_id), "trace_id": trace_id},
                trace_id=trace_id,
            )
        )
    )
    print(f"elapsed={time.perf_counter() - started:.1f}s")

    key = build_kg_artifact_key(
        org_id=org_id, doc_id=doc_id, filename="suspicions.json"
    )
    raw = get_storage().get(key, org_id=org_id)
    payload = json.loads(raw.decode("utf-8"))
    print(f"--- suspicions total={payload['total']} kg_version={payload['kg_version']} ---")
    for index, item in enumerate(payload["suspicions"], start=1):
        print(
            f"  [{index}] type={item['type']} severity={item['severity']} "
            f"names={item['entity_names']}"
        )
        for evidence in item["evidence"]:
            snippet = str(evidence.get("text", "")).replace("\n", " ")[:80]
            print(
                f"      node={evidence['node_id']} chunk={evidence['chunk_id']} "
                f"doc={evidence['doc_id']} page={evidence['page']} "
                f"[{evidence['char_start']},{evidence['char_end']}) {snippet}"
            )
    return 0


# --------------------------------------------------------------------------- #
# §2.2 真机 Neo4j 计数核验
# --------------------------------------------------------------------------- #
_NEO4J_COUNTS_CYPHER = (
    ("Subject 节点", "MATCH (n:Subject {kg_version: $v}) RETURN count(n) AS c"),
    ("Address 节点", "MATCH (n:Address {kg_version: $v}) RETURN count(n) AS c"),
    ("LegalPerson 节点", "MATCH (n:LegalPerson {kg_version: $v}) RETURN count(n) AS c"),
    (
        "LEGAL_REP 边",
        "MATCH ()-[r:LEGAL_REP {kg_version: $v}]->() RETURN count(r) AS c",
    ),
    (
        "REGISTERED_AT 边",
        "MATCH ()-[r:REGISTERED_AT {kg_version: $v}]->() RETURN count(r) AS c",
    ),
    ("Entity 节点（M2 对照）", "MATCH (n:Entity {kg_version: $v}) RETURN count(n) AS c"),
    ("Chunk 节点（证据层）", "MATCH (n:Chunk {kg_version: $v}) RETURN count(n) AS c"),
)

#: 类型核验（S6 真机踩过「位置字段落库成字符串」的坑，这里一并看属性值类型）
_NEO4J_TYPE_CYPHER = """
MATCH (s:Subject {kg_version: $v})
RETURN s.id AS id, valueType(s.name) AS name_type,
       valueType(s.source_entity_ids) AS source_ids_type,
       size(coalesce(s.source_entity_ids, [])) AS source_ids_len
ORDER BY s.id
LIMIT 5
"""


def cmd_neo4j_counts(args: argparse.Namespace) -> int:
    """打印指定 kg_version 的 M4 主体层计数与属性值类型（真机核验）。"""
    from app.services.graphs import GraphService

    service = GraphService.instance()
    version = args.version
    print(f"--- Neo4j counts kg_version={version} ---")
    with service._session() as session:  # noqa: SLF001 - 脚本直连，走既有会话封装
        for label, cypher in _NEO4J_COUNTS_CYPHER:
            row = session.run(cypher, v=version).single()
            print(f"  {label:<24} = {row['c'] if row else 'N/A'}")
        print("  --- 属性值类型抽样（Subject）---")
        for row in session.run(_NEO4J_TYPE_CYPHER, v=version):
            print(
                f"    id={str(row['id'])[:24]} name_type={row['name_type']} "
                f"source_ids_type={row['source_ids_type']} len={row['source_ids_len']}"
            )
    return 0


# --------------------------------------------------------------------------- #
# M4 主体层清理（修 id 口径后的重建前置动作；默认 dry-run）
# --------------------------------------------------------------------------- #
_WIPE_M4_CYPHER = """
MATCH (n {kg_version: $v})
WHERE n:Subject OR n:Address OR n:LegalPerson
RETURN labels(n) AS labels, count(n) AS c
"""

_WIPE_M4_DELETE = """
MATCH (n {kg_version: $v})
WHERE n:Subject OR n:Address OR n:LegalPerson
DETACH DELETE n
"""


def cmd_wipe_m4(args: argparse.Namespace) -> int:
    """删除指定版本的 M4 主体层节点（含边），供**重建**用。

    **默认 dry-run**（必须先看到要删多少再加 ``--apply``）：修正「边 id 口径」后，
    旧 id 的并行边不会自动消失，必须清掉再重建，否则两跳仍会重复出条。
    **不**动 Entity / Chunk / Document / KgVersionMirror（那些按 id MERGE，重建幂等）。
    """
    from app.services.graphs import GraphService

    service = GraphService.instance()
    with service._session() as session:  # noqa: SLF001
        rows = list(session.run(_WIPE_M4_CYPHER, v=args.version))
        total = 0
        for row in rows:
            print(f"  {'|'.join(row['labels']):<24} = {row['c']}")
            total += int(row["c"])
        if not args.apply:
            print(f"  [dry-run] 合计 {total} 个节点待删；加 --apply 才真删")
            return 0
        session.run(_WIPE_M4_DELETE, v=args.version).consume()
    print(f"  [apply] 已删除 {total} 个 M4 节点（含其边）")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sprint 7.1 演示数据重抽驱动")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("upload")
    p.add_argument("--pdf", type=Path, required=True)
    p.set_defaults(func=cmd_upload)

    p = sub.add_parser("wait-parse")
    p.add_argument("--doc", required=True)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--interval", type=int, default=10)
    p.set_defaults(func=cmd_wait_parse)

    p = sub.add_parser("status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("delete")
    p.add_argument("--doc", required=True)
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("prepare")
    p.add_argument("--docs", required=True, help="逗号分隔的 document_id")
    p.add_argument("--version", default=None)
    p.add_argument("--org-id", default=None)
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("extract")
    p.add_argument("--doc", required=True)
    p.add_argument("--reset", action="store_true")
    p.add_argument("--chunk-chars", type=int, default=1200,
                   help="每 chunk 字符上限（Sprint 7.0 真机验证档位 = 1200）")
    p.add_argument("--prompt-version", default="kg_extraction_v1")
    p.add_argument("--engine", default="llm")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("extract-all")
    p.add_argument("--docs", required=True, help="逗号分隔的 document_id")
    p.add_argument("--reset", action="store_true")
    p.add_argument("--chunk-chars", type=int, default=1200)
    p.add_argument("--prompt-version", default="kg_extraction_v1")
    p.add_argument("--engine", default="llm")
    p.set_defaults(func=cmd_extract_all)

    p = sub.add_parser("build")
    p.add_argument("--doc", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--reset", action="store_true")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("build-all")
    p.add_argument("--docs", required=True, help="逗号分隔的 document_id")
    p.add_argument("--version", required=True)
    p.add_argument("--reset", action="store_true")
    p.set_defaults(func=cmd_build_all)

    p = sub.add_parser("wipe-m4", help="清理 M4 主体层（默认 dry-run，加 --apply 执行）")
    p.add_argument("--version", required=True, help="kg_version 字符串")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_wipe_m4)

    p = sub.add_parser("finalize")
    p.add_argument("--version", required=True)
    p.set_defaults(func=cmd_finalize)

    p = sub.add_parser("probe")
    p.add_argument("--doc", default=None)
    p.add_argument("--top", type=int, default=0)
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("detect", help="§2.3/§2.4：跑 risk.detect 执行体（M4 疑点检出）")
    p.add_argument("--doc", required=True)
    p.set_defaults(func=cmd_detect)

    p = sub.add_parser("neo4j-counts", help="真机 Neo4j 计数核验（§2.2 验收）")
    p.add_argument("--version", required=True)
    p.set_defaults(func=cmd_neo4j_counts)
    return parser


def main() -> int:
    _utf8_console()
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
