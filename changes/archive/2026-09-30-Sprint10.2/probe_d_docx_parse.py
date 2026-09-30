"""S10 批次 D 真机：docx 上传 → MinerU 解析 → 产物落盘（真实云调用，会消耗额度）。

任务卡上写的是「`_do_parse` 真实实现（现状 `return None`）+ 依赖引入」——**这条已过期**：
Sprint 9.5 批次 B2 就把真实实现落好了（``app/tasks/registry.py::_do_parse``，
PDF / docx 走同一条 MinerU 链路，靠 `_PARSE_MIME_TO_SUFFIX` 映射后缀）。
所以本批次真正缺的是**真机证据**：docx 到底能不能解析出东西。

链路（跳过 HTTP，直接走服务层，避免把"端口没起"当成"解析不通"）：

1. 落一条 ``documents`` 行（SQLite 开发库）；
2. 源文件 put 进存储层（``{org}/{doc}/{filename_hash}``）；
3. 调 ``_do_parse``（真 MinerU 云）；
4. 读回 ``full.md`` / ``content_list.json``，验非空 + JSON 合法。

样本用 ``demo/attendance/corpus/*.docx``（项目自带的真实制度文档，不造假文件）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

# 先按应用正常顺序完成初始化：``app.tasks.manager`` 与 ``app.services.documents``
# 互相 import，直接先取 ``app.tasks.registry`` 会撞上"部分初始化"的循环导入。
import app.main  # noqa: E402,F401

from app.core.config import get_settings  # noqa: E402
from app.db.models import Document  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.storage import (  # noqa: E402
    build_parse_artifact_key,
    build_storage_key,
    get_storage,
)
from app.tasks.registry import _do_parse  # noqa: E402

CORPUS = Path(__file__).resolve().parents[2] / "demo" / "attendance" / "corpus"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _as_text(raw: object) -> str:
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


async def _run(sample: Path) -> None:
    settings = get_settings()
    org_id = settings.default_org_id
    doc_id = uuid4()
    content = sample.read_bytes()
    filename_hash = hashlib.sha256(sample.name.encode("utf-8")).hexdigest()

    db = SessionLocal()
    db.add(
        Document(
            id=doc_id,
            filename_hash=filename_hash,
            mime_type=DOCX_MIME,
            size_bytes=len(content),
            status="pending",
            uploaded_by=org_id,
            org_id=org_id,
            trace_id=uuid4(),  # ``documents.trace_id`` NOT NULL 且是 Uuid（贯穿调用链）
        )
    )
    db.commit()
    db.close()

    storage = get_storage()
    storage.put(
        build_storage_key(org_id=org_id, doc_id=doc_id, filename_hash=filename_hash),
        content,
    )

    print(f"\n=== {sample.name}（{len(content)} B）doc_id={doc_id}")
    try:
        await _do_parse(
            document_id=doc_id,
            payload={"trace_id": "probe-s10-d", "document_id": str(doc_id)},
        )
    except Exception as exc:  # noqa: BLE001 - 探针要看见全部故障
        print(f"    [FAIL] {type(exc).__name__}: {exc}")
        return

    md_key = build_parse_artifact_key(
        org_id=org_id, doc_id=doc_id, filename="full.md"
    )
    cl_key = build_parse_artifact_key(
        org_id=org_id, doc_id=doc_id, filename="content_list.json"
    )
    try:
        markdown = _as_text(storage.get(md_key, org_id=org_id))
        content_list = json.loads(_as_text(storage.get(cl_key, org_id=org_id)))
    except Exception as exc:  # noqa: BLE001
        print(f"    [FAIL] 产物读回失败：{type(exc).__name__}: {exc}")
        return

    print(f"    [OK] full.md {len(markdown)} 字符 / content_list {len(content_list)} 项")
    if isinstance(content_list, list) and content_list:
        kinds: dict[str, int] = {}
        for item in content_list:
            # content_list 的元素未必是 dict（实测第一项是 list）⇒ 不假设结构
            kind = (
                str(item.get("type", "?")) if isinstance(item, dict) else type(item).__name__
            )
            kinds[kind] = kinds.get(kind, 0) + 1
        print(f"         content_list 类型分布: {kinds}")
    print("         markdown 前 240 字:")
    print("         " + markdown[:240].replace("\n", "\n         "))


async def main() -> None:
    samples = sorted(CORPUS.glob("*.docx"))
    if not samples:
        print(f"没有 docx 样本：{CORPUS}")
        return
    print(f"样本 {len(samples)} 个；parser_provider={get_settings().parser_provider}")
    for sample in samples[:2]:  # 先跑 2 个（省额度；够证"docx 能解析"）
        await _run(sample)


if __name__ == "__main__":
    asyncio.run(main())
