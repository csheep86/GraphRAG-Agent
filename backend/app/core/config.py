"""应用配置：全部经环境变量 / `.env` 注入，禁止硬编码。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> parents[2] == backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
# parents[3] == 仓库根
REPO_ROOT = BACKEND_DIR.parent

# M1 验收 3 的 MIME 白名单（唯一真源，改动需同步 specs/m1-async-ingest.md §3）
DEFAULT_ALLOWED_MIME_TYPES: tuple[str, ...] = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
)

# 默认 Org / Actor：仅 development / test 下由 X-Org-Id / X-Actor-Id 兜底使用
DEFAULT_ORG_ID = UUID("00000000-0000-4000-8000-000000000001")
DEFAULT_ACTOR_ID = UUID("00000000-0000-4000-8000-0000000000aa")


class Settings(BaseSettings):
    """后端全部可配置项。"""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- 基础 --
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "GraphRAG-Agent Backend API"
    app_version: str = "1.0.0"
    api_prefix: str = "/api/v1"

    # -- 数据库：Sprint 1 临时兜底为 SQLite（见 backend/CODEBUDDY.md §1）--
    database_url: str = "sqlite:///./dev.db"

    # -- 租户隔离（ADR-0003）--
    allow_dev_org_header: bool = False
    default_org_id: UUID = DEFAULT_ORG_ID
    default_actor_id: UUID = DEFAULT_ACTOR_ID

    # -- 上传限制（M1 验收 2 / 3）--
    max_upload_size_mb: int = Field(default=100, gt=0)
    allowed_mime_types: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_MIME_TYPES)
    )

    # -- Prompt 目录（CODEBUDDY.md「Prompt 版本管理规范」）--
    prompts_dir: Path = REPO_ROOT / "prompts"

    # -- CORS（阶段 3.2 前端联调）--
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    @field_validator("allowed_mime_types")
    @classmethod
    def _normalize_mime_types(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().lower() for item in value if item.strip()]
        if not normalized:
            raise ValueError("ALLOWED_MIME_TYPES 不能为空")
        return normalized

    @model_validator(mode="after")
    def _guard_production_sqlite(self) -> Settings:
        """生产环境禁止 SQLite：不支持 RLS，会击穿 ADR-0003 的隔离底线。"""
        if self.app_env == "production" and self.database_url.startswith("sqlite"):
            raise ValueError(
                "生产环境禁止使用 SQLite（不支持 RLS）。"
                "请按 ADR-0003 §3.6 切换为 PostgreSQL 并启用行级安全。"
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def dev_org_header_enabled(self) -> bool:
        """`X-Org-Id` 兜底是否生效——仅非生产 + 显式开关同时满足。"""
        return self.allow_dev_org_header and not self.is_production

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
