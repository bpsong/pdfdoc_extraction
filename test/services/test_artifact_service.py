import logging
from unittest.mock import Mock

import modules.services.artifact_service as artifact_service


def test_registration_logs_non_sensitive_warning_on_database_failure(
    tmp_path,
    monkeypatch,
    caplog,
):
    connect = Mock(side_effect=OSError("SECRET database location"))
    monkeypatch.setattr(artifact_service, "connect", connect)
    caplog.set_level(logging.WARNING, logger=artifact_service.__name__)

    result = artifact_service.register_document_artifact(
        Mock(),
        {"document_id": "document-1"},
        file_type="export_json",
        file_path=tmp_path / "secret-customer-name.json",
    )

    assert result is None
    assert "document_id=document-1" in caplog.text
    assert "file_type=export_json" in caplog.text
    assert "error_type=OSError" in caplog.text
    assert "secret-customer-name" not in caplog.text
    assert "SECRET database location" not in caplog.text
