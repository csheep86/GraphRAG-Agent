"""**评测基线的本地 embedding 服务**（S-b，P6-F）——薄、离线、可被替代。

**它是干什么的**
给 C1（``c1_graph_gain``）的 **dense top-k 基线**提供向量化。暴露 **OpenAI 兼容**的
``/v1/embeddings`` ⇒ 评测侧现有的 ``app.evaluation.baseline.OpenAICompatibleEmbedder``
**一行都不用改**；换成云端网关或换成本地服务，对被测链路而言没有差别。

**为什么自己起一个（而不是直接用云端 key）**
C1 判的是「图谱相对 RAG 增益 ≥ 10%」这种**小差异**。云端嵌入模型的版本可能静默升级，
今天测出的结论半年后就不再可比；本地服务把**模型权重与版本钉死**在本地
⇒ 历史数字可回溯比对，且不依赖外网。

**为什么不用 torch**
走 ONNX Runtime + CPU（``fastembed``）⇒ 依赖体积从约 2–3GB 降到约 200MB 量级，
也不把 torch 塞进本项目的依赖图（新增依赖只进 ``dev`` group）。

**它不是什么**

- **不是**产品链路的一部分：产品问答 ``/agent/query`` **从不**调用它，
  它只服务 ``scripts/eval_acceptance.py`` 的基线侧；
- **不是**唯一的 embeddings 实现：把 ``EVAL_EMBEDDING_BASE_URL`` 指向任何
  OpenAI 兼容网关，本服务可以整个下线。

用法::

    # 起服务（首次 embed 时会拉 / 加载权重）
    uv run python scripts/local_embedding_server.py --port 8009

    # 冒烟
    curl -X POST http://127.0.0.1:8009/v1/embeddings \
         -H "Content-Type: application/json" \
         -d '{"model":"BAAI/bge-small-zh-v1.5","input":["你好","世界"]}'

**首次拉权重**（只需一次，之后走本地缓存）::

    set HF_ENDPOINT=https://hf-mirror.com      # 直连 huggingface.co 会超时时的镜像
    set HF_HUB_DISABLE_XET=1                   # HF 的 xet 存储后端在未登录时会 401
    uv run python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-zh-v1.5').embed(['预热'])"

::: note
  以上两个环境变量是**本机网络环境的适配**，写在这里是为了可复现——
  换一台能直连 HF 的机器就不需要它们。权重一旦进本地 HF 缓存，
  服务用 ``HF_HUB_OFFLINE=1`` 也能起来（**推荐**：模型已钉死，不该每次联网）。
:::

对应评测侧配置（本机 ``.env``，不入版本库）::

    EVAL_EMBEDDING_BASE_URL=http://127.0.0.1:8009/v1
    EVAL_EMBEDDING_API_KEY=local-dev      # 本地服务不校验，但**必须非空**（fail-fast）
    EVAL_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5

⚠️ **安全边界**：本服务**不校验 API Key**，默认只监听本机。
请**只在开发 / 交付演练环境起**，不要绑 0.0.0.0，不要放进生产 compose。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.disable(logging.CRITICAL)

import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field  # noqa: E402

#: **模型钉死处**：改动即换基线 ⇒ 历史 C1 数字不再可比，须同步登记。
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"

_OBJECT_LIST = "list"
_OBJECT_EMBEDDING = "embedding"


class EmbeddingRequest(BaseModel):
    """只接**用得到的**字段；未识别字段**宽容忽略**（见 docstring 说明）。"""

    model_config = ConfigDict(extra="allow")

    model: str = ""
    input: list[str] | str = Field(default="")


def _normalize_input(payload: EmbeddingRequest) -> list[str]:
    raw = payload.input
    return [raw] if isinstance(raw, str) else [t for t in raw if isinstance(t, str)]


#: 默认权重目录 = **HF 缓存**（``~/.cache/huggingface/hub``）。
#: 结构恰与 fastembed 期望的一致（``models--<repo>--<name>/...``）⇒ 命中即不联网。
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"


def create_app(
    model_name: str = DEFAULT_MODEL, cache_dir: Path = DEFAULT_CACHE_DIR
) -> FastAPI:
    """构造 FastAPI 应用（**延迟加载模型**：首次 embed 才拉权重）。

    :param cache_dir: 权重搜寻目录。默认复用 HF 缓存 ⇒ 本机已拉的 ONNX 直接命中，
        不需要联网；配合 ``HF_HUB_OFFLINE=1`` 起服务即可完全离线。
    """
    from fastembed import TextEmbedding  # noqa: PLC0415 - 重依赖，按需导入

    app = FastAPI(title="local-embedding-server", version="1.0")
    #: ``lazy_load=True``：**构造时不拉权重** ⇒ 服务先起来（``/health`` 可用），
    #: 首次 ``embed`` 才加载。否则模型下载一失败，连 health 都没有，
    #: 排障时无法区分"服务没起"与"模型没下来"。
    embedder = TextEmbedding(
        model_name=model_name, cache_dir=str(cache_dir), lazy_load=True
    )
    state: dict[str, Any] = {"dimension": None}

    @app.get("/health")
    def health() -> dict[str, Any]:
        """登录后可用于脚本核对：模型 id 与**维度**必须可见。

        维度为什么重要：同一份 chunk 池换模型就换向量空间，若维度不进报告，
        换了模型也没人知道 ⇒ 两次 C1 的值会被天真地放在一起比。
        """
        return {
            "status": "ok",
            "model": model_name,
            "dimension": state["dimension"],
            "note": "本地 dev embedding 服务；不校验 API Key，仅绑本机",
        }

    @app.post("/v1/embeddings")
    def embeddings(req: EmbeddingRequest) -> dict[str, Any]:
        texts = _normalize_input(req)
        if not texts:
            raise HTTPException(status_code=422, detail="input 为空")

        vectors = [list(map(float, v)) for v in embedder.embed(texts)]
        if len(vectors) != len(texts):
            #: **条数必须与输入严格一致**：少一条就意味着某题被静默丢弃，
            #: 而 chunk_id 是按位置对齐的 ⇒ 错位会让整份基线检索失效。
            raise HTTPException(
                status_code=500,
                detail=f"embedding 返回 {len(vectors)} 条，期望 {len(texts)} 条",
            )

        this_dim = len(vectors[0])
        if state["dimension"] is None:
            state["dimension"] = this_dim
        elif state["dimension"] != this_dim:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"维度漂移：本次 {this_dim}，此前 {state['dimension']}"
                    " ⇒ 同一模型不应变维"
                ),
            )

        return {
            "object": _OBJECT_LIST,
            "model": model_name,
            "data": [
                {"object": _OBJECT_EMBEDDING, "index": i, "embedding": vector}
                for i, vector in enumerate(vectors)
            ],
            "usage": {"prompt_tokens": 0, "total_tokens": 0},
        }

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1", help="**仅限本机**（默认）")
    parser.add_argument("--port", type=int, default=8009)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help=f"权重搜寻目录（默认 {DEFAULT_CACHE_DIR}，复用 HF 缓存 ⇒ 命中即不联网）",
    )
    args = parser.parse_args()

    uvicorn.run(
        create_app(args.model, args.cache_dir),
        host=args.host,
        port=args.port,
        log_level="error",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
