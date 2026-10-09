"""抽取侧（**接缝 3**）采样漂移探针（P6-R · T5）。

**为什么单独成脚本而不是塞进 pytest**：它要真调 LLM（经 ``build_chat_model()``），
花钱、不可复现、依赖 ``LLM_API_KEY``；CI 里跑的是全 fake 的
``tests/test_extraction_llm_engine.py``。**真机只在这里跑**，输出贴回
``changes/P6-R/integration-log.md``。

**它回答的问题**：P6-R 按裁决 **O1** 在接缝 3 全局钉 ``temperature=0``。
接缝 3 同时喂给**抽取 / 本体建议 / 问答**三条路径 ⇒ 钉温度会连带改**入图产物**。
本探针用**固定文本**在**图外**连跑 N 次（不写库、不污染演示图），
给出「同一份输入，抽取产物是否逐位一致」的机械读数，供改动前 / 改动后对比。

用法（须先配好 ``.env`` 的 ``LLM_API_KEY`` / ``LLM_BASE_URL`` / ``LLM_MODEL``）：

```bash
cd backend
uv run python scripts/probe_p6r_extraction_drift.py --runs 2 --tag before
uv run python scripts/probe_p6r_extraction_drift.py --runs 2 --tag after
```

⚠️ **每次运行 = ``--runs`` 次真实计费调用**。文本已刻意压到单 chunk ⇒ 每次 1 次调用。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

#: 与 ``scripts/`` 下其他脚本同款处理：以脚本方式跑时 ``backend/`` 不在 ``sys.path`` 上
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Windows 控制台默认 GBK，中文结果会 UnicodeEncodeError —— 强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

from app.services.extraction.langextract import (  # noqa: E402
    ExtractionResult,
    LangextractClient,
)

#: 固定输入：与演示业务域（``demo/attendance/``）同源的制度文本。
#: **改动前 / 改动后必须用同一份文本**，否则对比无意义。
FIXED_TEXT = (
    "第七条（2026 版修订）自动补卡不占用每月 3 次的补卡次数，员工无需手工提交申请。"
    "外勤缺卡由系统在次日 09:00 自动生成补卡记录。"
    "第八条 标准工时制岗位的核心在岗时段为 09:30 至 18:30，弹性工时制岗位为 10:00 至 19:00。"
    "月度累计迟到超过 3 次，按《员工考勤管理办法》第十条扣发当月绩效的 10%。"
)

#: 固定 document_id：实体 / 关系 id 由内容派生（``_stabilize_ids``），
#: 但 document_id 参与派生 ⇒ 必须钉死，否则两次运行的 id 不同源。
FIXED_DOC_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")

#: trace_id 不参与产物派生，但仍钉死以便日志可对账。
FIXED_TRACE_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")


def _fingerprint(result: ExtractionResult) -> dict[str, object]:
    """把一次抽取产物压成**可逐位比较**的指纹。

    用 ``canonical_name`` / 关系端点名 而非内部 id 排序 —— id 由内容派生，
    同名实体在不同运行里本应得到同一个 id；用名字比较更能直接回答
    「gold 命中是否漂移」。
    """
    entities = sorted(
        f"{e.canonical_name}|{e.entity_type}|{e.mention}" for e in result.entities
    )
    name_by_id = {e.id: e.canonical_name for e in result.entities}
    relations = sorted(
        f"{name_by_id.get(r.source_entity_id, r.source_entity_id)}"
        f"|{r.relation_type}|"
        f"{name_by_id.get(r.target_entity_id, r.target_entity_id)}"
        for r in result.relations
    )
    payload = json.dumps(
        {"entities": entities, "relations": relations},
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "entity_count": len(entities),
        "relation_count": len(relations),
        "failed_chunks": len(result.failed_chunks),
        "entities": entities,
        "relations": relations,
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--runs",
        type=int,
        default=2,
        help="连跑次数（默认 2：跑一次只看出「这次是多少」，区分不出抖动）",
    )
    parser.add_argument(
        "--tag",
        default="run",
        help="本轮标记（如 before / after），只进输出便于贴文档",
    )
    parser.add_argument(
        "--text-file",
        help="覆盖内置固定文本（**改动前后必须传同一个文件**，否则对比无意义）",
    )
    args = parser.parse_args()

    if args.runs < 2:
        print("[WARN] --runs < 2：单次运行无法区分「漂移」与「抖动」", file=sys.stderr)

    text = FIXED_TEXT
    if args.text_file:
        with open(args.text_file, encoding="utf-8") as handle:
            text = handle.read()

    client = LangextractClient.from_settings()
    fingerprints: list[dict[str, object]] = []
    for index in range(args.runs):
        try:
            result = client.extract_entities_relations(
                document_id=FIXED_DOC_ID,
                full_md_text=text,
                trace_id=FIXED_TRACE_ID,
            )
        except Exception as exc:  # noqa: BLE001 - 探针要把失败原因直接打出来
            print(
                f"[FAILED] run#{index + 1} {type(exc).__name__}: {exc}", file=sys.stderr
            )
            return 1
        fingerprints.append(_fingerprint(result))

    hashes = {str(item["sha256"]) for item in fingerprints}
    print(
        json.dumps(
            {
                "tag": args.tag,
                "runs": args.runs,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                "identical_across_runs": len(hashes) == 1,
                "distinct_results": len(hashes),
                "fingerprints": fingerprints,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
