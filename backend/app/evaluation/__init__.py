"""M6 出口判据（C1–C3）的**评测体系**（DR-D10 / TBD-7 的承载模块）。

分层（**刻意不放在一处**，避免"指标"与"取值"互相污染）：

- :mod:`app.evaluation.metrics` —— **纯函数**：只算数，不读配置、不碰网络 / DB / LLM；
- :mod:`app.evaluation.criteria` —— **四态状态机**：把"能不能自证"变成机器可判的状态；
- :mod:`app.evaluation.dataset` —— 版本化受控问题集 / gold 标注的加载与校验（E2）；
- :mod:`app.evaluation.runner` —— offline / live 双模式执行（E2）；
- :mod:`app.evaluation.report` —— JSON 报告与 diff（E2）。

**为什么纯函数要独立**：指标口径是本仓**唯一**要被两处消费的东西——
单测要钉它的边界（空集 / 零除 / 并列），执行器要拿它跑真数据。
若它顺手去读配置或打 HTTP，边界就只能在真机上测，CI 上必然变成"看着绿、其实没跑"。

**红线**：本模块**不改写** `specs/m6-ontology-incremental.md` §3.4 的任何口径原文；
发现的口径缺陷登记在 `changes/P0-m6-eval/proposal.md` §6（A1–A7），
由用户在下一批或本节裁决后再改 spec。
"""

from __future__ import annotations

__all__ = ["criteria", "metrics"]
