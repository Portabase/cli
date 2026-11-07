from __future__ import annotations

from typing import Any

from core.errors import ValidationError
from core.fields import Field
from core.specs import DatabaseSpec
from core.utils import generate_password
from engines.base import StandardSqlEngine
from engines.files import host_dir
from services.ports import PortAllocator


def bak_only(answers: dict[str, Any]) -> bool:
    return answers.get("backup_format") == "bak"


def server_folder(value: str) -> str:
    folder = value.strip()
    if not folder:
        raise ValidationError(
            "bak_server_path is required: the shared folder as SQL Server sees it.",
            hint=r"-o bak_server_path=D:\PortabaseBackups",
        )
    return folder


def agent_folder(value: str) -> str:
    if not value.strip():
        raise ValidationError(
            "bak_agent_path is required: the same folder on the agent host.",
            hint="-o bak_agent_path=/mnt/sql-backups",
        )
    return host_dir(value)


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
                choices=("dacpac", "bacpac", "bak"),
                help=(
                    "dacpac: sqlpackage Extract with all table data (default, works "
                    "with Windows principals). bacpac: sqlpackage Export, validated "
                    "against Azure SQL rules; fails with SQL71627 on databases holding "
                    "Windows principals such as NT AUTHORITY\\SYSTEM. Requires agent "
                    "1.22.0 or later. bak: native BACKUP DATABASE into a folder shared "
                    "with SQL Server; for applications that reference other databases "
                    "or are written to during backups. Existing servers only, not "
                    "Azure SQL Database. Requires agent 1.26.0 or later."
                ),
            ),
            Field(
                "bak_server_path",
                "Shared folder as SQL Server sees it",
                "text",
                default="",
                validator=server_folder,
                when=bak_only,
                help=(
                    r"e.g. D:\PortabaseBackups or \\nas\sql-backups. The SQL Server "
                    "service account must be able to write there."
                ),
            ),
            Field(
                "bak_agent_path",
                "Same folder on the agent host (absolute)",
                "text",
                default="",
                validator=agent_folder,
                when=bak_only,
                help=(
                    "e.g. /mnt/sql-backups. Mounted into the agent at the same path. "
                    "The agent must be able to read, write and delete there."
                ),
            ),
            Field(
                "bak_verify",
                "Verify each backup with RESTORE VERIFYONLY?",
                "bool",
                default=False,
                when=bak_only,
                help="Reads the whole backup again on SQL Server after each run.",
            ),
        ]

    @staticmethod
    def mount_for(spec: DatabaseSpec) -> tuple[str, str] | None:
        path = spec.options.get("bak_agent_path")
        return (path, path) if path else None

    def generate(
        self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]
    ) -> DatabaseSpec:
        if bak_only(answers.get("options", {})):
            raise ValidationError(
                "bak needs a folder shared with SQL Server, so it only works on an "
                "existing database.",
                hint="Use --mode existing, or dacpac for a new database.",
            )
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
