from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class DatabaseSpec:
    id: str
    engine: str
    name: str
    managed: bool = False
    host: str | None = None
    port: int | None = None
    host_port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    root_password: str | None = None
    path: str | None = None
    volume: str | None = None
    container: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def env_prefix(self) -> str:
        if not self.host:
            raise ValueError("env_prefix requires a host/service name")
        return self.host.upper().replace("-", "_")

    @property
    def auth(self) -> bool:
        return bool(self.password)

    def with_options(self, options: dict[str, Any]) -> DatabaseSpec:
        return replace(self, options=dict(options))
