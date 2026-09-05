"""Direct branch tests for small SQLite repository guard clauses."""

from unittest.mock import Mock

import pytest

from modules.db.repositories import (
    AuditRepository,
    BatchRepository,
    ConfigVersionRepository,
    DocumentRepository,
    PipelineTemplateRepository,
    ReviewRepository,
    ReviewLockConflictError,
    UserRepository,
    WatchFolderBindingRepository,
)


def _connection() -> Mock:
    connection = Mock()
    connection.in_transaction = False
    return connection


def test_user_batch_and_document_repository_guards() -> None:
    connection = _connection()
    users = UserRepository(connection)
    with pytest.raises(ValueError, match="Exactly admin"):
        users.initialize({"admin": "hash"})

    connection.execute.return_value.fetchone.return_value = (1,)
    users.initialize({"admin": "a", "operator": "o"}, overwrite=True)
    connection.execute.assert_any_call("DELETE FROM users")

    with pytest.raises(ValueError, match="Unknown fixed user"):
        users.update_password("unknown", "hash")
    cursor = Mock(rowcount=0)
    connection.execute.return_value = cursor
    with pytest.raises(ValueError, match="not initialized"):
        users.update_password("admin", "hash")

    batches = BatchRepository(connection)
    batches.update_status("batch", "processing")
    connection.execute.return_value = Mock(
        fetchone=Mock(return_value={"total": 0, "completed": 0, "failed": 0, "queued": 0})
    )
    assert batches.recompute_counts("batch") is not None

    documents = DocumentRepository(connection)
    connection.execute.return_value.fetchone.return_value = None
    assert documents.delete_pending_child("document") is False


def test_review_repository_filters_and_lock_conflicts() -> None:
    connection = _connection()
    connection.execute.return_value.fetchall.return_value = []
    reviews = ReviewRepository(connection)
    assert reviews.list_queue(status="pending", queue_name="invoices") == []

    cursor = Mock(rowcount=0)
    connection.execute.side_effect = [cursor, Mock(fetchone=Mock(return_value=None))]
    with pytest.raises(ReviewLockConflictError, match="no longer available"):
        reviews.claim("review", "operator")

    connection.execute.side_effect = [
        Mock(rowcount=0),
        Mock(fetchone=Mock(return_value={"status": "pending"})),
    ]
    with pytest.raises(ReviewLockConflictError, match="locked"):
        reviews.claim("review", "other")

    connection.execute.side_effect = None
    connection.execute.return_value = Mock()
    reviews.delete_lock("review")


def test_config_template_and_watch_binding_repository_branches() -> None:
    connection = _connection()
    versions = ConfigVersionRepository(connection)
    connection.execute.return_value.fetchone.return_value = None
    assert versions.publish("missing") is None

    templates = PipelineTemplateRepository(connection)
    with pytest.raises(ValueError, match="Unsupported template fields"):
        templates.update("template", unsupported=True)
    connection.execute.return_value.fetchone.return_value = {"id": "template"}
    assert templates.update("template", operator_selectable=True)["id"] == "template"

    bindings = WatchFolderBindingRepository(connection)
    connection.execute.return_value.fetchall.return_value = [{"id": "binding"}]
    assert bindings.list_enabled() == [{"id": "binding"}]
    connection.execute.return_value.fetchone.return_value = {"id": 1}
    assert bindings.has_enabled_for_template("template") is True

    query, values = AuditRepository._admin_event_query(
        event_type="admin_update",
        user="operator",
        created_from="2026-01-01",
        created_to="2026-02-01",
    )
    assert "created_at <= ?" in query
    assert values == ["admin_update", "operator", "2026-01-01", "2026-02-01"]
