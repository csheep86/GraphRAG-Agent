"""受控问题集评估器（Sprint 6 §5.3 验收第 1 条：引用覆盖率 100%、无拒答误伤）。

**只评估、不调 Prompt**（plan §4.2 纪律）：本脚本只跑真实链路并统计，
发现质量问题应登记到 `changes/Sprint6.*/integration-log.md`，**不**就地改 Prompt。

用法::

    uv run python scripts/eval_controlled_qset.py            # 默认 http://127.0.0.1:8002
    EVAL_BASE_URL=http://127.0.0.1:8000 uv run python scripts/eval_controlled_qset.py

统计口径：

- **引用覆盖率** = 非拒答回答中「`citations` 非空 **且** 每条 `chunk_id` 均为
  ``chunk-`` 前缀」的比例（目标 100%）；
- **拒答误伤** = 标注了 ``should_refuse=True`` 却未拒答，或反之（目标 0）。

退出码：覆盖率 < 100% 或存在误伤 → ``1``（可作为机械判据接入验收，不进 CI 门禁）。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

# Windows 控制台默认 GBK，中文结果会 UnicodeEncodeError —— 强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):  # pragma: no cover - 仅 Windows 生效
    sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = os.environ.get("EVAL_BASE_URL", "http://127.0.0.1:8002")
ORG_ID = "00000000-0000-4000-8000-000000000001"
ACTOR_ID = "00000000-0000-4000-8000-0000000000aa"

#: (问题, 是否预期拒答)。问题基于真机文档「2025 年度集团经营指标分析报告」，
#: 库外两问用于验证拒答出口不被误伤（F3 的反面：不该答的别答）。
QUESTIONS: list[tuple[str, bool]] = [
    ("集团整体净利润率是多少？", False),
    ("智能制造板块的营业收入是多少？", False),
    ("数字服务板块的净利润是多少？", False),
    ("哪个业务板块的同比增幅最快？", False),
    ("海外贸易板块收入同比变化如何？", False),
    ("智能制造与数字服务两大板块合计贡献集团多少营业收入占比？", False),
    ("集团五大板块的营业收入合计是多少？", False),
    ("新能源板块的净利润是多少？", False),
    ("本报告的数据截止日期是什么时候？", False),
    ("这份报告由哪个部门编制？", False),
    ("表中所有金额的单位是什么？", False),
    ("集团整体净利润率较上年度提升多少？", False),
    # ---- 库外问题：预期拒答（refused=true）----
    ("这份合同里甲方是哪家公司？", True),
    ("2026 年集团营业收入预计是多少？", True),
]


def ask(question: str) -> dict[str, Any]:
    payload = json.dumps({"question": question, "scope": "cross_doc"}).encode()
    request = urllib.request.Request(  # noqa: S310 - 固定本地地址
        f"{BASE_URL}/api/v1/agent/query",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Org-Id": ORG_ID,
            "X-Actor-Id": ACTOR_ID,
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    answered = 0
    cited = 0
    mismatches: list[str] = []
    failures: list[str] = []

    print(f"base_url={BASE_URL}  questions={len(QUESTIONS)}\n")

    for index, (question, should_refuse) in enumerate(QUESTIONS, start=1):
        try:
            response = ask(question)
        except urllib.error.HTTPError as exc:
            failures.append(f"Q{index} HTTP {exc.code}")
            print(f"[Q{index:02d}] HTTP {exc.code}  {question}")
            continue
        except Exception as exc:  # noqa: BLE001 - 评估器需跑完全集
            failures.append(f"Q{index} {exc!r}")
            print(f"[Q{index:02d}] ERROR {exc!r}  {question}")
            continue

        refused = bool(response.get("refused"))
        citations = response.get("citations") or []
        chunk_hits = [
            item
            for item in citations
            if str(item.get("chunk_id") or "").startswith("chunk-")
        ]
        kg_version = response.get("kg_version")

        if refused != should_refuse:
            mismatches.append(
                f"Q{index} 期望拒答={should_refuse} 实际={refused} :: {question}"
            )

        if not refused:
            answered += 1
            if citations and len(chunk_hits) == len(citations):
                cited += 1

        print(
            f"[Q{index:02d}] refused={refused!s:<5} conf={response.get('confidence')} "
            f"citations={len(citations)}(chunk={len(chunk_hits)}) "
            f"kg_version={kg_version} :: {question}"
        )
        print(f"       answer: {str(response.get('answer'))[:120]}")

    coverage = (cited / answered * 100) if answered else 0.0
    print("\n================ 汇总 ================")
    print(f"总题数          : {len(QUESTIONS)}")
    print(f"非拒答          : {answered}")
    print(f"引用命中(chunk-): {cited}")
    print(f"引用覆盖率      : {coverage:.1f}%  (目标 100%)")
    print(f"拒答口径不符    : {len(mismatches)}")
    for line in mismatches:
        print(f"  - {line}")
    print(f"请求失败        : {len(failures)}")
    for line in failures:
        print(f"  - {line}")

    ok = coverage >= 100.0 and not mismatches and not failures
    print("\n结论:", "PASS" if ok else "NOT PASS（仅登记，不在本脚本改 Prompt）")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
