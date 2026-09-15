from __future__ import annotations

from core.fields import Field
from engines.base import StandardSqlEngine


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
        ]


class PostgresClusterEngine(StandardSqlEngine):
    key, display, default_port = "postgresql-cluster", "PostgreSQL Cluster", 5432
    template, slug, db_prefix = "engines/postgresql-cluster.yml.j2", "pg", "pg"
    warning = (
        "Postgres Cluster requires a superuser. Cluster backup/restore uses "
        "pg_dumpall, which dumps all databases and global objects (roles, "
        "tablespaces). The provided user must be a Postgres superuser."
    )
