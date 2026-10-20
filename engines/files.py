from __future__ import annotations

import posixpath
from typing import Any

from core.errors import ValidationError
from core.fields import Field
from core.specs import DatabaseSpec
from engines.base import DbEngine
from services.ports import PortAllocator

DATA_DIR = "/data"


def host_dir(value: str) -> str:
    path = posixpath.normpath(str(value).strip())
    if not path.startswith("/") or not path.strip("/"):
        raise ValidationError(
            f"Path must be an absolute directory other than /, got {value!r}",
            hint="e.g. /srv/uploads",
        )
    if any(char in path for char in ":#\n"):
        raise ValidationError(
            f"Path cannot contain ':', '#' or a newline, got {value!r}",
            hint="They break the Docker Compose bind mount.",
        )
    return path


def no_braces(patterns: list[str]) -> list[str]:
    if any("{" in pattern or "}" in pattern for pattern in patterns):
        raise ValidationError(
            "Brace alternation ({a,b}) is not supported in exclude patterns.",
            hint="List each pattern separately: *.log,*.tmp",
        )
    return patterns


class FilesEngine(DbEngine):
    key, display = "files", "Files"
    template = None
    has_modes = False
    label_default = "Files"
    warning = (
        f"The directory is mounted read-write under {DATA_DIR}: a restore replaces "
        "its content (excluded paths are kept). Requires Agent 1.24.0+."
    )

    def fields_existing(self) -> list[Field]:
        return [
            Field(
                "path",
                "Directory on the host (absolute, e.g. /srv/uploads)",
                "text",
                validator=host_dir,
            )
        ]

    def fields_new(self) -> list[Field]:
        return self.fields_existing()

    def option_fields(self) -> list[Field]:
        return [
            Field(
                "method",
                "Backup method",
                "choice",
                default="archive",
                choices=("archive", "snapshot", "sync"),
                help=(
                    "archive: a tar.gz archive per run. snapshot: incremental, "
                    "deduplicated restic snapshots. sync: mirrors the directory onto "
                    "each storage; deletions propagate and it cannot be restored from "
                    "Portabase. Cannot be changed once the source exists."
                ),
            ),
            Field(
                "exclude",
                "Exclude patterns",
                "list",
                default=[],
                validator=no_braces,
                help=(
                    "Comma-separated patterns, e.g. node_modules,*.tmp,/cache. Without "
                    "a leading / a pattern matches at any depth; with one it is "
                    "relative to the directory. Excluded paths are kept on restore."
                ),
            ),
            Field(
                "one_file_system",
                "Stay on one file system?",
                "bool",
                default=False,
                help="Skip mount points found inside the directory.",
            ),
        ]

    def generate(
        self, *, auth: bool, ports: PortAllocator, answers: dict[str, Any]
    ) -> DatabaseSpec:
        return self.from_existing(answers)

    def from_existing(self, answers: dict[str, Any]) -> DatabaseSpec:
        return DatabaseSpec(
            id=self.new_id(),
            engine=self.key,
            name=answers.get("label") or self.label_default,
            managed=False,
            path=DATA_DIR + answers["path"],
        )

    @staticmethod
    def mount_for(spec: DatabaseSpec) -> tuple[str, str] | None:
        if spec.path and spec.path.startswith(f"{DATA_DIR}/"):
            return (spec.path[len(DATA_DIR) :], spec.path)
        return None

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        return {}

    def agent_entry(self, spec: DatabaseSpec) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "name": spec.name,
            "type": self.key,
            "path": spec.path,
            "generated_id": spec.id,
        }
        options = self.non_default_options(spec)
        if options:
            entry["options"] = options
        return entry

    def describe(self, spec: DatabaseSpec) -> str:
        mount = self.mount_for(spec)
        return f"dir: {mount[0] if mount else spec.path}"
