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

    # -- Neo4j（阶段九：ADR-0002 主写入 / 查询目标）--
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    neo4j_connection_timeout_seconds: float = Field(default=5.0, gt=0)

    # -- LLM 推理（接缝 3：OpenAI 兼容 Provider，Sprint 5 批次 A2 去厂商硬编码）--
    # 原 deepseek_* 字段改名为中性 llm_*（.env 需同步改名，见 changes/Sprint5.2）；
    # llm_provider 是接缝 3 的切换开关（内网双轨时指向本地 vLLM/Ollama 端点，
    # 见 plan §3.4-5 / §18.4）。
    llm_provider: str = "openai_compatible"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    llm_request_timeout_seconds: float = Field(default=60.0, gt=0)

    # -- 解析 Provider（接缝 3：parser 侧切换开关，Sprint 5 批次 A2）--
    # 当前唯一实现 mineru_cloud；内网本地解析通路（plan §18.4）落地时在此切换。
    parser_provider: str = "mineru_cloud"

    # -- 异步任务并发（ADR-0001 §3.3）--
    task_parse_concurrency: int = Field(default=2, ge=1)
    task_retry_initial_seconds: float = Field(default=1.0, gt=0)
    task_retry_max_attempts: int = Field(default=3, ge=1)
    task_retry_multiplier: float = Field(default=2.0, gt=1)

    # -- 处理管线阶段（接缝 4：启停与顺序，Sprint 5 批次 A2）--
    # 顺序即执行顺序；删除某项 = 停用该阶段。未登记执行体的阶段自动跳过
    # （document.extract / kg.build 随批次 B、risk.detect 随 Sprint 7 登记）。
    pipeline_stages: list[str] = [
        "document.parse",
        "document.extract",
        "kg.build",
        "risk.detect",
    ]

    # -- 存储（M1 §4.3：开发本地 FS；生产 S3 由抽象层切换，不加无消费者的开关）--
    storage_root: Path = BACKEND_DIR / "storage"

    # -- MinerU 云解析（Sprint 5 批次 A 接入主链路；批次 A2 将收口为 parser_provider）--
    mineru_api_base: str = "https://mineru.net"
    mineru_token: str = ""
    mineru_model_version: str = "vlm"
    mineru_language: str = "ch"
    mineru_request_timeout_seconds: float = Field(default=120.0, gt=0)
    mineru_poll_interval_seconds: float = Field(default=5.0, gt=0)
    mineru_poll_timeout_seconds: float = Field(default=600.0, gt=0)

    # -- 基础 --
    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "GraphRAG-Agent Backend API"
    app_version: str = "1.1.0"
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

    # -- 实体 / 关系抽取（Sprint 5 批次 B：LangExtract 接入；接缝 3 内部档位）--
    # 与 MineruClient 同模式：单实现 + 切换键，不抽接口；
    # `extraction_provider` 默认 'langextract'，未实现别档显式报错（与 llm_provider 同策略）。
    extraction_provider: str = "langextract"
    #: 单次送入 LLM 的最大字符数；超长在客户端内切分
    extraction_max_chars_per_chunk: int = Field(default=4000, gt=0)
    #: 单文档实体上限（防 LLM 失控批量生成）
    extraction_max_entities_per_doc: int = Field(default=500, gt=0)
    #: 单文档关系上限
    extraction_max_relations_per_doc: int = Field(default=1000, gt=0)
    #: Prompt 版本（CODEBUDDY.md 版本管理规范）；prompt_loader 必须有对应版本文件
    extraction_prompt_version: str = "kg_extraction_v1"

    # -- KG 构建（Sprint 5 批次 B：ADR-0002 三段式写入 Neo4j）--
    #: stage-2 / stage-3 batch LOAD 的批大小（防内存峰值）
    kg_build_batch_size: int = Field(default=500, gt=0)
    #: 唯一档位 'per_org'（全局版本留 Pro / Enterprise，ADR-0004 §3 第 2 条）
    kg_version_strategy: str = "per_org"

    # -- Agent fail-closed（ADR-0003 强化：跨租户子图必须由 PG documents 兜底校验）--
    #: True = 跨 org_id 即抛 KG_TENANT_LEAK（路由层转 403）；False 仅日志告警
    agent_fail_closed: bool = True

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
