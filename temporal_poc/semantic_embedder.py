"""真实中文语义 Embedding（用于消除 Track G 的"占位向量"干扰项）。

默认 `BAAI/bge-small-zh-v1.5`（1024 维量级小、中文效果好）。
国内网络拉不到 HF 时，先试 HF 镜像：设置 `HF_ENDPOINT=https://hf-mirror.com`。
"""

from __future__ import annotations

from graphiti_core.embedder.client import EmbedderClient, EmbedderConfig  # noqa: E402

MODEL_NAME = "BAAI/bge-small-zh-v1.5"


class SemanticEmbedder(EmbedderClient):
    """包装 sentence-transformers，实现 Graphiti 的 EmbedderClient 契约。"""

    def __init__(self, model_name: str = MODEL_NAME, dim: int = 512) -> None:
        from sentence_transformers import SentenceTransformer

        self.config = EmbedderConfig(embedding_dim=dim)
        self._dim = dim
        self._model = SentenceTransformer(model_name)

    async def create(
        self, input_data: str | list[str] | __import__("typing").Iterable
    ) -> list[float]:
        text = input_data if isinstance(input_data, str) else " ".join(map(str, input_data))
        vector = self._model.encode([text], normalize_embeddings=True)[0]
        return [float(value) for value in vector]

    async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
        vectors = self._model.encode(input_data_list, normalize_embeddings=True)
        return [list(map(float, vector)) for vector in vectors]


def build_semantic_embedder() -> SemanticEmbedder:
    embedder = SemanticEmbedder()
    probe = embedder._model.encode(["连通性自检"], normalize_embeddings=True)[0]
    print(f"[semantic] 已加载 {MODEL_NAME}，维度={len(probe)}")
    return embedder


if __name__ == "__main__":
    build_semantic_embedder()
