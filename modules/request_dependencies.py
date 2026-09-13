"""Bind an application's startup dependencies to each request context."""

from contextvars import ContextVar
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send


active_dependencies: ContextVar[tuple[Any, ...] | None] = ContextVar(
    "active_dependencies", default=None
)


class ApplicationDependenciesMiddleware:
    """Share one dependency set within an app, including synchronous handlers."""

    def __init__(self, app: ASGIApp, dependencies: tuple[Any, ...]) -> None:
        self.app = app
        self.dependencies = dependencies

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = active_dependencies.set(self.dependencies)
        try:
            await self.app(scope, receive, send)
        finally:
            active_dependencies.reset(token)
