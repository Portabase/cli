from __future__ import annotations

from typing import Any

from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import StandardSqlEngine
from services.ports import PortAllocator


class FirebirdEngine(StandardSqlEngine):
    key, display, default_port = "firebird", "Firebird", 3050
    template, slug, db_prefix = "engines/firebird.yml.j2", "firebird", "fb"
    DATA_DIR = "/var/lib/firebird/data"

    def generate(
        self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]
    ) -> DatabaseSpec:
        db_file = "mirror.fdb"
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=db_file,
            managed=True,
            host=self.service_name(self.slug),
            port=self.default_port,
            host_port=ports.free(),
            database=f"{self.DATA_DIR}/{db_file}",
            username="alice",
            password=generate_password(16),
            root_password=generate_password(16),
        )

    @staticmethod
    def _file_name(spec: DatabaseSpec) -> str:
        return (spec.database or "").rsplit("/", 1)[-1]

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        base = super().env_vars(spec)
        base[f"{spec.env_prefix}_DB"] = self._file_name(spec)
        base[f"{spec.env_prefix}_ROOT_PASS"] = spec.root_password or ""
        return base

    def template_ctx(
        self, spec: DatabaseSpec, *, inline: bool = False
    ) -> dict[str, Any]:
        ctx = super().template_ctx(spec, inline=inline)
        ctx["db_var"] = self.var(spec, "DB", self._file_name(spec), inline)
        ctx["root_password_var"] = self.var(
            spec, "ROOT_PASS", spec.root_password, inline
        )
        return ctx
