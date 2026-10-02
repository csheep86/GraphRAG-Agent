"""M6 本体增量演进契约（spec §5.5 的 6 个 ontology 端点 + §4.1 数据形状）。

**本批（`changes/P0-m6-finalization` F2）只落契约与 501 占位骨架，不含业务逻辑**
（Non-goals：占位骨架 ≠ 实现，实现归 P5-M6 批次）。

字段形状与 F1 的 :class:`~app.services.ontology.OntologySuggestion` **同构**
（``{name, description?}`` / ``{name, head_types, tail_types, description?}``）
⇒ 冷启动建议的结果可以**原样**交给 ``POST /ontology/confirm``，
**不需要**在路由层 / 前端做二次映射——映射层是错配的高发地，能不写就不写。

**两处 spec 写了省略号的地方，本批不自行展开**（CODEBUDDY §功能预留原则：
预留是留位子，不是替 spec 发明字段）：

- ``POST /ontology/split`` 的 ``new_entities[]`` 除 ``canonical_name`` 外的其余字段；
- ``GET /cost/dashboard`` 的 ``by_date[]`` 每项字段（见 :mod:`app.schemas.cost`）。

⇒ 均已登记为**定稿增补项**，由 F3 裁决（``integration-log.md`` §2）。

**为什么响应体按 §5.5 逐字照抄、不加 ``trace_id``**：§5.5 只有冷启动响应列了
``trace_id``，其余 6 个没列。项目惯例是所有响应都带 —— 两者冲突时**以 spec 为准**，
差异登记待 F3 裁决（``X-Trace-Id`` 响应头恒回显，不受此影响）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OntologyEntityType(BaseModel):
    """一个实体类型（与 F1 建议结果、``ontology_schemas.entity_types`` 同形状）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"name": "EMPLOYEE", "description": "员工，含正式工与合同工"}
        }
    )

    name: str = Field(
        min_length=1,
        max_length=64,
        description=(
            "类型名。**必须英文大写下划线**（如 `EMPLOYEE` / `POLICY_CLAUSE`）——"
            "它会被整段塞进抽取 Prompt 的类型词表，中文或含空格会导致抽取侧匹配失败"
        ),
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="中文一句话说明该类型在本域指什么；可省略",
    )


class OntologyRelationType(BaseModel):
    """一个关系类型（含首尾实体类型约束）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "PARTY_TO",
                "head_types": ["COMPANY"],
                "tail_types": ["COMPANY"],
                "description": "双方存在关联关系",
            }
        }
    )

    name: str = Field(
        min_length=1,
        max_length=64,
        description="关系类型名，同实体类型的命名约束（英文大写下划线）",
    )
    head_types: list[str] = Field(
        description="允许的头实体类型名（**必须**取自同一份 entity_types）"
    )
    tail_types: list[str] = Field(
        description="允许的尾实体类型名（**必须**取自同一份 entity_types）"
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="中文一句话说明该关系在本域指什么；可省略",
    )


class OntologyColdStartRequest(BaseModel):
    """`POST /ontology/cold-start` 请求：一段业务域描述换一组类型建议。"""

    model_config = ConfigDict(
        json_schema_extra={"example": {"domain_description": "财务关联交易识别"}}
    )

    domain_description: str = Field(
        min_length=1,
        max_length=2000,
        description="业务域描述（人工输入）。越具体，建议的类型越贴业务",
    )


class OntologyColdStartResponse(BaseModel):
    """`POST /ontology/cold-start` 响应：**仅建议，未生效**。

    ⚠️ **未确认不生效**（M6 §3.1 验收 1 / §3.5 验收 12）：本端点只返回建议，
    **不**写 `ontology_schemas`；要生效必须再调 `POST /ontology/confirm`。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "suggested_entity_types": [
                    {"name": "COMPANY", "description": "法人主体"},
                    {"name": "EMPLOYEE"},
                ],
                "suggested_relation_types": [
                    {
                        "name": "PARTY_TO",
                        "head_types": ["COMPANY"],
                        "tail_types": ["COMPANY"],
                        "description": "关联关系",
                    }
                ],
                "trace_id": "5f2c1b7e-9d4a-4c1e-8f3b-6a0d2e5c7b91",
            }
        }
    )

    suggested_entity_types: list[OntologyEntityType] = Field(
        description="建议的实体类型（**未生效**，需 confirm）"
    )
    suggested_relation_types: list[OntologyRelationType] = Field(
        description="建议的关系类型（**未生效**，需 confirm）"
    )
    trace_id: str = Field(
        description="本次请求的 trace_id（冷启动含 LLM 调用，便于溯源）"
    )


class OntologyConfirmRequest(BaseModel):
    """`POST /ontology/confirm` 请求：把（人工校正后的）类型集确认为 active。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": 1,
                "entity_types": [{"name": "COMPANY", "description": "法人主体"}],
                "relation_types": [
                    {
                        "name": "PARTY_TO",
                        "head_types": ["COMPANY"],
                        "tail_types": ["COMPANY"],
                    }
                ],
            }
        }
    )

    version: int = Field(ge=1, description="要确认生效的 schema 版本号")
    entity_types: list[OntologyEntityType] = Field(description="确认后的实体类型集")
    relation_types: list[OntologyRelationType] = Field(description="确认后的关系类型集")


class OntologyConfirmResponse(BaseModel):
    """`POST /ontology/confirm` 响应：确认生效的结果。

    `status` **只有 `active`** 一种取值——写进 Literal 是刻意的：契约不承诺
    产不出的状态（M6 §4.1 的 `status` 只有 `active` / `superseded` 两档，
    本端点不可能返回 `superseded`）。
    """

    model_config = ConfigDict(
        json_schema_extra={"example": {"version": 1, "status": "active"}}
    )

    version: int = Field(ge=1, description="已生效的 schema 版本号")
    status: Literal["active"] = Field(description="生效状态（**恒为** `active`）")


class OntologyMergeRequest(BaseModel):
    """`POST /ontology/merge` 请求：合并两个实体（M6 §3.2 三动作之一）。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "left_entity_id": "ent_6f1c2b7e9d4a",
                "right_entity_id": "ent_9a0d2e5c7b91",
            }
        }
    )

    left_entity_id: str = Field(
        min_length=1, max_length=64, description="保留侧的实体 id"
    )
    right_entity_id: str = Field(
        min_length=1,
        max_length=64,
        description="被并入侧的实体 id（合并后不再独立存在）",
    )


class OntologyNewEntity(BaseModel):
    """`POST /ontology/split` 里拆分出的**新实体**。

    ⚠️ spec §5.5 写的是 ``{canonical_name, ...}``——省略号部分本批**不展开**
    （功能预留原则），等 M6 实现批次按真实需求补字段并同步契约。
    """

    model_config = ConfigDict(json_schema_extra={"example": {"canonical_name": "张伟"}})

    canonical_name: str = Field(
        min_length=1, max_length=128, description="拆分后新实体的规范名"
    )


class OntologySplitRequest(BaseModel):
    """`POST /ontology/split` 请求：把一个实体拆成多个。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity_id": "ent_6f1c2b7e9d4a",
                "new_entities": [
                    {"canonical_name": "张伟"},
                    {"canonical_name": "张玮"},
                ],
            }
        }
    )

    entity_id: str = Field(min_length=1, max_length=64, description="要拆分的实体 id")
    new_entities: list[OntologyNewEntity] = Field(
        min_length=2,
        description=(
            "拆分出的新实体（**至少 2 个**——只拆出 1 个等价于改名，应走 "
            "`POST /ontology/rename`）。本约束为本批推断，待 F3 确认"
        ),
    )


class OntologyRenameRequest(BaseModel):
    """`POST /ontology/rename` 请求：改实体的规范名。"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity_id": "ent_6f1c2b7e9d4a",
                "new_canonical_name": "张伟",
            }
        }
    )

    entity_id: str = Field(min_length=1, max_length=64, description="要改名的实体 id")
    new_canonical_name: str = Field(
        min_length=1, max_length=128, description="新的规范名"
    )


class OntologyActionResponse(BaseModel):
    """merge / split / rename **三个动作共用**的响应（M6 §3.2：三动作，不多做）。

    `status` 恒为 `applied`：动作已应用到图谱并产出新的 `kg_version`。
    **没有 `pending`**——三动作是同步的（原子性由 M6 实现批次保证），
    契约不承诺产不出的中间态。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"kg_version": "kg-20261002-003", "status": "applied"}
        }
    )

    kg_version: str = Field(description="本次动作产出的图谱版本（新版本，非原版本）")
    status: Literal["applied"] = Field(description="动作状态（**恒为** `applied`）")


class OntologyActiveResponse(BaseModel):
    """`GET /ontology/active` 响应：当前生效的本体 schema。

    **无 active 时返回 409 `SCHEMA_VERSION_NOT_ACTIVE`**，与图谱版本的纪律一致：
    **严禁**静默返回一份"看起来合理"的默认 schema（那会让用户以为自己配过）。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "version": 1,
                "entity_types": [{"name": "COMPANY", "description": "法人主体"}],
                "relation_types": [
                    {
                        "name": "PARTY_TO",
                        "head_types": ["COMPANY"],
                        "tail_types": ["COMPANY"],
                    }
                ],
                "status": "active",
            }
        }
    )

    version: int = Field(ge=1, description="生效中的 schema 版本号")
    entity_types: list[OntologyEntityType] = Field(description="生效中的实体类型集")
    relation_types: list[OntologyRelationType] = Field(description="生效中的关系类型集")
    status: Literal["active"] = Field(description="状态（**恒为** `active`）")
