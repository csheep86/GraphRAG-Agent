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
# ⚠️ 路径带 `backend/` 前缀（2026-10-04，P2.5 / E3）：compose 的 `build.context`
#    已改为**仓库根**（为让 `COPY plugins` 有源）⇒ Dockerfile 内的相对路径全部要加前缀。
COPY backend/pyproject.toml backend/uv.lock ./
# `--no-install-project`：本项目是**应用**不是库，代码以 COPY 进镜像，
# 免得 uv_build 去找并不存在的 `backend/` 包目录（项目名与代码目录不同名）
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
# **P3-A 收口（2026-10-04）**：镜像里必须能跑 `scripts/init_rls_roles.py`——
# RLS 的角色 / 受控函数 / 策略**只能由超级用户建一次**，而部署侧负责这一步的是
# compose 的 `db-init` 一次性服务（它复用本镜像）。少了这一行，`db-init` 会在
# 容器里报 `No such file or directory`，而 backend 仍会**照常起来**——
# 于是"部署已完成、其实库里根本没装 RLS"（超级用户绕过一切策略，症状全无）。
COPY backend/scripts ./scripts

# **构建期烘焙插件**（ADR-0007 §3.1 / DR-A3）：manifest 进镜像后，镜像内即可自证
# 「这一版烘焙了哪些插件」——ADR-0007 §4 列的负面项正是「半年后无人知道客户 B 的
# 镜像里烘焙了什么」。插件**实现**仍在 `app/` 里（`entry_point` 指向既有类），
# 此处 COPY 的是清单（B 类插件将来还会带契约片段与前端资源）。
COPY plugins ./plugins

# 非 root 运行；/data 承载 SQLite（`DATABASE_URL` 由 compose 指向此处）
RUN useradd -m -u 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
