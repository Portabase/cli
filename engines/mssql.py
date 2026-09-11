from __future__ import annotations

from typing import Any

from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import StandardSqlEngine
from services.ports import PortAllocator


class MssqlEngine(StandardSqlEngine):
    key, display, default_port = "mssql", "Microsoft SQL Server", 1433
    template, slug, db_prefix = "engines/mssql.yml.j2", "mssql", "master"

    def generate(
        self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]
    ) -> DatabaseSpec:
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name="MSSQL",
            managed=True,
            host=self.service_name(self.slug),
            port=self.default_port,
            host_port=ports.free(),
            database="master",
            username="sa",
            password=generate_password(16),
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        p = spec.env_prefix
        return {f"{p}_PORT": str(spec.host_port), f"{p}_PASS": spec.password or ""}
