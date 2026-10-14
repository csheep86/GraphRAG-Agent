"""P7-K · 评测可复现性闸门（D4 环境自检 / D5 空心 PASS）。

**这些用例的职责是证明"数字不能被偷换"**，而不是证明链路能跑：

- D5 的经典形状由 P6-T canary 实证：**6/6 全拒答，多跳照样报 ``0.8333 PASS``**，
  根因是 ``correct = judgements.get(...)` 与本次答案**不发生任何关系**；
- D4 的形状同源于此：换了池 / 换了代码 / 换了模型 ⇒ 答案悄悄变了，
  而判分表还是旧的 ⇒ 出出来的数字看着一样，实则已经不可复核。

故每条人都ाली用例都写成"能被打红"的形状：**改坏闸门 ⇒ 这里必红**，而不是绿着通过。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.evaluation import runner as runner_module
from app.evaluation.criteria import CriterionStatus, Provenance, Verdict
from app.evaluation.metrics import AnswerRecord
from app.evaluation.runner import (
    JudgementBasis,
    RunnerContext,
    _answer_gate,
    _reproducibility_gate,
    eval_multihop_accuracy,
)

GIT = "unit-test-git"
POOL = "e36322bb2d86865f"
MODEL = "deepseek-chat"


def _basis(**overrides: object) -> JudgementBasis:
    defaults: dict = {
        "dataset_version": "gold-multihop-v1",
        "source": "unit-sheets.json",
        "git_hash": GIT,
        "pool_fingerprint": POOL,
        "top_k": 32,
        "generation_model": MODEL,
        "answers": {1: "原始答案"},
    }
    defaults.update(overrides)
    return JudgementBasis(**defaults)  # type: ignore[arg-type]


def _answer(text: str = "原始答案", *, refused: bool = False) -> AnswerRecord:
    return AnswerRecord(
        refused=refused,
        citations=(),
        answer_text=text,
        correct=None,
        judged_by=None,
    )


def _write_sheets(
    tmp_path: Path, *, side: str = "graph", answer: str = "原始答案"
) -> Path:
    """落一份与真实 ``c1-sheets-*.json`` 同形状的答卷（键名对齐，便于 reader 复用）。"""
    spec = {
        "retriever": "dense_top_k",
        "pool": {
            "kg_version": "attendance-demo-v1",
            "org_id": "o",
            "fingerprint": POOL,
            "size": 1,
        },
        "top_k": 32,
        "generation_model": MODEL,
        "prompt_id": "kg_qa_v5",
    }
    sheet = {
        "_dataset_version": "controlled-qset-v4",
        "_git_hash": GIT,
        f"_{side}_spec": spec,
        side: [{"index": 1, "answer": answer, "refused": False}],
    }
    sheet_path = tmp_path / "sheets.json"
    sheet_path.write_text(json.dumps(sheet, ensure_ascii=False), encoding="utf-8")
    return sheet_path


class TestJudgementBasisLoading:
    """判分材料能不能被**定位并读出坐标**（错一步 ⇒ 后面全部退化为"未核"）。"""

    def test_load_reads_coordinates_from_source_sheets(self, tmp_path: Path) -> None:
        sheet_path = _write_sheets(tmp_path)
        table_path = tmp_path / "judgements.json"
        table_path.write_text(
            json.dumps(
                {"_source_sheets": sheet_path.name, "1": True}, ensure_ascii=False
            ),
            encoding="utf-8",
        )

        basis = JudgementBasis.load(table_path, side="graph")

        assert basis is not None
        assert basis.git_hash == GIT
        assert basis.pool_fingerprint == POOL
        assert basis.top_k == 32
        assert basis.generation_model == MODEL
        assert basis.answers == {1: "原始答案"}

    def test_baseline_side_reads_baseline_spec(self, tmp_path: Path) -> None:
        _write_sheets(tmp_path, side="baseline", answer="基线答案")
        table_path = tmp_path / "j.json"
        table_path.write_text(
            json.dumps({"_source_sheets": "sheets.json"}, ensure_ascii=False),
            encoding="utf-8",
        )

        basis = JudgementBasis.load(table_path, side="baseline")

        assert basis is not None, "基线侧必须有自己的 basis（A1 裁决 3：两侧各判各的）"
        assert basis.answers == {1: "基线答案"}

    def test_missing_source_sheets_returns_none(self, tmp_path: Path) -> None:
        table_path = tmp_path / "j.json"
        table_path.write_text(json.dumps({"1": True}), encoding="utf-8")

        #: 不能抛——没有 basis 时判据走「未核 + 如实登记」，而不是崩掉。
        assert JudgementBasis.load(table_path, side="graph") is None

    def test_dangling_sheets_reference_returns_none(self, tmp_path: Path) -> None:
        table_path = tmp_path / "j.json"
        table_path.write_text(
            json.dumps({"_source_sheets": "早已删除.json"}), encoding="utf-8"
        )

        assert JudgementBasis.load(table_path, side="graph") is None

    def test_absent_judgement_path_returns_none(self) -> None:
        assert JudgementBasis.load(None, side="graph") is None  # type: ignore[arg-type]


class TestEnvironmentMismatch:
    """门 ①：站错环境 ⇒ 不给数字。"""

    def test_matching_environment_passes(self) -> None:
        blocked, detail = _reproducibility_gate(
            _basis(),
            dataset_version="gold-multihop-v1",
            git_hash=GIT,
            pool_fingerprint=POOL,
            top_k=32,
            generation_model=MODEL,
        )
        assert blocked is None
        assert detail["reproducibility"] == "verified"

    def test_pool_drift_blocks(self) -> None:
        blocked, detail = _reproducibility_gate(
            _basis(),
            dataset_version="gold-multihop-v1",
            git_hash=GIT,
            pool_fingerprint="ffffffffffffffff",
            top_k=32,
            generation_model=MODEL,
        )
        assert blocked is not None
        assert "chunk 池不同" in blocked
        assert detail["reproducibility"] == "blocked"
        #: 报告里必须同时给期望与实际 —— 只说"不符"等于让人去猜差在哪。
        assert detail["expected"]["pool_fingerprint"] == POOL
        assert detail["actual"]["pool_fingerprint"] == "ffffffffffffffff"

    def test_git_and_model_and_topk_each_block(self) -> None:
        for kwargs, hint in (
            ({"git_hash": "另一个 commit"}, "代码版本不同"),
            ({"generation_model": "另一个模型"}, "生成模型不同"),
            ({"top_k": 8}, "注入证据条数不同"),
        ):
            coords = {
                "git_hash": GIT,
                "pool_fingerprint": POOL,
                "top_k": 32,
                "generation_model": MODEL,
            }
            coords.update(kwargs)
            blocked, _ = _reproducibility_gate(
                _basis(), dataset_version="gold-multihop-v1", **coords
            )
            assert blocked is not None and hint in blocked, f"{hint} 未被拦住"

    def test_unreadable_coordinates_are_not_turned_into_failure(self) -> None:
        """本次取不到池坐标 ⇒ **不许**读成不一致（无法反驳的假红会淹没真红）。"""
        blocked, detail = _reproducibility_gate(
            _basis(),
            dataset_version="gold-multihop-v1",
            git_hash=GIT,
            pool_fingerprint=None,
            top_k=None,
            generation_model=None,
        )
        assert blocked is None
        assert detail["reproducibility"] == "verified"

    def test_other_dataset_basis_is_reported_unchecked_not_blocked(self) -> None:
        blocked, detail = _reproducibility_gate(
            _basis(dataset_version="controlled-qset-v4"),
            dataset_version="gold-multihop-v1",
            git_hash=GIT,
        )
        assert blocked is None
        assert detail["reproducibility"] == "unchecked"

    def test_absent_basis_is_unchecked_and_says_so(self) -> None:
        blocked, detail = _reproducibility_gate(
            None, dataset_version="gold-multihop-v1", git_hash=GIT
        )
        assert blocked is None
        assert detail["reproducibility"] == "unchecked"
        #: 不许登记成"已核实"——那正是让 D5 复活的入口。
        assert "无法证明" in detail["note"]


class TestAnswerGate:
    """门 ②：答案不是人判过的那批 ⇒ 不许套判分。"""

    def test_identical_answers_pass(self) -> None:
        assert _answer_gate(_basis(), [1], [_answer()]) == []

    def test_drifted_answer_is_caught(self) -> None:
        stale = _answer_gate(_basis(), [1], [_answer("完全不同的新版答案")])

        assert len(stale) == 1
        assert stale[0]["index"] == 1
        assert "不一致" in stale[0]["reason"]

    def test_refusal_is_caught_even_without_basis(self) -> None:
        """拒答检测**不依赖**判分材料——这是最后一道、也最不该缺的一道。"""
        stale = _answer_gate(None, [1, 2], [_answer(refused=True), _answer()])

        assert [item["index"] for item in stale] == [1]

    def test_refusal_is_caught_with_basis_too(self) -> None:
        stale = _answer_gate(_basis(), [1], [_answer("原始答案", refused=True)])

        assert len(stale) == 1
        assert "拒答" in stale[0]["reason"]


class TestMultihopReproducibilityEndToEnd:
    """多跳判据（含 P6-T canary 复演）——这两条是 P7-K 里最贵的两条教训。"""

    @staticmethod
    def _patch_link(monkeypatch, answer: str, *, refused: bool) -> None:
        monkeypatch.setattr(
            runner_module,
            "ask_safe",
            lambda question, ctx: (
                {
                    "refused": refused,
                    "answer": answer,
                    "citations": [],
                    "kg_version": "attendance-demo-v1",
                },
                None,
            ),
        )

    def test_all_refused_no_longer_reports_pass(self, monkeypatch) -> None:
        """**[P6-T canary 复演]** 6/6 全拒答：旧实现报 ``0.8333 PASS``（吃 gold 老账）。

        加了这两道门之后，它必须变成 **UNKNOWN + value=None + INDETERMINATE**。
        """
        monkeypatch.setattr(
            runner_module,
            "load_multihop_set",
            lambda: [
                SimpleNamespace(index=i, question=f"q{i}", correct=True) for i in (1, 2)
            ],
        )
        monkeypatch.setattr(runner_module, "_live_env_coords", lambda ctx: None)
        self._patch_link(monkeypatch, "INSUFFICIENT_CONTEXT", refused=True)

        result = eval_multihop_accuracy(
            {"ctx": RunnerContext(mode="live", git_hash=GIT, judged_by="unit-test")}
        )

        assert result.value is None, "全拒答却出了数 —— 那就是 P6-T 那条 canary"
        assert result.status is CriterionStatus.UNKNOWN
        assert result.verdict is Verdict.INDETERMINATE
        assert result.blocked_by is not None and "判分已过期" in result.blocked_by
        assert result.detail is not None
        assert len(result.detail["stale_answers"]) == 2

    def test_reuses_judgement_when_environment_and_answers_match(
        self, monkeypatch
    ) -> None:
        """环境和答案都对得上 ⇒ **照旧出数**（闸门不该把正常的复用挡掉）。"""
        monkeypatch.setattr(
            runner_module,
            "load_multihop_set",
            lambda: [SimpleNamespace(index=1, question="q1", correct=None)],
        )
        monkeypatch.setattr(
            runner_module, "_live_env_coords", lambda ctx: (POOL, 32, MODEL)
        )
        self._patch_link(monkeypatch, "原始答案", refused=False)

        result = eval_multihop_accuracy(
            {
                "ctx": RunnerContext(
                    mode="live",
                    git_hash=GIT,
                    judgements={1: True},
                    judged_by="unit-test",
                    judgement_basis=_basis(),
                )
            }
        )

        assert result.value == 1.0
        assert result.threshold_source == "calibrated"
        #: provenance 必须带全坐标 ⇒ 脱离坐标无法引用这个数字（出口判据 5）。
        assert result.provenance.pool_fingerprint == POOL
        assert result.provenance.generation_model == MODEL
        assert result.provenance.top_k == 32

    def test_pool_drift_blocks_instead_of_reusing_scores(self, monkeypatch) -> None:
        monkeypatch.setattr(
            runner_module,
            "load_multihop_set",
            lambda: [SimpleNamespace(index=1, question="q1", correct=True)],
        )
        monkeypatch.setattr(
            runner_module,
            "_live_env_coords",
            lambda ctx: ("换了池的指纹", 32, MODEL),
        )
        self._patch_link(monkeypatch, "原始答案", refused=False)

        result = eval_multihop_accuracy(
            {
                "ctx": RunnerContext(
                    mode="live",
                    git_hash=GIT,
                    judgements={1: True},
                    judged_by="unit-test",
                    judgement_basis=_basis(),
                )
            }
        )

        assert result.value is None
        assert result.blocked_by is not None and "chunk 池不同" in result.blocked_by
        assert result.detail is not None
        assert result.detail["reproducibility"] == "blocked"


class TestProvenanceCoordinates:
    """坐标字段是**新增可选**的：旧调用方式不许因此崩掉。"""

    def test_defaults_stay_none(self) -> None:
        provenance = Provenance(
            dataset_version="controlled-qset-v4", mode="live", git_hash=GIT
        )
        assert provenance.pool_fingerprint is None
        assert provenance.generation_model is None
        assert provenance.top_k is None

    def test_coordinates_are_carried(self) -> None:
        provenance = Provenance(
            dataset_version="controlled-qset-v4",
            mode="live",
            git_hash=GIT,
            pool_fingerprint=POOL,
            generation_model=MODEL,
            top_k=32,
        )
        #: 坐标必须能随报告序列化——写不进报告等于没写。
        assert (
            json.loads(json.dumps(provenance.__dict__, ensure_ascii=False))[
                "pool_fingerprint"
            ]
            == POOL
        )
