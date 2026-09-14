from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from commands.base import Command
from commands.db import report_write
from core.errors import ValidationError
from services.project import (
    ENV_FILE,
    AgentProject,
    DashboardProject,
    detect_kind,
)
from services.renderer import ComposeRenderer, RenderResult
from services.telemetry import Telemetry
from services.templates import TemplateRepository
from ui import UI


class BuildCommand(Command):
    name = "build"
    help = "Re-render docker-compose.yml from the component's configuration."
    panel = "Configuration"
    no_args_is_help = True

    def __init__(
        self,
        ui: UI,
        telemetry: Telemetry,
        templates: TemplateRepository,
        renderer: ComposeRenderer,
    ) -> None:
        super().__init__(ui, telemetry)
        self.templates = templates
        self.renderer = renderer

    def run(
        self,
        path: Annotated[Path, typer.Argument(help="Component folder")],
        diff: Annotated[
            bool, typer.Option("--diff", help="Show the diff, write nothing")
        ] = False,
        stdout: Annotated[
            bool, typer.Option("--stdout", help="Print the compose, write nothing")
        ] = False,
        inline_env: Annotated[
            bool,
            typer.Option(
                "--inline-env", help="Substitute values instead of ${VAR} references"
            ),
        ] = False,
        output: Annotated[
            Path | None,
            typer.Option("--output", "-o", help="Write files to another directory"),
        ] = None,
    ) -> None:
        if sum([diff, stdout, output is not None]) > 1:
            raise ValidationError("Use only one of --diff, --stdout, --output.")
        path = self.require_project_dir(path)
        self.templates.resolve()
        kind = detect_kind(path)

        if kind == "agent":
            agent = AgentProject.load(path)
            result: RenderResult = self.renderer.render_agent(agent, inline=inline_env)
        else:
            dashboard = DashboardProject.load(path)
            result = self.renderer.render_dashboard(dashboard, inline=inline_env)
        result.validate()

        if inline_env and not stdout:
            self.ui.warning(
                "--inline-env writes secrets in clear text into the compose file."
            )

        if stdout:
            self.ui.out(result.compose)
            return
        if diff:
            self.ui.diff(result.diff_against(path))
            return

        target = (output or path).resolve()
        if output is not None:
            target.mkdir(parents=True, exist_ok=True)
            (target / ENV_FILE).write_text(
                (path / ENV_FILE).read_text(encoding="utf-8"), encoding="utf-8"
            )
        report = result.write(target)
        report_write(self.ui, report)
        self.ui.success(
            f"Rendered {', '.join(path.name for path in report.wrote)} in {target}"
        )
        if kind == "agent" and output is None:
            self.ui.info(f"Restart to apply: portabase restart {path.name}")
