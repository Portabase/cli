from __future__ import annotations

import secrets
from typing import Any

from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import DbEngine
from services.ports import PortAllocator


class MongoEngine(DbEngine):
    key, display, default_port = "mongodb", "MongoDB", 27017
    template = "engines/mongodb.yml.j2"
    auth_variants = True

    def generate(
        self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]
    ) -> DatabaseSpec:
        db_name = f"mongo_{secrets.token_hex(4)}"
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=db_name,
            managed=True,
            host=self.service_name("mongo", auth),
            port=self.default_port,
            host_port=ports.free(),
            database=db_name,
            username="admin" if auth else "",
            password=generate_password(16) if auth else None,
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        p = spec.env_prefix
        out = {f"{p}_PORT": str(spec.host_port), f"{p}_DB": spec.database or ""}
        if spec.auth:
            out[f"{p}_USER"] = spec.username or ""
            out[f"{p}_PASS"] = spec.password or ""
        return out
