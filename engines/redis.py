from __future__ import annotations

import secrets
from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import DbEngine
from services.ports import PortAllocator


class RedisEngine(DbEngine):
    key, display, default_port = "redis", "Redis", 6379
    template = "engines/redis.yml.j2"
    auth_variants = True

    def fields_existing(self) -> list[Field]:
        return [
            Field("host", "Host", "text", default="localhost"),
            Field("port", "Port", "int", default=self.default_port),
            Field("database", "Database index", "text", default="0"),
            Field("username", "Username (empty if none)", "text", default=""),
            Field("password", "Password (empty if none)", "text", default=""),
        ]

    def generate(
        self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]
    ) -> DatabaseSpec:
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=f"redis_{secrets.token_hex(4)}",
            managed=True,
            host=self.service_name("redis", auth),
            port=self.default_port,
            host_port=ports.free(),
            database="0",
            username="",
            password=generate_password(16) if auth else None,
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        prefix = spec.env_prefix
        out = {f"{prefix}_PORT": str(spec.host_port)}
        if spec.auth:
            out[f"{prefix}_PASS"] = spec.password or ""
        return out

    def agent_database(self, spec: DatabaseSpec) -> str:
        return spec.database or "0"
