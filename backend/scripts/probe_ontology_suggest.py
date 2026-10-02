"""冷启动建议的**真机留证**脚本（M6 §3.1 验收 1 / PoC F1）。

**为什么单独成脚本而不是放在 pytest 里**：真 LLM 调用要花钱、不可复现、且依赖
``LLM_API_KEY``。CI 里跑的是 ``tests/test_ontology_suggest.py``（全 fake）；
**真机只在这里跑一次**，把输出贴回 ``changes/P0-m6-finalization/integration-log.md``。

用法（须先配好 ``.env`` 的 ``LLM_API_KEY`` / ``LLM_BASE_URL`` / ``LLM_MODEL``）：

```bash
cd backend && uv run python scripts/probe_ontology_suggest.py
```

⚠️ **每次执行 = 一次真实计费调用**。别把它塞进 CI，也别反复跑着玩
（v1.3.0 时期本仓曾因反复真机调用把余额打到 ¥8.37）。
"""

from __future__ import annotations

import json
import sys

from app.services.ontology import suggest_ontology_types

#: 与 M6 的演示业务域保持一致（``demo/attendance/``），便于和既有本体对照
DOMAIN_DESCRIPTION = "企业考勤与工时合规管理：员工、考勤记录、请假与加班、制度条款"


def main() -> int:
    try:
        suggestion = suggest_ontology_types(domain_description=DOMAIN_DESCRIPTION)
    except Exception as exc:  # noqa: BLE001 - 探针要把失败原因直接打出来
        print(f"[FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "domain_description": DOMAIN_DESCRIPTION,
                "prompt": f"{suggestion.prompt_name}_v{suggestion.prompt_version}",
                "entity_types": suggestion.entity_types,
                "relation_types": suggestion.relation_types,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
