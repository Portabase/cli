from __future__ import annotations

from typing import Any

from core.fields import Field
from core.specs import DatabaseSpec
from engines.base import DbEngine
from services.ports import PortAllocator


class DockerVolumeEngine(DbEngine):
    key, display = "docker-volume", "Docker Volume"
    template = None
    has_modes = False
    label_default = "Docker Volume"
    warning = (
        "Requires the Docker socket. It will be mounted on the agent "
        "(/var/run/docker.sock)."
    )

    def fields_existing(self) -> list[Field]:
        return [
            Field("volume", "Volume Name (e.g. databases_sqlite-data)", "text"),
            Field(
                "container",
                "Container Name (optional, enables auto-restart after restore)",
                "text",
                default="",
            ),
        ]

    def fields_new(self) -> list[Field]:
        return self.fields_existing()

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
            volume=str(answers["volume"]).strip(),
            container=(str(answers.get("container") or "").strip() or None),
        )

    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]:
        return {}

    def agent_entry(self, spec: DatabaseSpec) -> dict[str, Any]:
        entry = {
            "name": spec.name,
            "type": self.key,
            "volume_name": spec.volume,
            "generated_id": spec.id,
        }
        if spec.container:
            entry["container_name"] = spec.container
        return entry

    def describe(self, spec: DatabaseSpec) -> str:
        return f"volume: {spec.volume}"
