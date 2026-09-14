from __future__ import annotations

from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from engines.base import DbEngine
from services.ports import PortAllocator

CONFIG_DIR = "/config"


class SqliteEngine(DbEngine):
    key, display = "sqlite", "SQLite"
    template = None
    auth_variants = False

    def fields_existing(self) -> list[Field]:
        return [Field("path", "Database Path (relative or absolute)", "text")]

    def fields_new(self) -> list[Field]:
        return [Field("name", "Database Name", "text", default="local")]

    def generate(
        self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]
    ) -> DatabaseSpec:
        name = str(answers.get("name") or "local")
        if not name.endswith(".sqlite"):
            name += ".sqlite"
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=name,
            managed=False,
            path=name,
            database=f"{CONFIG_DIR}/{name}",
        )

    def from_existing(self, answers: dict[str, Any]) -> DatabaseSpec:
        raw = str(answers["path"])
        absolute = raw.startswith("/")
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=answers.get("label") or self.label_default,
            managed=False,
            path=raw,
            database=raw if absolute else f"{CONFIG_DIR}/{raw}",
        )

    @staticmethod
    def mount_for(spec: DatabaseSpec) -> tuple[str, str] | None:
        if spec.database and spec.database.startswith(f"{CONFIG_DIR}/"):
            rel = spec.database[len(CONFIG_DIR) + 1 :]
            return (f"./{rel}", spec.database)
        return None

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        return {}

    def agent_entry(self, spec: DatabaseSpec) -> dict[str, Any]:
        return {
            "name": spec.name,
            "database": spec.database,
            "type": self.key,
            "generated_id": spec.id,
        }

    def describe(self, spec: DatabaseSpec) -> str:
        return "Local File"
