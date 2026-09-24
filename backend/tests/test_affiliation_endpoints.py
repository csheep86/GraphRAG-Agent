"""Sprint 7.2 批次 B：M4 疑点端点 + 任务状态机（spec §4.3–4.5 / §5.5）。

守的是四条**真机踩过或 spec 明文**的纪律：

1. **任务状态唯一真值源 = PG**（ADR-0001 要求 1）：`POST detect` 返回的任务必须在表里，
   且能被 `GET /affiliation/tasks/{id}` 读到；
2. **租户边界**：跨租户任务 / 疑点 → **403**，不存在 → **404**（ADR-0003，两者不混用）；
3. **批次口径 B2**：`GET /suspicions` 不带 `task_id` 时取**最近一条 completed 任务**的疑点，
   不带回旧批次；
4. **每次提交新建任务（B3）**：重复 POST 得到**两个不同** task_id（幂等由任务承载，
   不是「复用上次的疑点」）。

> 路由层的 `TaskManager` 在本文件里被替换成记账用的假实现——**不是**为了跳过验证：
> 真实执行体会连 Neo4j 跑两跳查询，那是 `changes/Sprint7.2/integration-log.md` §8 的
> 真机环节；单测只表征 HTTP 语义与 PG 落库。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

import pytest
from fastapi import BackgroundTasks
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.models import AffiliationSuspicion, AffiliationTask, Document
from app.db.session import SessionLocal, init_db
from app.tasks.manager import TaskManager, recover_orphan_tasks
from app.tasks.types import TaskSpec

_SETTINGS = get_settings()
#: dev_headers 对应的租户（= `settings.default_org_id`），即「当前租户」
ORG_A: uuid.UUID = _SETTINGS.default_org_id
#: 外部租户，用于跨租户回到 403
ORG_B = uuid.uuid4()


@pytest.fixture(autouse=True, scope="module")
def _ensure_schema() -> None:
    init_db()


@pytest.fixture
def created_ids() -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    yield ids
    with SessionLocal() as session:
        session.execute(
            delete(AffiliationSuspicion).where(
                AffiliationSuspicion.org_id.in_((ORG_A, ORG_B))
            )
        )
        session.execute(
            delete(AffiliationTask).where(AffiliationTask.org_id.in_((ORG_A, ORG_B)))
        )
        session.commit()


def _insert_document(*, org_id: uuid.UUID) -> uuid.UUID:
    """插一条 completed 文档（仅供 detect 校验 `doc_ids` 归属，不触发解析链路）。"""
    row = Document(
        filename_hash=hashlib.sha256(b"m4-detect-fixture").hexdigest(),
        mime_type="text/plain",
        size_bytes=16,
        status="completed",
        uploaded_by=uuid.uuid4(),
        org_id=org_id,
        trace_id=uuid.uuid4(),
    )
    with SessionLocal() as session:
        session.add(row)
        session.commit()
        return row.id


def _insert_task(
    *,
    org_id: uuid.UUID,
    status: str = "pending",
    created_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> uuid.UUID:
    row = AffiliationTask(
        org_id=org_id,
        doc_ids=[str(uuid.uuid4())],
        status=status,
        trace_id=uuid.uuid4(),
    )
    with SessionLocal() as session:
        session.add(row)
        session.commit()
        if created_at is not None:
            row.created_at = created_at
        if completed_at is not None:
            row.completed_at = completed_at
            session.commit()
        return row.id


def _insert_suspicion(
    *,
    org_id: uuid.UUID,
    task_id: uuid.UUID,
    severity: str = "medium",
    status: str = "open",
) -> uuid.UUID:
    row = AffiliationSuspicion(
        org_id=org_id,
        task_id=task_id,
        suspicion_type="shared_legal_rep",
        severity=severity,
        entities=["sub-a", "sub-b", "shared-person"],
        entity_names=["甲公司", "乙公司", "缪某"],
        evidence=[
            {
                "node_id": "sub-a",
                "chunk_id": "chunk-abc123456789",
                "doc_id": str(uuid.uuid4()),
                "page": 1,
                "char_start": 0,
                "char_end": 10,
                "text": "法定代表人为缪某……",
            }
        ],
        kg_version="v-fixture",
        status=status,
        trace_id=uuid.uuid4(),
    )
    with SessionLocal() as session:
        session.add(row)
        session.commit()
        return row.id


class _FakeTaskManager:
    """只记账、不真跑（真跑会连 Neo4j）。"""

    def __init__(self, _background_tasks: BackgroundTasks) -> None:
        self.specs: list[TaskSpec] = []

    def submit(self, spec: TaskSpec) -> str:
        self.specs.append(spec)
        return str(spec.payload["affiliation_task_id"])


@pytest.fixture
def no_real_dispatch(monkeypatch: pytest.MonkeyPatch) -> list[_FakeTaskManager]:
    managers: list[_FakeTaskManager] = []

    def factory(_background_tasks: BackgroundTasks) -> _FakeTaskManager:
        manager = _FakeTaskManager(_background_tasks)
        managers.append(manager)
        return manager

    monkeypatch.setattr("app.api.v1.routes.affiliation.TaskManager", factory)
    return managers


# --------------------------------------------------------------------------- #
# 1) TaskManager 双载体投递（B8）
# --------------------------------------------------------------------------- #
def test_submit_affiliation_task_accepts_multi_document_payload(
    created_ids: list[uuid.UUID],
) -> None:
    """affiliation 类任务**没有** document_id，task_id 来自 `affiliation_tasks.id`。"""
    task_id = _insert_task(org_id=ORG_A)
    created_ids.append(task_id)

    background = BackgroundTasks()
    spec = TaskSpec(
        task_type="affiliation.detect",
        payload={"affiliation_task_id": str(task_id)},
        trace_id=str(uuid.uuid4()),
    )

    returned = TaskManager(background).submit(spec)

    assert returned == str(task_id)
    assert len(background.tasks) == 1, "执行体必须真的被投递（不是空转）"


def test_submit_unknown_affiliation_task_raises() -> None:
    spec = TaskSpec(
        task_type="affiliation.detect",
        payload={"affiliation_task_id": str(uuid.uuid4())},
        trace_id=str(uuid.uuid4()),
    )
    with pytest.raises(LookupError):
        TaskManager(BackgroundTasks()).submit(spec)


# --------------------------------------------------------------------------- #
# 2) 启动回收必须扫两张表（ADR-0001 第 73 行）
# --------------------------------------------------------------------------- #
def test_recover_reclaims_pending_affiliation_tasks(
    created_ids: list[uuid.UUID],
) -> None:
    task_id = _insert_task(org_id=ORG_A, status="processing")
    created_ids.append(task_id)

    report = recover_orphan_tasks()

    assert report.affiliation_reclaimed >= 1, (
        "扫不到 affiliation_tasks = 该表可能永久卡 processing"
    )
    with SessionLocal() as session:
        row = session.get(AffiliationTask, task_id)
        assert row is not None
        assert row.status == "failed"
        assert row.error_code == "TASK_INTERRUPTED"


# --------------------------------------------------------------------------- #
# 3) 端点：202 / 状态 / 批次口径（B2 / B3）
# --------------------------------------------------------------------------- #
def test_post_detect_returns_202_and_persists_task(
    client, dev_headers, created_ids, no_real_dispatch
) -> None:
    doc_id = _insert_document(org_id=ORG_A)

    response = client.post(
        "/api/v1/affiliation/detect",
        json={"doc_ids": [str(doc_id)]},
        headers=dev_headers,
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "pending"
    task_id = uuid.UUID(body["task_id"])
    created_ids.append(task_id)

    with SessionLocal() as session:
        row = session.get(AffiliationTask, task_id)
        assert row is not None, "任务真值源必须是 PG，不是响应体里的一句话"
        assert row.status == "pending"


def test_each_detect_creates_a_new_task(
    client, dev_headers, created_ids, no_real_dispatch
) -> None:
    """B3：重复提交 = 新任务，不复用上一次的疑点。"""
    doc_id = _insert_document(org_id=ORG_A)

    first = client.post(
        "/api/v1/affiliation/detect",
        json={"doc_ids": [str(doc_id)]},
        headers=dev_headers,
    )
    second = client.post(
        "/api/v1/affiliation/detect",
        json={"doc_ids": [str(doc_id)]},
        headers=dev_headers,
    )

    assert first.status_code == second.status_code == 202
    created_ids.extend(
        [uuid.UUID(first.json()["task_id"]), uuid.UUID(second.json()["task_id"])]
    )
    assert first.json()["task_id"] != second.json()["task_id"]
    assert len(no_real_dispatch) == 2, "两次提交各投一次，不能被幂等掉"


def test_detect_rejects_cross_tenant_document(client, dev_headers) -> None:
    foreign_doc_id = _insert_document(org_id=ORG_B)

    response = client.post(
        "/api/v1/affiliation/detect",
        json={"doc_ids": [str(foreign_doc_id)]},
        headers=dev_headers,
    )

    assert response.status_code == 403, response.text


def test_cross_tenant_task_is_403(client, dev_headers, created_ids) -> None:
    task_id = _insert_task(org_id=ORG_B)
    created_ids.append(task_id)

    response = client.get(f"/api/v1/affiliation/tasks/{task_id}", headers=dev_headers)

    assert response.status_code == 403, response.text


def test_missing_task_is_404(client, dev_headers) -> None:
    response = client.get(
        f"/api/v1/affiliation/tasks/{uuid.uuid4()}", headers=dev_headers
    )
    assert response.status_code == 404, response.text


def test_suspicion_list_defaults_to_latest_completed_batch(
    client, dev_headers, created_ids
) -> None:
    """B2：默认取**最近一条 completed** 任务；旧批次的疑点不混进来。"""
    older = _insert_task(
        org_id=ORG_A,
        status="completed",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        completed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    newer = _insert_task(
        org_id=ORG_A,
        status="completed",
        created_at=datetime(2026, 9, 24, tzinfo=UTC),
        completed_at=datetime(2026, 9, 24, tzinfo=UTC),
    )
    created_ids.extend([older, newer])
    _insert_suspicion(org_id=ORG_A, task_id=older, severity="low")
    fresh_id = _insert_suspicion(org_id=ORG_A, task_id=newer, severity="high")

    response = client.get("/api/v1/affiliation/suspicions", headers=dev_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["items"]] == [str(fresh_id)]
    assert body["task_id"] == str(newer)
    assert body["items"][0]["task_id"] == str(newer)


def test_suspicion_list_is_empty_when_no_batch_ran(client) -> None:
    """从未跑过检测 → 200 + 空列表 + `task_id = null`（**不**用 404 表示「没数据」）。"""
    headers = {"X-Org-Id": str(uuid.uuid4()), "X-Actor-Id": str(uuid.uuid4())}

    response = client.get("/api/v1/affiliation/suspicions", headers=headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == []
    assert body["task_id"] is None


# --------------------------------------------------------------------------- #
# 4) 复核流转（B4）
# --------------------------------------------------------------------------- #
def test_review_suspicion_writes_actor_and_is_not_reversible(
    client, dev_headers, created_ids
) -> None:
    task_id = _insert_task(
        org_id=ORG_A, status="completed", completed_at=datetime.now(UTC)
    )
    created_ids.append(task_id)
    suspicion_id = _insert_suspicion(org_id=ORG_A, task_id=task_id)

    response = client.patch(
        f"/api/v1/affiliation/suspicions/{suspicion_id}",
        json={"status": "confirmed"},
        headers=dev_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["reviewed_by"] == dev_headers["X-Actor-Id"], "reviewed_by 必须落真值"

    # 已终态再复核 → 400（不允许把复核留痕改回去）
    second = client.patch(
        f"/api/v1/affiliation/suspicions/{suspicion_id}",
        json={"status": "dismissed"},
        headers=dev_headers,
    )
    assert second.status_code == 400, second.text


def test_review_cross_tenant_suspicion_is_403(client, dev_headers, created_ids) -> None:
    task_id = _insert_task(org_id=ORG_B)
    created_ids.append(task_id)
    suspicion_id = _insert_suspicion(org_id=ORG_B, task_id=task_id)

    response = client.patch(
        f"/api/v1/affiliation/suspicions/{suspicion_id}",
        json={"status": "confirmed"},
        headers=dev_headers,
    )

    assert response.status_code == 403, response.text
