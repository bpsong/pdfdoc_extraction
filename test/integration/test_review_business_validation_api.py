"""HTTP contracts for business validation on authenticated extraction reviews."""

from contextlib import closing

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import modules.api_router as api_router
from modules.db.connection import connect
from modules.services.startup_migration_service import initialize_database
from test.helpers_business_validation import seed_business_review
from test.helpers_sqlite import TempConfig


@pytest.fixture
def api(tmp_path, monkeypatch):
    config = TempConfig(tmp_path / "state.sqlite3")
    initialize_database(config)
    seeded = seed_business_review(config, tmp_path)
    seeded["task"].run(seeded["context"])
    monkeypatch.setattr(api_router, "get_dependencies", lambda: (config, None, None, None, None))
    app = FastAPI()
    app.include_router(api_router.build_router())
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    with TestClient(app) as client:
        yield client, f"/api/review/items/{seeded['context']['review_item_id']}", config, app


def test_revalidate_draft_and_completion_http_contract(api, monkeypatch):
    client, url, config, _ = api
    monkeypatch.setattr("modules.resume_manager.ResumeManager.resume_document", lambda *_args, **_kwargs: False)
    assert client.post(url + "/claim", json={}).status_code == 200
    loaded = client.get(url).json()
    token = loaded["review_revision"]
    assert loaded["business_validation"]["has_blocking_findings"]
    assert client.post(url + "/revalidate", json={}).json()["detail"]["code"] == "review_revision_required"
    request = {"expected_revision": token, "request_revision": 8, "corrections": {"subtotal": 300}}
    result = client.post(url + "/revalidate", json=request)
    assert result.status_code == 200
    assert result.json()["request_revision"] == 8
    assert not result.json()["business_validation"]["has_blocking_findings"]
    saved = client.post(url + "/draft", json=request)
    assert saved.status_code == 200
    assert not saved.json()["business_validation"]["has_blocking_findings"]
    stale = client.post(url + "/complete", json=request)
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_review"
    token = saved.json()["review_revision"]
    blocked = client.post(url + "/complete", json={"expected_revision": token, "corrections": {}})
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["business_validation"]["has_blocking_findings"]
    accepted = client.post(url + "/complete", json={**request, "expected_revision": token})
    assert accepted.status_code == 200 and accepted.json()["status"] == "completed"
    assert client.post(url + "/revalidate", json=request).status_code == 409


@pytest.mark.parametrize("body", [[], "text", None])
def test_revalidate_rejects_nonobject_json(api, body):
    client, url, _, _ = api
    response = client.post(url + "/revalidate", content=__import__("json").dumps(body),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 400


def test_revalidate_requires_auth_and_csrf_for_browser_session(api):
    client, url, _, app = api
    app.dependency_overrides.pop(api_router.get_current_user)
    assert client.post(url + "/revalidate", json={}).status_code == 401
    app.dependency_overrides[api_router.get_current_user] = lambda: "operator"
    client.cookies.set("access_token", "synthetic-session")
    client.cookies.set("csrf_token", "synthetic-csrf")
    assert client.post(url + "/revalidate", json={}).status_code == 403
    assert client.post(url + "/revalidate", json={}, headers={"x-csrf-token": "wrong"}).status_code == 403
    assert client.post(url + "/claim", json={}, headers={"x-csrf-token": "synthetic-csrf"}).status_code == 200
    token = client.get(url).json()["review_revision"]
    assert client.post(url + "/revalidate", json={"expected_revision": token},
                       headers={"x-csrf-token": "synthetic-csrf"}).status_code == 200


def test_revalidate_rejects_wrong_owner_and_manual_split(api):
    client, url, config, app = api
    client.post(url + "/claim", json={})
    token = client.get(url).json()["review_revision"]
    app.dependency_overrides[api_router.get_current_user] = lambda: "other"
    assert client.post(url + "/revalidate", json={"expected_revision": token}).status_code == 409
    with closing(connect(config)) as conn:
        conn.execute("UPDATE review_items SET review_kind='manual_split'")
        conn.commit()
    assert "manual split" in client.post(url + "/revalidate", json={}).json()["detail"]
