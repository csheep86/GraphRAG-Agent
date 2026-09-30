"""把已在库文档的 ``document_date`` 用**同一套解析代码**补上（¥0，不烧 LLM）。

为什么要有它
------------
``documents.document_date`` 的写入点是抽取任务（``tasks/registry.py`` 在 MinerU
解析后认一次）。但**历史文档是在解析能力完善之前进的库**——认不出的那一刻被
如实存成了 NULL，此后既没有重解析、也没有别的写入路径 ⇒ 演示库 17 份文档
``document_date`` **全为 NULL**（2026-09-30 实测），直接后果有两个：

1. 答案模板里的「依据截至 X 日的披露文件」恒为空（``kg_qa_v5`` 起改为整句不出现，
   泄漏没了，但**能力也看不见了**）；
2. 抽取时 Prompt 的 ``{{document_date}}`` 恒为 ``unknown`` ⇒ 关系 ``valid_from``
   少一个确定性兜底源（ADR-0005 R4）。

本脚本**只补不改变任何判定逻辑**：对每个还没有日期的文档读它**已存**的
``full.md``（parse 阶段的产物），交给 :func:`app.services.parsing.document_date.
resolve_document_date` ——与上传链路用的**同一个函数、同一套锚点**。
认不出就留 None：**不会**因为它叫"回填"就去猜一个。

用法（工作目录 = ``backend/``）::

    uv run python scripts/backfill_document_date.py            # 预演：只打印会写什么
    uv run python scripts/backfill_document_date.py --apply    # 真写

写之前要先看清楚会写什么：这就是为什么默认 ``--dry-run``。

已知边界（2026-09-30 Sprint 10.4 的决定：**本脚本当前不对演示库执行 --apply**）
--------------------------------------------------------------------------
预演结果是「16/17 份都能认出日期」，看起来只要按一下 ``--apply`` 就能把
R23 的「有值 0 / 共 17」抹掉。但那会把演示变成**另一种失真**：

- 演示图的考勤事实发生在 **2026-10**，而日期最晚的那批文档是 4 份制度文档
  （生效日 2026-01-01）⇒ ``_resolve_context_date`` 取「租户内最新 document_date」
  ⇒ 答案会说「依据截至 **2026-01-01** 的披露文件」，而它引用的其实是 10 月的事实；
- 也就是说：**数字变好看了，陈述变错了**。宁可让 as-of 整句不出现
  （``kg_qa_v5`` 的行为），也不能让它指向一个张冠李戴的日期。

真要启用需先动两件事之一：① 让 as-of 只取**本次真的引用到的文档**的日期；
② 演示语料的业务事实与文档日期处在同一个时间量级。两者都属下一批议题。
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.models import Document  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.services.parsing.document_date import resolve_document_date  # noqa: E402
from app.storage import build_parse_artifact_key, get_storage  # noqa: E402


def _read_full_md(*, org_id: object, doc_id: object) -> str | None:
    """读该文档的 ``full.md``；**没有就算了**（没解析过的文档无从谈日期）。"""
    try:
        raw = get_storage().get(
            build_parse_artifact_key(org_id=org_id, doc_id=doc_id, filename="full.md"),
            org_id=org_id,
        )
    except Exception:  # noqa: BLE001 - 产物缺失是合法的，不是故障
        return None
    return raw.decode("utf-8", errors="replace")


def backfill(*, apply: bool, today: date) -> int:
    written = 0
    scanned = 0
    recognized = 0

    with SessionLocal() as db:
        documents = (
            db.query(Document)
            .filter(Document.document_date.is_(None))
            .order_by(Document.created_at)
            .all()
        )
        print(f"待处理文档（document_date IS NULL）：{len(documents)} 份")

        for doc in documents:
            scanned += 1
            markdown = _read_full_md(org_id=doc.org_id, doc_id=doc.id)
            if markdown is None:
                print(f"  [skip ] {doc.id} 无 full.md 产物（未解析 / 产物缺失）")
                continue
            resolved, source = resolve_document_date(text=markdown, today=today)
            if resolved is None:
                print(f"  [none ] {doc.id} 认不出日期（source={source}）⇒ 保持 NULL")
                continue
            recognized += 1
            print(f"  [found] {doc.id} -> {resolved.isoformat()}（source={source}）")
            if apply:
                doc.document_date = resolved
                written += 1

        if apply and written:
            db.commit()

    state = f"已写入 {written} 份" if apply else "预演未写库"
    print(f"===== 扫描 {scanned} 份 / 认出 {recognized} 份 / {state} =====")
    if not apply and recognized:
        print("加 --apply 才会真写库。")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="回填 documents.document_date")
    parser.add_argument("--apply", action="store_true", help="真实写库（缺省只预演）")
    parser.add_argument(
        "--today",
        default=None,
        help="解析用的“今天”（YYYY-MM-DD，仅决定年份上限；缺省取系统当天）",
    )
    args = parser.parse_args(argv)

    init_db()
    today = date.fromisoformat(args.today) if args.today else date.today()
    backfill(apply=bool(args.apply), today=today)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
