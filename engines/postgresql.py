from __future__ import annotations

from typing import Any

from core.errors import ValidationError
from core.fields import Field
from core.specs import DatabaseSpec
from engines.base import StandardSqlEngine
from services.ports import PortAllocator

# Physical restores write a data directory into RESTORE_PATH on the agent.
RESTORE_MOUNT = ("./restores", "/restores")


def physical_only(answers: dict[str, Any]) -> bool:
    return answers.get("method") == "physical"


def at_least_one_day(value: int) -> int:
    if value < 1:
        raise ValidationError("full_every_days must be at least 1.")
    return value


class PostgresEngine(StandardSqlEngine):
    key, display, default_port = "postgresql", "PostgreSQL", 5432
    template, slug, db_prefix = "engines/postgresql.yml.j2", "pg", "pg"

    def option_fields(self) -> list[Field]:
        return [
            Field(
                "keep_ownership",
                "Keep ownership?",
                "bool",
                default=False,
                help=(
                    "When enabled, omits --no-owner and --no-privileges from the dump. "
                    "Ownership and role assignments are preserved. By default these "
                    "flags are applied to keep restores portable across users and "
                    "environments."
                ),
            ),
            Field(
                "clean_mode",
                "Clean mode",
                "choice",
                default="clean",
                choices=("clean", "none", "drop_schemas", "drop_database"),
                help=(
                    "How the target database is cleaned before a restore. clean: "
                    "pg_restore --clean --if-exists. none: no pre-clean. drop_schemas: "
                    "drop every non-system schema CASCADE (works on managed Postgres). "
                    "drop_database: DROP DATABASE + CREATE DATABASE — requires CREATEDB "
                    "or superuser; most managed providers do not allow it."
                ),
            ),
            Field(
                "exclude_tables",
                "Exclude tables",
                "list",
                default=[],
                help=(
                    "Comma-separated pg_dump patterns (--exclude-table), e.g. "
                    "public.search_index__*. Leave empty to dump every table. "
                    "Excluded tables are dropped on restore with drop_schemas or "
                    "drop_database. Requires Agent 1.23.0+."
                ),
            ),
            Field(
                "exclude_schemas",
                "Exclude schemas",
                "list",
                default=[],
                help=(
                    "Comma-separated pg_dump patterns (--exclude-schema). Leave empty "
                    "to dump every schema. Requires Agent 1.23.0+."
                ),
            ),
        ]


class PostgresClusterEngine(StandardSqlEngine):
    key, display, default_port = "postgresql-cluster", "PostgreSQL Cluster", 5432
    template, slug, db_prefix = "engines/postgresql-cluster.yml.j2", "pg", "pg"
    warning = (
        "Postgres Cluster with the archive method uses pg_dumpall, which dumps all "
        "databases and global objects (roles, tablespaces): the user must be a "
        "Postgres superuser. The physical method needs PostgreSQL 17+, a role "
        "with REPLICATION, a pg_hba.conf replication line and summarize_wal = on."
    )

    def option_fields(self) -> list[Field]:
        return [
            Field(
                "method",
                "Backup method",
                "choice",
                default="archive",
                choices=("archive", "physical"),
                help=(
                    "archive: pg_dumpall of every database (default). physical: "
                    "pg_basebackup of the whole cluster, a full backup then "
                    "incrementals holding only the changed blocks (PostgreSQL 17+). Restores rebuild "
                    "a data directory in ./restores on the agent host. Requires "
                    "Agent 1.27.0+ and Dashboard 1.37.0+. Cannot be changed later."
                ),
            ),
            Field(
                "full_every_days",
                "Start a new full backup every N days",
                "int",
                default=7,
                validator=at_least_one_day,
                when=physical_only,
                help="The next backup is a new full once the chain's full is this old.",
            ),
        ]

    @staticmethod
    def mount_for(spec: DatabaseSpec) -> tuple[str, str] | None:
        return RESTORE_MOUNT if physical_only(spec.options) else None

    def generate(
        self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]
    ) -> DatabaseSpec:
        if physical_only(answers.get("options", {})):
            # ponytail: a managed container would need summarize_wal and a
            # replication pg_hba.conf line; refuse until someone asks for it.
            raise ValidationError(
                "The physical method needs a server set up for replication, so it "
                "only works on an existing database.",
                hint="Use --mode existing, or the archive method for a new database.",
            )
        return super().generate(auth=auth, ports=ports, answers=answers)
