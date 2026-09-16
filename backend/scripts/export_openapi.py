"""把 FastAPI 生成的 OpenAPI 结构导出到 `contracts/openapi.yaml`。

用法（工作目录 = `backend/`）：

    uv run python scripts/export_openapi.py          # 生成 / 覆盖契约
    uv run python scripts/export_openapi.py --check   # 仅校验是否与磁盘一致（CI 用）

确定性保证（否则阶段 3.3 的 `git diff --exit-code` 会永远失败）：
- `info.version` 取常量 `APP_VERSION`，不含时间戳 / 随机值；
- 顶层与嵌套映射统一 `sort_keys=True`；
- 路径由 `app/core/openapi.py` 预先排序；
- YAML 统一 UTF-8 + `\n` 换行，宽度固定。
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import yaml  # noqa: E402

from app.core.openapi import build_openapi  # noqa: E402
from app.main import app  # noqa: E402

REPO_ROOT = BACKEND_DIR.parent
TARGET = REPO_ROOT / "contracts" / "openapi.yaml"

#: 固定宽度，避免超长描述被 PyYAML 折行导致输出随内容长度漂移
_YAML_WIDTH = 4096

HEADER = (
    "# 本文件由 backend/scripts/export_openapi.py 自动生成，请勿手工编辑。\n"
    "# 真源：backend/app/schemas/*.py（Pydantic 模型）。\n"
    "# 重新生成：cd backend && uv run python scripts/export_openapi.py\n"
)


def render() -> str:
    schema = build_openapi(app)
    body = yaml.safe_dump(
        schema,
        allow_unicode=True,
        sort_keys=True,
        default_flow_style=False,
        width=_YAML_WIDTH,
    )
    return HEADER + body


def main(argv: list[str]) -> int:
    check_only = "--check" in argv[1:]
    rendered = render()

    if check_only:
        if not TARGET.is_file():
            print(f"[FAIL] 契约文件不存在: {TARGET}", file=sys.stderr)
            return 1
        current = TARGET.read_text(encoding="utf-8")
        if current != rendered:
            print(
                f"[FAIL] {TARGET} 与后端模型不一致，请重新执行 "
                "`uv run python scripts/export_openapi.py` 并提交生成物。",
                file=sys.stderr,
            )
            return 1
        print(f"[OK] {TARGET} 与后端模型一致")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"[OK] 已生成 {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
