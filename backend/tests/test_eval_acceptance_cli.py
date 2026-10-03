"""`scripts/eval_acceptance.py` 的 CLI 契约（**E2.5**：不做没人会跑的孤儿脚本）。

钉住四件事：

1. ``--offline`` **不依赖 LLM / 网络 / Neo4j** 就能跑通（这是 CI 能接进去的前提）；
2. offline **不产出判据数字**——依赖真机的判据必须是 ``null`` + ``blocked_by``（不是 0）；
3. **幂等**：同一输入两次运行 ⇒ 报告（除 ``generated_at``）逐字一致；
4. ``--calibrate`` **绝不改 config / .env**（RK-E7：禁止脚本自己把阈值调松）。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND_DIR / "scripts" / "eval_acceptance.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 固定参数，无 shell
        [sys.executable, str(SCRIPT), *args],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_offline_runs_without_network_and_exits_zero(tmp_path: Path) -> None:
    """offline 是**默认**模式且必须零依赖跑通（断网 / 无 LLM / 无 Neo4j）。"""
    out = tmp_path / "offline.json"
    proc = _run("--offline", "--out", str(out))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out.exists()

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["schema"] == "eval-acceptance/v1"
    assert report["mode"] == "offline"
    assert report["git_hash"]
    assert report["dataset_versions"]["controlled-qset-v3"] == "v3-2026-09-30"


def test_offline_yields_no_criterion_numbers(tmp_path: Path) -> None:
    """**核心守卫**：offline 不产出判据数字——断网跑出来的"召回 0.8"必然是假的。"""
    out = tmp_path / "offline.json"
    assert _run("--offline", "--out", str(out)).returncode == 0
    report = json.loads(out.read_text(encoding="utf-8"))

    for item in report["criteria"]:
        assert item["value"] is None, f"{item['criterion']} 在 offline 下不该有数字"
        assert item["blocked_by"], f"{item['criterion']} 无值却没说为什么"
        assert item["status"] in {"blocked", "unknown"}


def test_blocked_criteria_name_their_blocker(tmp_path: Path) -> None:
    """依赖 M6 的判据必须点名 blocked_by=P5-M6；基线缺失的点名 A1。"""
    out = tmp_path / "offline.json"
    assert _run("--offline", "--out", str(out)).returncode == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    blocked = {item["criterion"]: item["blocked_by"] for item in report["criteria"]}

    assert "P5-M6" in blocked["c3_a_single_doc_cost"]
    assert "P5-M6" in blocked["c3_b_incremental_cost_ratio"]
    assert "baseline" in blocked["c1_graph_gain"]
    #: C2-a / C2-b 的 id 空间**已核对**（2026-10-03）⇒ 不再是"数据未核对"，
    #: 而是 offline 读不到 Neo4j ⇒ 点名 live。
    assert "live" in blocked["c2_a_hidden_relation_recall"]
    assert "live" in blocked["c2_b_false_positive_rate"]


def test_self_test_block_is_flagged_synthetic(tmp_path: Path) -> None:
    """口径演练值必须与判据**分区**且标 synthetic（否则迟早被读成测量结果）。"""
    out = tmp_path / "offline.json"
    assert _run("--offline", "--out", str(out)).returncode == 0
    report = json.loads(out.read_text(encoding="utf-8"))

    block = report["self_test"]
    assert block["synthetic"] is True
    # 演练值确实算得出来（口径可跑通），但它们不在 criteria 里
    assert block["metrics"]["findings_recall"] == 0.5
    assert block["metrics"]["findings_false_positive_rate"] == 0.5
    assert block["metrics"]["citation_coverage"] == 1.0


def test_report_is_idempotent(tmp_path: Path) -> None:
    """**幂等契约**：同一输入两次运行 ⇒ 报告（除 generated_at）逐字一致。"""
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    assert _run("--offline", "--out", str(first)).returncode == 0
    assert _run("--offline", "--out", str(second)).returncode == 0
    assert _run("--compare", str(first), str(second)).returncode == 0


def test_upgrade_todo_is_printed(tmp_path: Path) -> None:
    """报告必须回答「升为 MEASURED 还缺什么」（不许留成黑箱）。"""
    out = tmp_path / "offline.json"
    assert _run("--offline", "--out", str(out)).returncode == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["upgrade_todo"]
    assert any("P5-M6" in item for item in report["upgrade_todo"])


def test_live_link_unavailable_is_unknown_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**真跑学到的教训（2026-10-03）**：链路不可用（后端恒 501）时，
    脚本必须**跑完并给出结论**，而不是抛栈崩溃；结论是 ``UNKNOWN`` + 原因，
    **不是** 0（0 会被读成"覆盖率为 0"）。
    """
    import urllib.error

    import app.evaluation.runner as runner
    from app.evaluation.criteria import CriterionStatus

    def boom(question: str, *, ctx: object, scope: str = "cross_doc") -> dict:
        raise urllib.error.HTTPError("http://x", 501, "Not Implemented", {}, None)

    monkeypatch.setattr(runner, "ask", boom)
    ctx = runner.RunnerContext(mode="live", git_hash="unit-test")
    results = runner.run(ctx, criteria=(runner.C_CITATION,))

    assert len(results) == 1
    assert results[0].status is CriterionStatus.UNKNOWN
    assert results[0].value is None
    assert "链路不可用" in (results[0].blocked_by or "")


def test_calibrate_never_touches_config(tmp_path: Path) -> None:
    """**RK-E7**：--calibrate 只输出建议值，绝不改 config / .env。"""
    config = BACKEND_DIR / "app" / "core" / "config.py"
    env_example = BACKEND_DIR / ".env.example"
    before_config = config.read_text(encoding="utf-8")
    before_env = env_example.read_text(encoding="utf-8") if env_example.exists() else ""

    records = tmp_path / "costs.json"
    records.write_text(
        json.dumps(
            [
                {"doc_id": "d1", "token_usage_total": 20000, "sequence": 0},
                {"doc_id": "d1", "token_usage_total": 25000, "sequence": 1},  # 重算
                {"doc_id": "d2", "token_usage_total": 30000, "sequence": 0},
                {"doc_id": "d3", "token_usage_total": 22000, "outcome": "failed"},
            ]
        ),
        encoding="utf-8",
    )
    proc = _run("--calibrate", "--cost-records", str(records))
    assert proc.returncode == 0
    # last_success 口径：d1 取 25000、d2 取 30000、d3 失败不计
    assert "P50 / P90" in proc.stdout
    assert "不写" in proc.stdout

    assert config.read_text(encoding="utf-8") == before_config
    if env_example.exists():
        assert env_example.read_text(encoding="utf-8") == before_env


def test_calibrate_without_records_says_it_cannot(tmp_path: Path) -> None:
    """无真实成本记录 ⇒ 明说"无法校准"，**不**拿默认值冒充校准结果。"""
    proc = _run("--calibrate")
    assert proc.returncode == 0
    assert "无法校准" in proc.stdout
    assert "provisional" in proc.stdout
