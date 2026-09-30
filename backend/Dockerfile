# D-1 容器化（Sprint 10.3）— backend 运行镜像
#
# 纪律来源（`docs/deployment-spec.md`）：
#   §1.2「不做客户现场编译 / 禁现场 pip install」⇒ 依赖 baked 进镜像；
#   §3  「密钥禁止写进镜像」⇒ 本镜像**不含** `.env`，配置全部由 compose 以环境变量注入；
#   §2   端口取默认 8000。
#
# 与业务解耦（裁决 D-P）：本文件不改动任何业务代码与契约。

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

# uv 版本固定（可复现；`:latest` 是今日清理教训里"占 1.14GB 却没人用"的同义词）
COPY --from=ghcr.io/astral-sh/uv:0.12.14 /uv /usr/local/bin/uv

WORKDIR /app

# 依赖先行分层：只拷清单，代码变了不必重装依赖
COPY pyproject.toml uv.lock ./
# `--no-install-project`：本项目是**应用**不是库，代码以 COPY 进镜像，
# 免得 uv_build 去找并不存在的 `backend/` 包目录（项目名与代码目录不同名）
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

# 非 root 运行；/data 承载 SQLite（`DATABASE_URL` 由 compose 指向此处）
RUN useradd -m -u 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
