"""Application dependencies remain isolated across requests and app instances."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api_router import get_dependencies
from modules.request_dependencies import ApplicationDependenciesMiddleware, active_dependencies


def test_each_app_reuses_its_own_dependencies(monkeypatch) -> None:
    import modules.api_router as api

    def unexpected_load(*args, **kwargs):
        raise AssertionError("Request attempted to reload deployment YAML")

    monkeypatch.setattr(api, "ConfigManager", unexpected_load)

    def app_for(name: str) -> FastAPI:
        app = FastAPI()
        dependencies = ({"name": name}, object(), None, object(), object())
        app.add_middleware(ApplicationDependenciesMiddleware, dependencies=dependencies)

        @app.get("/test")
        def show() -> dict[str, str]:
            assert get_dependencies() is dependencies
            return get_dependencies()[0]

        return app

    with TestClient(app_for("first")) as first, TestClient(app_for("second")) as second:
        for _ in range(2):
            assert first.get("/test").json() == {"name": "first"}
            assert second.get("/test").json() == {"name": "second"}
    assert active_dependencies.get() is None
