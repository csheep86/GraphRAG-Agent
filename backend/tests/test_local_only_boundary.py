"""`local_only` 边界的登记一致性——防止"看着绿，其实没跑"悄悄复发。

背景（本轮第三、四例同类病）：`bridge_web_demo/output.json` 与
`mineru_mvp/output/complex_table/` 都**未入库**（分别命中 `bridge_web_demo/.gitignore:19`
与根 `.gitignore:40` 的 `**/output/*`），而 `pytest -q` 又不打印 skip 原因。
⇒ 那两条"真实产物回归"用例**本地跑得到、CI 上永远跑不到**，且日志上无痕
（上一次 CI：`573 passed, 5 skipped`；同版本本地：`575 passed, 3 skipped`）。

本文件把这个边界变成机械事实三条：

1. **登记集合 = `-m local_only` 实际收集到的集合**（去重后的用例级）。
   新增这类用例必须同步登记到本文件——否则它会静默地加入"永不执行"的一伙。
2. **每个登记项依赖的产物确实未入库**（`git ls-files` 无输出）。
   一旦有人把产物提交了，这里立刻红：那时它已在 CI 上跑得到，**应当摘掉**
   `local_only` 标记，而不是继续挂着"CI 不覆盖"的牌子假装没看见。
3. 反向由 `pytest -q -rs` 与 CI 的"本地独占用例"步骤保证：skip 原因必须写在日志里。

不做的：**不**在本文件断言"本地产物存在与否"——那会把测试变成依赖本机状态，
反而制造新的"本地绿 / CI 红"。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

#: 登记的「CI 上跑不到」用例（去掉参数后缀后的 <文件>::<用例>）
REGISTERED_NODES: frozenset[str] = frozenset(
    {
        "tests/test_import_to_neo4j.py::test_real_bridge_output_is_fully_resolvable",
        "tests/test_page_index.py::test_real_mineru_artifacts_alignment",
        "tests/test_temporal_track_s.py::test_as_of_query_against_real_neo4j",
    }
)

#: 每个登记项**依赖但未入库**的产物 ⇒ CI 上必然拿不到
UNTRACKED_ARTIFACTS: tuple[str, ...] = (
    "bridge_web_demo/output.json",
    "mineru_mvp/output/complex_table",
)


def _collect_local_only() -> set[str]:
    proc = subprocess.run(  # noqa: S603 - 固定参数，不接外部输入
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "local_only"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        pytest.fail(
            f"无法收集 local_only 用例：pytest 退出码 {proc.returncode}\n{proc.stderr}"
        )
    nodes: set[str] = set()
    for line in (proc.stdout or "").splitlines():
        match = re.match(r"^(tests/[^:]+\.py)::([A-Za-z_0-9]+)", line.strip())
        if match:
            nodes.add(f"{match.group(1)}::{match.group(2)}")
    return nodes


def _tracked_files(specs: tuple[str, ...]) -> list[str]:
    proc = subprocess.run(  # noqa: S603 - 固定参数，不接外部输入
        ["git", "ls-files", "--", *specs],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        pytest.fail(f"无法判定产物是否入库：git ls-files 退出码 {proc.returncode}")
    return [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]


def test_registered_matches_collected() -> None:
    """漏登记 ⇒ 红：新增这类用例必须**显式**承认自己不在 CI 上跑。"""
    collected = _collect_local_only()
    assert collected, "没有收集到任何 local_only 用例——标记可能已被整体摘掉"

    extra = sorted(collected - REGISTERED_NODES)
    missing = sorted(REGISTERED_NODES - collected)
    assert not extra, (
        f"以下用例标了 local_only 但未登记到本文件（会在 CI 上静默不执行）：{extra}"
        f"——请加入 test_local_only_boundary.py 的 REGISTERED_NODES"
    )
    assert not missing, (
        f"登记了但 pytest 收不到（用例改名或标记被摘？）：{missing}"
        f"——登记集合与实现必须一致，见 tests/test_check_seams.py 的同型判据"
    )


def test_local_only_reasons_are_untracked_artifacts() -> None:
    """产物一旦入库，这里必须红：那时它就该在 CI 上真跑，而不是继续挂着免死牌。"""
    tracked = _tracked_files(UNTRACKED_ARTIFACTS)
    assert tracked == [], (
        f"下列产物已进版本库，却在 local_only 名下继续躲开 CI：{tracked}"
        f"——请摘掉对应的 local_only 标记并同步本文件的登记集合"
    )
