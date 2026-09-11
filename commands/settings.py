from __future__ import annotations

import inspect
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Protocol

import typer

from commands.base import Command
from commands.db import report_write
from core.errors import ValidationError
from services import settings as cfg
from services.renderer import RenderResult
from services.telemetry import Telemetry
from services.templates import TemplateRepository
from ui import UI


class SettingsProject(Protocol):
    path: Path
    registry: cfg.Registry

    def setting(self, name: str) -> Any: ...
    def settings(self) -> dict[str, Any]: ...
    def set(self, name: str, value: Any) -> None: ...
    def unset(self, name: str) -> None: ...
    def save_state(self) -> None: ...


def flag_of(name: str) -> str:
    return "--" + name.replace("_", "-")


def settings_parameters(registry: cfg.Registry) -> list[inspect.Parameter]:
    params: list[inspect.Parameter] = []
    for setting in registry:
        field = setting.field
        flag = flag_of(setting.name)
        if field.kind == "bool":
            ann: Any = Annotated[
                bool | None, typer.Option(f"{flag}/--no-{flag[2:]}", help=field.prompt)
            ]
        elif field.kind == "int":
            ann = Annotated[int | None, typer.Option(flag, help=field.prompt)]
        else:
            note = " (prefer the -stdin variant)" if setting.secret else ""
            ann = Annotated[str | None, typer.Option(flag, help=field.prompt + note)]
        params.append(
            inspect.Parameter(
                setting.name,
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=ann,
            )
        )
        if setting.secret:
            params.append(
                inspect.Parameter(
                    f"{setting.name}_stdin",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=False,
                    annotation=Annotated[
                        bool,
                        typer.Option(
                            f"{flag}-stdin",
                            help=f"Read {field.prompt.lower()} from stdin",
                        ),
                    ],
                )
            )
    return params


def with_settings_flags(
    run: Callable[..., None], registry: cfg.Registry
) -> Callable[..., None]:
    def entry(*args: Any, **kwargs: Any) -> None:
        run(*args, **kwargs)

    static = [
        p
        for p in inspect.signature(run, eval_str=True).parameters.values()
        if p.kind is not inspect.Parameter.VAR_KEYWORD
    ]
    signature = inspect.Signature(static + settings_parameters(registry))
    entry.__signature__ = signature  # type: ignore[attr-defined]
    entry.__annotations__ = {
        name: param.annotation for name, param in signature.parameters.items()
    }
    return entry


def read_secret_flags(registry: cfg.Registry, values: dict[str, Any]) -> dict[str, Any]:
    out = dict(values)
    for setting in registry:
        if setting.secret and out.pop(f"{setting.name}_stdin", False):
            out[setting.name] = sys.stdin.readline().rstrip("\n")
    return out


def display(setting: cfg.Setting, value: Any) -> str:
    if setting.secret:
        return "••••••••"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def apply_settings(ui: UI, project: SettingsProject, values: dict[str, Any]) -> None:
    form = ui.form()
    for name, raw in values.items():
        if raw is not None:
            project.set(name, form.ask(project.registry.get(name).field, raw))


def show_settings(ui: UI, project: SettingsProject) -> None:
    values = project.settings()
    for section, title in project.registry.sections.items():
        rows = [
            (s.field.prompt, display(s, values[s.name]))
            for s in project.registry.in_section(section)
            if values[s.name] not in (None, "")
        ]
        if rows:
            ui.summary(rows, title=title.upper())


class _SettingsCommand(Command):
    panel = "Components"
    no_args_is_help = True

    def __init__(
        self,
        ui: UI,
        telemetry: Telemetry,
        templates: TemplateRepository,
        load: Callable[[Path], SettingsProject],
        render: Callable[[Any], RenderResult],
    ) -> None:
        super().__init__(ui, telemetry)
        self.templates = templates
        self._load = load
        self._render = render

    def load(self, path: Path) -> SettingsProject:
        project_path = self.require_project_dir(path)
        self.templates.resolve()
        return self._load(project_path)

    def write(self, project: SettingsProject) -> None:
        with self.ui.status("Rendering configuration..."):
            result = self._render(project)
            project.save_state()
            report = result.write(project.path)
        report_write(self.ui, report)
        self.ui.info(f"Apply with: portabase restart {project.path.name}")


class SetCommand(_SettingsCommand):
    name, help = "set", "Change settings: KEY VALUE [KEY VALUE ...]."

    def run(
        self,
        path: Annotated[Path, typer.Argument(help="Component folder")],
        pairs: Annotated[
            list[str], typer.Argument(help="KEY VALUE pairs; keys as in 'show'")
        ],
    ) -> None:
        project = self.load(path)
        if len(pairs) % 2:
            raise ValidationError(
                "Expected KEY VALUE pairs.",
                hint="Known keys: " + ", ".join(project.registry.names()),
            )
        apply_settings(
            self.ui, project, dict(zip(pairs[::2], pairs[1::2], strict=True))
        )
        self.write(project)
        for key in pairs[::2]:
            self.ui.success(
                f"{key} = {display(project.registry.get(key), project.setting(key))}"
            )


class UnsetCommand(_SettingsCommand):
    name, help = "unset", "Reset settings to their default: KEY [KEY ...]."

    def run(
        self,
        path: Annotated[Path, typer.Argument(help="Component folder")],
        keys: Annotated[list[str], typer.Argument(help="Setting keys")],
    ) -> None:
        project = self.load(path)
        for key in keys:
            project.unset(key)
        self.write(project)
        self.ui.success("Reset: " + ", ".join(keys))
