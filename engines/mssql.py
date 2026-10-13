from __future__ import annotations

from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import StandardSqlEngine
from services.ports import PortAllocator


class MssqlEngine(StandardSqlEngine):
    key, display, default_port = "mssql", "Microsoft SQL Server", 1433
    template, slug, db_prefix = "engines/mssql.yml.j2", "mssql", "master"

    def option_fields(self) -> list[Field]:
        return [
            Field(
                "backup_format",
                "Backup format",
                "choice",
                default="dacpac",
                choices=("dacpac", "bacpac"),
                help=(
                    "dacpac: sqlpackage Extract with all table data (default, works "
                    "with Windows principals). bacpac: sqlpackage Export, validated "
                    "against Azure SQL rules; fails with SQL71627 on databases holding "
                    "Windows principals such as NT AUTHORITY\\SYSTEM. Requires agent "
                    "1.22.0 or later."
                ),
            ),
        ]

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
        prefix = spec.env_prefix
        return {
            f"{prefix}_PORT": str(spec.host_port),
            f"{prefix}_PASS": spec.password or "",
        }
