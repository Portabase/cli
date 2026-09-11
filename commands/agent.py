from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from commands.base import Command
from commands.db import report_write
from commands.flows.add_database import AddDatabaseFlow
from core.errors import ValidationError
from core.utils import validate_edge_key
from engines import EngineRegistry
from services.docker import DockerRunner
from services.ports import PortAllocator
from services.project import AgentProject
from services.renderer import ComposeRenderer
from services.telemetry import Telemetry
from services.templates import TemplateRepository
from ui import UI

NETWORK = "portabase_network"


def _edge_key(value: str) -> str:
    if not validate_edge_key(value):
        raise ValidationError(
            "Invalid Edge Key.",
            hint="Expected Base64 or JSON with serverUrl, agentId, masterKeyB64.",
        )
    return value


class AgentCommand(Command):
    name, help, panel = "agent", "Create a new Portabase Agent instance.", "Creation"
    no_args_is_help = True

    def __init__(
        self,
        ui: UI,
        telemetry: Telemetry,
        docker: DockerRunner,
        templates: TemplateRepository,
        renderer: ComposeRenderer,
        engines: EngineRegistry,
        ports: PortAllocator,
    ) -> None:
        super().__init__(ui, telemetry)
        self.docker = docker
        self.templates = templates
        self.renderer = renderer
        self.engines = engines
        self.ports = ports

    def run(
        self,
        name: Annotated[str, typer.Argument(help="Agent name (creates a folder)")],
        key: Annotated[str | None, typer.Option("--key", "-k", help="Edge Key")] = None,
        tz: Annotated[str | None, typer.Option("--tz", help="Timezone")] = None,
        polling: Annotated[
            int | None, typer.Option("--polling", help="Polling frequency in seconds")
        ] = None,
        host_gateway: Annotated[
            bool | None,
            typer.Option(
                "--host-gateway/--no-host-gateway",
                help="Map localhost to host-gateway",
            ),
        ] = None,
        start: Annotated[
            bool, typer.Option("--start", "-s", help="Start immediately")
        ] = False,
        force: Annotated[
            bool, typer.Option("--force", "-f", help="Overwrite an existing folder")
        ] = False,
        yes: Annotated[
            bool,
            typer.Option("--yes", "-y", help="Skip the configuration confirmation"),
        ] = False,
    ) -> None:
        self.ui.banner()
        self.require_docker(self.docker)
        self.docker.ensure_network(NETWORK)
        self.templates.resolve()

        path = Path(name).resolve()
        if path.exists() and not force:
            self.ui.warning(f"Directory '{name}' already exists.")
            self.confirm_or_abort("Overwrite?", default=False)

        form = self.ui.form()
        env_vars = {
            "EDGE_KEY": form.text(
                "Edge Key", value=key, validator=_edge_key, name="key"
            ),
            "TZ": form.text("Timezone", value=tz, default="UTC", name="tz"),
            "POLLING": str(
                form.integer(
                    "Polling frequency (seconds)",
                    value=polling,
                    default=5,
                    name="polling",
                )
            ),
            "LOG_LEVEL": "info",
        }
        gateway = form.confirm(
            "Add extra_hosts mapping (localhost -> host-gateway)?",
            value=host_gateway,
            default=False,
            name="host_gateway",
        )

        self.ui.summary(
            [
                ("Agent Name", name),
                ("Path", str(path)),
                ("Edge Key", env_vars["EDGE_KEY"]),
                ("Timezone", env_vars["TZ"]),
                ("Polling", f"{env_vars['POLLING']}s"),
                ("Host Gateway", "Yes" if gateway else "No"),
                ("Files to Create", "docker-compose.yml, .env, databases.json"),
            ],
            title="SUMMARY",
        )
        if not yes:
            self.confirm_or_abort(
                "Apply this configuration and generate files?", default=True
            )

        project = AgentProject.create(path, env_vars, host_gateway=gateway)
        self._write(project)
        self.ui.success(f"Agent '{name}' created in {path}")

        if self.ui.non_interactive:
            self.ui.hint(
                f"Add databases with: portabase db add {name} "
                "--engine postgresql --mode new"
            )
        else:
            self.ui.section("Database Setup")
            flow = AddDatabaseFlow(self.ui, self.engines, self.ports)
            while self.ui.confirm("Add a database?", default=True):
                spec, engine = flow.collect({})
                flow.apply(project, spec, engine)
                self._write(project)
                self.ui.success(
                    f"Added {engine.display} '{spec.name}' ({engine.describe(spec)})"
                )

        if start or (
            not self.ui.non_interactive
            and self.ui.confirm("Start agent now?", default=False)
        ):
            with self.ui.status("Starting agent..."):
                self.docker.compose(path, ["up", "-d"])
            self.ui.success("Agent started.")
        else:
            self.ui.info(f"Run: portabase start {name}")

    def _write(self, project: AgentProject) -> None:
        with self.ui.status("Rendering configuration..."):
            result = self.renderer.render_agent(project)
            project.save_state()
            report = result.write(project.path)
        report_write(self.ui, report)
