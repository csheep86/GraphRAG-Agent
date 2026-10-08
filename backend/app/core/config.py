"""应用配置：全部经环境变量 / `.env` 注入，禁止硬编码。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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

#: JWT 签名的**开发态**密钥（P2-C）。**生产沿用此值即启动失败**
#: （见 :meth:`Settings._guard_production_jwt_secret`）——拿一个开源默认值去签令牌，
#: 等于任何人都能给自己签一份 admin。
DEFAULT_JWT_SECRET = "dev-only-jwt-secret"


class Settings(BaseSettings):
    """后端全部可配置项。"""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- License（接缝 9 / DR-C1 / ADR-0006）--
    # ⚠️ 六项**逐项**都有真实消费点，**无一占位**（ADR-0004 §3 第 5 条；写了不读 ⇒ CI 红，
    # 由 scripts/check_seams.py 的「settings 必须有消费者」判据盯住）：
    #   - license_file_path / _public_key / _state_ttl_seconds → LicenseProvider 加载与重载；
    #   - license_fp_salt → 机器指纹计算；
    #   - license_clock_skew_tolerance_days → 时钟漂移（只告警不拒绝）；
    #   - license_enforce → LicenseMiddleware（false 时放行，但**必须**落 license.bypass 审计）。
    license_file_path: str = "deploy/license/app.lic"
    #: Ed25519 公钥（base64）。**留空 = 一律验签失败** —— 没有密钥就应当拒绝，
    #: 而不是退化为「不校验」（后者会让 License 形同虚设，ADR-0006 §2.3）。
    license_public_key: str = ""
    license_enforce: bool = True
    #: 指纹 salt（ADR-0006 §2.1：应用级，同一客户 / 同一版本一致，**不是密钥**）
    license_fp_salt: str = "graphrag-fp-salt-v1"
    #: 内存态 TTL（秒）——到期重载，保证每请求都是 O(1) 判断（§2.6 / R-L4）
    license_state_ttl_seconds: int = Field(default=60, gt=0)
    #: 时钟回拨容忍天数（§2.7：只告警不拒绝，避免客户调时钟把自己锁死）
    license_clock_skew_tolerance_days: int = Field(default=7, ge=0)

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

    # -- 评测基线 embedding（A1 / L10-A1：dense top-k 基线侧的向量化）--
    # 消费者唯一落点：app/evaluation/baseline.py::build_default_embedder。
    # 留空⇒回落到 LLM_*：绝大多数 OpenAI 兼容网关的 chat 与 embeddings 同源。
    eval_embedding_base_url: str = ""
    eval_embedding_api_key: str = ""
    #: **刻意无默认值**：嵌入模型与对话模型必然不是同一个，填错会 Embedding 报 404，
    #: 给一个"看起来能用"的默认值反而会把错误推迟到跑数据那天。
    eval_embedding_model: str = ""
    #: 基线侧注入条数。**下限由 L10-A1 反向守卫钉住**：
    #: 不得小于图侧的 EVIDENCE_CHUNK_LIMIT（comparability_error 会在运行时再判一次）。
    eval_baseline_top_k: int = Field(default=32, ge=1)

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
    app_version: str = "1.6.0"
    api_prefix: str = "/api/v1"

    # -- 数据库：**DR-B1 裁决**：开发 / 测试 / 生产一律 PostgreSQL 16.x --
    # SQLite **既非替身也非兜底**：原「开发态替身」口径已于 2026-10-01 作废——
    # 它让方言债在「反正只是开发库」的心态下持续累积（RK-2 的成因）。
    database_url: str = "postgresql+psycopg://graphrag:graphrag@localhost:5432/graphrag"

    #: **owner 连接串（P3-D，2026-10-04 新增）：建表 / 迁移 / DDL 专用**。
    #:
    #: 为什么必须有第二串：P3-A 把应用账号切成了受限角色 ``app_rls``（``NOBYPASSRLS``，
    #: 只有 DML）。而 **DDL 需要 owner**——``app_rls`` 跑 ``alembic upgrade head`` 会
    #: 直接 ``permission denied``。在此之前仓库里**没有**这个配置（``DATABASE_URL_OWNER``
    #: 只被测试侧用 ``os.environ`` 直接读）⇒ 部署形态下**升级路径是断的**，而平时没人会发现。
    #:
    #: 为 ``None`` 时（本地 / 老环境）回落到 ``database_url``——那通常就是超级用户，
    #: 能跑 DDL，行为与改动前一致。
    database_url_owner: str | None = None

    # -- 租户隔离（ADR-0003）--
    allow_dev_org_header: bool = False
    default_org_id: UUID = DEFAULT_ORG_ID
    default_actor_id: UUID = DEFAULT_ACTOR_ID

    # -- 登录与访问令牌（P2-C：DR-D9 的「真实登录」一半；接缝 1 仍只有 LocalAuthProvider）--
    #: JWT（HS256）签名密钥。**dev / test 之外的环境必须显式注入**：沿用开源默认值
    #: 去签令牌，等于任何人都能给自己签一份 admin ⇒ 生产启动即失败（fail-closed，
    #: 与 :meth:`_guard_production_sqlite` 同款口径）。
    #: 唯一消费点：`app/services/auth/token.py`（签发与验签各一次）。
    auth_jwt_secret: str = DEFAULT_JWT_SECRET
    #: 访问令牌有效期（**分钟**）。唯一消费点：
    #: `app/services/auth/token.py::issue_access_token`。
    auth_jwt_ttl_minutes: int = Field(default=480, gt=0)

    # -- 上传限制（M1 验收 2 / 3）--
    max_upload_size_mb: int = Field(default=100, gt=0)
    allowed_mime_types: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_MIME_TYPES)
    )

    # -- Prompt 目录（CODEBUDDY.md「Prompt 版本管理规范」）--
    prompts_dir: Path = REPO_ROOT / "prompts"

    # -- 问答引用闸门（Sprint 10 批次 E，用户决策 A）--
    #: 引用**归因**闸门：答案里的凭据（实体提及 / 单号 / 数字）必须能在被引 chunk 的
    #: 原文里逐字找到，找不到的引用一律丢弃；全丢 ⇒ 按 ``no_grounded_evidence`` 拒答。
    #:
    #: 为什么需要：实测「引用覆盖率 100%」抓不到归因错——chunk_id 合法、前缀也对，
    #: 但那条 chunk 里根本没有答案依据（Q11 答「LV0001 病假」却挂了一条门禁刷卡记录）。
    #: 这是 F3「引用可溯源」的核心，覆盖率只是它的弱代理指标。
    #:
    #: 关掉即回到「chunk_id 合法就放行」的旧口径——**只用于 A/B 对照**，不是常态档位。
    qa_citation_gate_enabled: bool = True

    # -- 实体 / 关系抽取（Sprint 5 批次 B：LangExtract 接入；接缝 3 内部档位）--
    # 与 MineruClient 同模式：单实现 + 切换键，不抽接口；
    # `extraction_provider` 默认 'langextract'，未实现别档显式报错（与 llm_provider 同策略）。
    extraction_provider: str = "langextract"
    #: 抽取引擎（Sprint 7.0 新增，偿 v1.1.0 §6.3「注入 provider 后启用」悬空债）：
    #:   'llm'  = 真实调用 LLM（经接缝 3 build_chat_model，不新建客户端）；
    #:   'mock' = 正则占位器（仅 CI / 单测注入，产物不代表真实抽取质量）。
    #: 未知档位由 LangextractClient 显式报错，**绝不静默回退**（plan §4.4）。
    #: 唯一消费点：app/services/extraction/langextract.py::LangextractClient.from_settings
    extraction_engine: str = "llm"
    #: 单次送入 LLM 的最大字符数；超长在客户端内切分
    extraction_max_chars_per_chunk: int = Field(default=4000, gt=0)
    #: 单文档实体上限（防 LLM 失控批量生成）。
    #: Sprint 7.1 批次 A 真机校准：**500 对 190 页级文档不够**——蛇口 p1-190 抽完后
    #: 裁剪到 500，`招商局集团有限公司` 还在，`缪建民` / 注册地址这类"低密度但高价值"
    #: 实体全部被按 confidence 挤掉（M4 的数据前提直接落空）。
    #: 该上限是**容量护栏**不是疑点阈值：放宽它不会制造任何疑点，只会少丢真实实体；
    #: 裁剪前后的数量都记在 ``langextract_done`` 日志里（``*_before_clamp``）。
    extraction_max_entities_per_doc: int = Field(default=2000, gt=0)
    #: 单文档关系上限（同上：``LEGAL_REP`` / ``REGISTERED_AT`` 不能被挤掉）
    extraction_max_relations_per_doc: int = Field(default=4000, gt=0)
    #: Prompt 版本（CODEBUDDY.md 版本管理规范）；prompt_loader 必须有对应版本文件。
    #: Sprint 7.1 批次 A：v2 = v1 + 类型枚举参数化（``{{entity_types}}`` /
    #: ``{{relation_types}}``）+ 法人 / 地址两类（M4 算法的数据前提）；v1 文件保留不动。
    #: Sprint 9 批次 A：**v3 = v2 + 知识时效**（ADR-0005 §4 / §6 L0）——关系带
    #: ``valid_from`` / ``valid_to``，并新增 ``{{document_date}}`` 作为 R4 不猜值的
    #: 兜底源；v1 / v2 文件保留不动。切版本只需改这里——渲染层按模板**声明的占位符**
    #: 给值（见 ``extraction._render_extraction_prompt``），**不按版本号走分支**。
    extraction_prompt_version: str = "kg_extraction_v3"

    # -- KG 构建（Sprint 5 批次 B：ADR-0002 三段式写入 Neo4j）--
    #: stage-2 / stage-3 batch LOAD 的批大小（防内存峰值）
    kg_build_batch_size: int = Field(default=500, gt=0)
    #: 唯一档位 'per_org'（全局版本留 Pro / Enterprise，ADR-0004 §3 第 2 条）
    kg_version_strategy: str = "per_org"
    #: M6 §3.3 增量重算：单批重写受影响子图的**节点数**（避免大事务）。
    #: 唯一消费点：app/services/kg/incremental.py::rebuild_incrementally
    increment_rebuild_batch_size: int = Field(default=100, gt=0)

    # -- Agent fail-closed（ADR-0003 强化：跨租户子图必须由 PG documents 兜底校验）--
    #: True = 跨 org_id 即抛 KG_TENANT_LEAK（路由层转 403）；False 仅日志告警
    agent_fail_closed: bool = True
    #: G-17 / DR-B12 逃生阀围栏：``agent_fail_closed=False`` 会让跨租户隔离
    #: **降级为 fail-open**（仅告警放行），这是全系统**唯一一个可配置关闭租户
    #: 隔离**的开关。默认**禁止**；客户侧确需时必须显式置
    #: ``ALLOW_AGENT_FAIL_OPEN=true``，并同时完成「显式登记 + 告知客户 + 落审计」
    #: 三项（与信创降级 DR-B10 同级别处理）。
    allow_agent_fail_open: bool = False

    # -- CORS（阶段 3.2 前端联调）--
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )

    # -- 限流（M5 §3 验收 5 / 决策 A11：slowapi，"默认 N=60，可配置"）--
    #: 同一 IP 每分钟对同一接口的请求上限。唯一消费点：core/limiter.py::get_limiter
    rate_limit_per_minute: int = Field(default=60, ge=1)

    # -- 私域出向管控（M5 §3 验收 4 / §4.6，spec 名为 `private_deploy`）--
    #: 私域部署开关。**true** ⇒ 出向目标必须是**内网地址**或在 `ALLOWED_EGRESS_HOSTS`
    #: 白名单内，否则在**构造期**抛 503 `PRIVATE_DEPLOY_BLOCKED`（守护 + 审计）。
    #: 为什么默认 **false**：开发 / CI 的 `LLM_BASE_URL` 就是公网地址，置 true 会让
    #: 一大批用例（含必需联网的计算项）全部失败；生产是否置 true 属部署侧动作
    #: （本批**不**加"生产必须为 true"的护栏——那是新增需求，登记为建议项）。
    #: 唯一消费点：app/core/egress.py::guard_egress
    private_deploy_enabled: bool = False
    #: 出向白名单。条目形如 `host` 或 `host:port`（写了端口 ⇒ 端口必须匹配，
    #: **不**静默忽略端口那个部分）；**本批只做精确匹配，不支持通配 / 子域**。
    #: 为什么还需要它：内网 / 回环天然放行（D9），白名单是给「确实在公网上、
    #: 但客户允许出向」的目标留的口子。
    #: 唯一消费点：app/core/egress.py::_matches_allowlist
    allowed_egress_hosts: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # -- 敏感字段脱敏（M5 §3 验收 3 / §4.5 / §5.3）--
    #: 哈希类脱敏（税号 / 法人姓名 / 身份证）的 salt。
    #:
    #: ⚠️ 与 ``license_fp_salt`` **同款**：它是**应用级 salt，不是密钥**
    #: （ADR-0006 §2.1 同口径）——它防的是「同一份原文在不同部署里算出同一个哈希
    #: 从而被彩虹表反查」，**不提供**机密性，也不得被写成"我们有加密"。
    #:
    #: 生产部署**应当**换成部署侧私有值（换值会让既有哈希不可比对，属预期行为：
    #: 脱敏值本就不需要跨部署一致）。
    #: 唯一消费点：app/core/masking.py::_mask_hashed。
    mask_salt: str = "graphrag-mask-salt-v1"

    # -- 可观测导出（ADR-0004 §2.1 注：不单列接缝；§3 第 5 条的"合规占位"）--
    #: 统一日志平台 / OTLP 导出开关。**Demo-MVP 阶段未实现**：置 true 时
    #: core/logging.py 显式抛 NOT_IMPLEMENTED，绝不静默无效（占位≠假做）。
    #: 唯一消费点：core/logging.py::setup_logging
    log_export: bool = False

    # -- 评测准入线（TBD-7 / DR-D10；P0-m6-eval 批次 E3 落地）--
    #: C3-a「单文档成本」上限。**单位 = token / 文档**（**不是**元——spec §4.3 的
    #: ``single_doc_cost`` 把 token 与钱混用了，这里不继承那个歧义）。
    #:
    #: **来源 = 2026-10-03 演示语料推算，provisional（不是达标线）**：
    #:   单次抽取 LLM 调用 1799 tokens（矩阵 §3.4 M2-7 真机）
    #:   × 约 13 chunk/文档（attendance-demo-v1 = 224 chunks / 15 docs，其中 CSV 派生
    #:     约占 77% ⇒ 4 份 docx ≈ 52 chunks ⇒ ≈13/文档）
    #:   ≈ 23.4k token/文档 × 1.35 余量 ⇒ 取整 32 000。
    #:
    #: ⚠️ **chunk 数一律读 `backend/data/eval/MANIFEST.json`**（当前值的**单一真源**）。
    #:    `scripts/eval_controlled_qset.py` 注释里的 **230 是 2026-09-30 那次 probe 的
    #:    历史值**（旁证：`tests/test_langextract_chunks.py` 记「230 → 去重后 205」），
    #:    **不可**拿它推演阈值——本字段的推算就差点踩这条。按 224 重算仍是 ≈13 chunk/文档
    #:    ⇒ 32 000 **不变**，但**分母的出处必须写对**。
    #:
    #: ⚠️ TBD-7 正式收敛在 **P6**：须经 `scripts/eval_acceptance.py --calibrate` 校准；
    #:    校准前判定只给 ``PASS(provisional)``（**不构成 TBD-7 收敛证据**，§5.2 第 3 条）。
    #:    已知不确定性：若抽取是「每文档一次调用」而非「每 chunk 一次」，真实量级
    #:    会掉到 ~2k/文档 ⇒ 32 000 偏松，这正是 `--calibrate` 存在的理由。
    #:
    #: 唯一消费点：`app/evaluation/runner.py::resolve_cost_ceiling`（C3-a 判定）
    #:            + `scripts/eval_acceptance.py::_calibrate`（校准建议）。
    eval_single_doc_token_ceiling: int = Field(default=32_000, gt=0)

    @field_validator("allowed_mime_types")
    @classmethod
    def _normalize_mime_types(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().lower() for item in value if item.strip()]
        if not normalized:
            raise ValueError("ALLOWED_MIME_TYPES 不能为空")
        return normalized

    @field_validator("allowed_egress_hosts", mode="before")
    @classmethod
    def _decode_egress_hosts(cls, value: object) -> list[str]:
        """把环境变量的**原始字符串**解析成清单（容忍 JSON 数组 / 逗号分隔 / 空串）。

        为什么不能用 source 层默认的 JSON 解析：``ALLOWED_EGRESS_HOSTS=``（空值）
        会让 **服务启动即失败**（``SettingsError: Expecting value: line 1 column 1``，
        本机实跑复现），而"白名单缺省"是这个字段**最常见的合法取值**——
        不该让一个缺省形态把整套服务带停。故用 ``NoDecode`` 接管解析。
        """
        if value is None:
            return []
        if not isinstance(value, str):
            return value  # type: ignore[unreachable] - 直接传 list 的场合（含 init）
        text = value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except ValueError:
            return text.split(",")
        if isinstance(decoded, list):
            return [str(item) for item in decoded]
        return [str(decoded)]

    @field_validator("allowed_egress_hosts")
    @classmethod
    def _normalize_egress_hosts(cls, value: list[str]) -> list[str]:
        """归一化：去空白、统一小写、**丢掉空项**。

        ⚠️ 为什么必须显式丢空项：条目一旦出现 ``''``，「白名单为空」与
        「有一条匹配任何东西的规则」这两种状态就会混为一谈——
        `M5` 陷阱表专门点过这一条（清单型配置被解析成 `['']` 是典型形态）。
        """
        return [item.strip().lower() for item in value if item.strip()]

    @model_validator(mode="after")
    def _guard_production_sqlite(self) -> Settings:
        """生产环境禁止 SQLite：不支持 RLS，会击穿 ADR-0003 的隔离底线。"""
        if self.app_env == "production" and self.database_url.startswith("sqlite"):
            raise ValueError(
                "生产环境禁止使用 SQLite（不支持 RLS）。"
                "请按 ADR-0003 §3.6 切换为 PostgreSQL 并启用行级安全。"
            )
        return self

    @model_validator(mode="after")
    def _guard_agent_fail_open(self) -> Settings:
        """G-17：禁止**无声**关闭跨租户隔离（ADR-0003 §3.7）。

        ``agent_fail_closed=False`` 会让泄漏从「403 阻断」退化成「仅告警放行」。
        ADR-0003 §3.7 定的是「应用层过滤升格为常设防线、**不设移除条件**」——
        若允许一个配置项无声关掉它，那条裁决就被架空了。

        因此本守卫只拦「无声」：客户侧确需时，显式置 ``ALLOW_AGENT_FAIL_OPEN=true``
        即可破例，但破例须同时完成登记 / 告知 / 审计三项。
        """
        if self.agent_fail_closed or self.allow_agent_fail_open:
            return self
        raise ValueError(
            "agent_fail_closed=False 会让跨租户隔离降级为 fail-open（仅告警放行），"
            "违反 ADR-0003 §3.7「常设防线、不设移除条件」。"
            "客户侧确需时必须同时置 ALLOW_AGENT_FAIL_OPEN=true，"
            "并完成「显式登记 + 告知客户 + 落审计」三项（与信创降级 DR-B10 同级）。"
        )

    @model_validator(mode="after")
    def _guard_production_jwt_secret(self) -> Settings:
        """生产环境禁止沿用默认 JWT 密钥（P2-C）。

        为什么必须启动就拦：`auth_jwt_secret` 是**签名**密钥，它的默认值和数据库口令
        的默认值性质不同——口令猜不到就进不来，而一个公开的签名密钥意味着
        **任何人都能给自己签一份任意 org / 任意主体的令牌**，且事后无法区分伪造与真实。
        故不能用"日志警告"这种软处置。
        """
        if self.is_production and self.auth_jwt_secret == DEFAULT_JWT_SECRET:
            raise ValueError(
                "生产环境禁止沿用默认 AUTH_JWT_SECRET（开源默认值签出来的令牌"
                "任何人都能伪造）。请经 Secrets / KMS 注入一个随机密钥。"
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
