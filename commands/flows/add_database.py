from __future__ import annotations

from typing import Any

from core.errors import ValidationError
from core.fields import Field
from core.specs import DatabaseSpec
from engines import EngineRegistry
from engines.base import DbEngine
from services.ports import PortAllocator
from services.project import AgentProject
from ui import UI
from ui.form import Form

FLOW_KEYS = {"engine", "mode", "auth", "label", "options"}


class AddDatabaseFlow:
    def __init__(self, ui: UI, engines: EngineRegistry, ports: PortAllocator) -> None:
        self.ui = ui
        self.engines = engines
        self.ports = ports

    @staticmethod
    def parse_options(items: list[str] | None) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in items or []:
            if "=" not in item:
                raise ValidationError(
                    f"Invalid option '{item}'.", hint="Use -o KEY=VALUE"
                )
            key, value = item.split("=", 1)
            out[key.strip()] = value.strip()
        return out

    def collect(self, values: dict[str, Any]) -> tuple[DatabaseSpec, DbEngine]:
        form = self.ui.form()
        engine_key = form.choice(
            "Select Database Engine",
            self.engines.choices(),
            value=values.get("engine"),
            name="engine",
        )
        engine = self.engines.get(engine_key)
        if engine.warning:
            self.ui.warning(engine.warning)

        mode = "new"
        if engine.has_modes:
            mode = form.choice(
                "Configuration Mode",
                ["new", "existing"],
                value=values.get("mode"),
                default="new",
                name="mode",
            )

        fields = list(
            engine.fields_new() if mode == "new" else engine.fields_existing()
        )
        if mode == "existing" or not engine.has_modes:
            fields.insert(
                0, Field("label", "Display Name", "text", default=engine.label_default)
            )

        self._reject_irrelevant(values, fields, engine, mode)

        auth = True
        if mode == "new" and engine.auth_variants:
            raw = values.get("auth")
            if raw is None:
                picked = form.choice("Variant", ["with-auth", "no-auth"], name="auth")
                auth = picked == "with-auth"
            else:
                auth = bool(raw)

        if mode == "existing":
            self.ui.info(f"{engine.display} — existing database")
        answers = form.collect(fields, values)
        answers["options"] = self._collect_options(
            form, engine, values.get("options") or {}
        )

        if mode == "new":
            spec = engine.generate(auth=auth, ports=self.ports, answers=answers)
        else:
            spec = engine.from_existing(answers)
        return spec.with_options(answers["options"]), engine

    def apply(
        self, project: AgentProject, spec: DatabaseSpec, engine: DbEngine
    ) -> None:
        project.add(spec, engine)

    def _collect_options(
        self, form: Form, engine: DbEngine, provided: dict[str, str]
    ) -> dict[str, Any]:
        option_fields = engine.option_fields()
        known = {f.name for f in option_fields}
        unknown = set(provided) - known
        if unknown:
            raise ValidationError(
                f"Unknown option(s) for {engine.key}: {', '.join(sorted(unknown))}.",
                hint=(
                    ("Valid options: " + ", ".join(sorted(known)))
                    if known
                    else f"{engine.key} has no options."
                ),
            )
        if not option_fields:
            return {}
        return form.collect(option_fields, provided)

    @staticmethod
    def _reject_irrelevant(
        values: dict[str, Any], fields: list[Field], engine: DbEngine, mode: str
    ) -> None:
        relevant = {f.name for f in fields} | FLOW_KEYS
        extra = sorted(
            k for k, v in values.items() if v is not None and k not in relevant
        )
        if not extra:
            return
        flags = ", ".join("--" + k.replace("_", "-") for k in extra)
        applicable = ", ".join("--" + f.name.replace("_", "-") for f in fields)
        raise ValidationError(
            f"Option(s) not applicable to {engine.key} in '{mode}' mode: {flags}.",
            hint=f"Applicable: {applicable}"
            if applicable
            else "No extra input needed.",
        )
