from __future__ import annotations

import secrets
from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import DbEngine
from services.ports import PortAllocator


class MongoEngine(DbEngine):
    key, display, default_port = "mongodb", "MongoDB", 27017
    template = "engines/mongodb.yml.j2"
    auth_variants = True

    def option_fields(self) -> list[Field]:
        return [
            Field(
                "auth_source",
                "Auth source",
                "text",
                default="",
                help=(
                    "Authentication database, set as authSource on the URI. Leave "
                    "empty to use admin when credentials are provided. Override if "
                    "your user is defined in another database."
                ),
            ),
            Field(
                "replica_set",
                "Replica set",
                "text",
                default="",
                help=(
                    "Replica set name, set as replicaSet on the URI. Required to "
                    "connect to a self-hosted replica set."
                ),
            ),
            Field(
                "tls",
                "Force TLS?",
                "bool",
                default=False,
                help="When enabled, adds tls=true to the URI to force a TLS connection.",
            ),
        ]

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
            options=dict(answers.get("options", {})),
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        prefix = spec.env_prefix
        out = {
            f"{prefix}_PORT": str(spec.host_port),
            f"{prefix}_DB": spec.database or "",
        }
        if spec.auth:
            out[f"{prefix}_USER"] = spec.username or ""
            out[f"{prefix}_PASS"] = spec.password or ""
        return out
