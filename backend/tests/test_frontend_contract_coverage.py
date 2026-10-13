"""P7-D：前端 Mock 白名单 `CONTRACT_COVERED_PATTERNS` 与契约 `paths` **必须**互为零差。

为什么有这条（机制本身很土，害人地方在"静默"）：
`frontend/src/api/client.ts` 的 `shouldMock()` 是 `USE_MOCK=false` 时按白名单挑真请求的。
契约里写了、白名单里没写的那条端点 ⇒ **不报错、不打日志、直接返回本地 Mock**
——屏幕看着一切正常，数据其实是假的（`docs/dev-doc-status.md:100` 记的就是这个病）。
所以这里盯的本批新做的部分只有一句话：**差集必须是 0**。

盯四件事（其余闭环完成后自己会说清楚）：

1. **契约的每条 path 都被某个 pattern 命中**（漏登 ⇒ 上面那个静默回落立即复现）。
2. **白名单不许有孤儿 pattern**（契约没有却自称覆盖 ⇒ 白名单变成第二份说谎的契约）。
3. **解析下限**：读到 0 条 path / 0 个 pattern 直接 FAIL ——
   典型死法是"文件挪走了、正则没匹配上，测试依旧绿"（纪律 **R-9 恒绿即失效**）。
4. **反向用例**：差分本身要能被证伪。少一条 pattern / 多一条 path / 多一个孤儿，
   三种改动各自必须被报出来；报不出来这条护栏就是摆设。

**为什么落在 `backend/tests`**（2026-10-13 用户裁决）：
`frontend/package.json` 没有任何测试框架（只有 dev/build/start/lint/typecheck/gen:api），
给它装 vitest/jest = 新增依赖 = P7-D §3 Non-goals 的范围蔓延；
而"后端测试读 frontend 侧文件"在仓库里已有先例（`tests/test_delivery_images.py`
读 `deploy/` 与 `frontend/`）。代价是这条护栏在 CI 里归**后端 job** 跑，不归前端 job。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
CONTRACT = REPO_ROOT / "contracts" / "openapi.yaml"
CLIENT_TS = REPO_ROOT / "frontend" / "src" / "api" / "client.ts"

#: 白名单数组的起止标记。client.ts 若改结构，这里先红——属预期，同步过来即可。
_LIST_HEAD = "const CONTRACT_COVERED_PATTERNS: RegExp[] = ["
_LIST_TAIL = "];"

#: TS 正则字面量，形如 `  /^\/api\/v1\/health$/,
_LITERAL_RE = re.compile(r"/\^(?P<body>.+?)\$/(?P<flags>[gimsuy]*),?\s*$", re.MULTILINE)

#: 解析结果下限：低于它说明"读到了空壳"，按上面的第 3 条直接判失败
_MIN_PATHS = 20
_MIN_PATTERNS = 20


def _list_block(text: str) -> str:
    """截取白名单数组那一段（注释里同样满是 `/.../`，不截取会误抓）。"""
    assert _LIST_HEAD in text, f"client.ts 里找不到白名单声明头：{_LIST_HEAD}"
    head = text.index(_LIST_HEAD)
    assert _LIST_TAIL in text[head:], "白名单数组没有闭合 `];`"
    return text[head : head + text[head:].index(_LIST_TAIL)]


def contract_paths() -> list[str]:
    """契约里的所有 path（`contracts/openapi.yaml` 是 CI 已校验零漂移的生成物）。"""
    data = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    return sorted(data.get("paths") or {})


def pattern_sources() -> list[str]:
    """白名单里的 TS 正则字面量原文（转义未还原，用于报错时定位原文）。"""
    return [
        m.group("body")
        for m in _LITERAL_RE.finditer(
            _list_block(CLIENT_TS.read_text(encoding="utf-8"))
        )
    ]


def _compiled(source: str) -> re.Pattern[str]:
    """TS 正则字面量 → Python 正则：只需还原 `\\/` ⇒ `/`（`[^/]+` 两侧方言一致）。"""
    return re.compile("^" + source.replace("\\/", "/") + "$")


def diff(paths: list[str], patterns: list[str]) -> tuple[list[str], list[str]]:
    """返回（契约里有但白名单没覆盖的 path，白名单里对不上任何 path 的 pattern）。"""
    compiled = [(_compiled(src), src) for src in patterns]
    missing = [p for p in paths if not any(rx.match(p) for rx, _ in compiled)]
    orphan = [src for rx, src in compiled if not any(rx.match(p) for p in paths)]
    return missing, orphan


def test_contract_yields_paths() -> None:
    paths = contract_paths()
    assert len(paths) >= _MIN_PATHS, (
        f"只解析出 {len(paths)} 条契约 path（下限 {_MIN_PATHS}）⇒ 很可能是读取/解析坏了，"
        "而不是契约真的变短了"
    )


def test_client_yields_patterns() -> None:
    sources = pattern_sources()
    assert len(sources) >= _MIN_PATTERNS, (
        f"只解析出 {len(sources)} 条白名单 pattern（下限 {_MIN_PATTERNS}）⇒ 很可能是"
        "`CONTRACT_COVERED_PATTERNS` 被改名或改结构了；此时下面所有差分都会失真为 0"
    )


def test_every_contract_path_is_covered() -> None:
    missing, _ = diff(contract_paths(), pattern_sources())
    assert missing == [], (
        f"{len(missing)} 条契约端点不在白名单内 ⇒ USE_MOCK=false 时它们会**静默返回 Mock**：\n  "
        + "\n  ".join(missing)
        + "\n修法：往 `CONTRACT_COVERED_PATTERNS` 补正则（路径参数用 [^/]+），"
        "或在集成日志里登记**显式豁免**并写明 UI 表现（P7-D 裁决为豁免清单为空）。"
    )


def test_no_orphan_pattern() -> None:
    """白名单不许自称覆盖契约里不存在的东西。"""

    _, orphan = diff(contract_paths(), pattern_sources())
    assert orphan == [], (
        f"{len(orphan)} 条白名单 pattern 匹配不到任何契约 path：\n  "
        + "\n  ".join(orphan)
    )


def test_reverse_pruning_a_pattern_is_detected() -> None:
    """反向 1/3：抽掉一条 pattern ⇒ 对应端点必须立刻变成 missing。"""

    paths = contract_paths()
    sources = pattern_sources()
    pruned = [src for src in sources if "health" not in src]
    assert len(pruned) < len(sources), "构造失败：白名单里没有可抽的 /health pattern"

    missing, _ = diff(paths, pruned)
    assert "/api/v1/health" in missing, (
        "抽掉 /health 的 pattern 后竟然没被报出来 ⇒ 护栏恒绿"
    )


def test_reverse_extra_contract_path_is_detected() -> None:
    """反向 2/3：契约多一条 ⇒ 必须报 missing（防"将来新增端点忘了同步"这条路径失效）。"""

    ghost = "/api/v1/__coverage_probe__"
    missing, _ = diff([*contract_paths(), ghost], pattern_sources())
    assert ghost in missing, "凭空多出的契约 path 没被报出来 ⇒ 护栏恒绿"


def test_reverse_extra_pattern_is_detected() -> None:
    """反向 3/3：白名单多一条 ⇒ 必须报 orphan。"""

    ghost = r"\/api\/v1\/__ghost__"
    _, orphan = diff(contract_paths(), [*pattern_sources(), ghost])
    assert ghost in orphan, "凭空多出的白名单 pattern 没被报出来 ⇒ 护栏恒绿"


@pytest.mark.parametrize(
    ("path", "source"),
    [
        (
            "/api/v1/documents/{document_id}/graph",
            r"\/api\/v1\/documents\/[^/]+\/graph",
        ),
        (
            "/api/v1/documents/{document_id}/status",
            r"\/api\/v1\/documents\/[^/]+\/status",
        ),
        (
            "/api/v1/graph/versions/{version}/activate",
            r"\/api\/v1\/graph\/versions\/[^/]+\/activate",
        ),
    ],
)
def test_path_parameters_match_without_expansion(path: str, source: str) -> None:
    """路径参数 `{x}` 直接被 `[^/]+` 吃掉——不许为了通过而把契约 path 展开。"""

    assert _compiled(source).match(path), f"{source} 匹配不上契约里的 {path}"
