from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from commands.base import Command, CommandGroup
from commands.db import DbCommands, report_write
from commands.flows.add_database import AddDatabaseFlow
from commands.settings import (
    SetCommand,
    UnsetCommand,
    apply_settings,
    display,
    read_secret_flags,
    show_settings,
    with_settings_flags,
)
from engines import EngineRegistry
from services import settings as cfg
from services.docker import DockerRunner
from services.ports import PortAllocator
from services.project import AgentProject
from services.renderer import ComposeRenderer
from services.telemetry import Telemetry
from services.templates import TemplateRepository
from ui import UI

NETWORK = "portabase_network"


class AgentCreateCommand(Command):
    name, help, panel = "create", "Create a new Portabase Agent instance.", "Components"
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

    def register(self, app: typer.Typer) -> None:
        app.command(
            self.name, help=self.help, rich_help_panel=self.panel, no_args_is_help=True
        )(self._traced(with_settings_flags(self.run, cfg.AGENT)))

    def run(
        self,
        name: Annotated[str, typer.Argument(help="Agent name (creates a folder)")],
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
        **settings: Any,
    ) -> None:
        self.ui.banner()
        self.require_docker(self.docker)
        self.docker.ensure_network(NETWORK)
        self.templates.resolve()

        path = Path(name).resolve()
        if path.exists() and not force:
            self.ui.warning(f"Directory '{name}' already exists.")
            self.confirm_or_abort("Overwrite?", default=False)

        provided = read_secret_flags(cfg.AGENT, settings)
        form = self.ui.form()
        answers = {
            s.name: form.ask(s.field, provided.get(s.name)) for s in cfg.AGENT if s.core
        }
        env_vars = {
            s.env: s.to_env(answers[s.name]) for s in cfg.AGENT if s.core and s.env
        }
        gateway = bool(answers["host_gateway"])

        rows = [("Agent Name", name), ("Path", str(path))]
        rows += [
            (s.field.prompt, display(s, answers[s.name])) for s in cfg.AGENT if s.core
        ]
        rows.append(("Files to Create", "docker-compose.yml, .env, databases.json"))
        self.ui.summary(rows, title="SUMMARY")
        if not yes:
            self.confirm_or_abort(
                "Apply this configuration and generate files?", default=True
            )

        project = AgentProject.create(path, env_vars, host_gateway=gateway)
        apply_settings(
            self.ui,
            project,
            {k: v for k, v in provided.items() if not cfg.AGENT.get(k).core},
        )
        self._write(project)
        self.ui.success(f"Agent '{name}' created in {path}")

        if self.ui.non_interactive:
            self.ui.hint(
                f"Add databases with: portabase agent db add {name} "
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


class AgentShowCommand(Command):
    name, help, panel = "show", "Show an agent's settings and databases.", "Components"
    no_args_is_help = True

    def __init__(self, ui: UI, telemetry: Telemetry, engines: EngineRegistry) -> None:
        super().__init__(ui, telemetry)
        self.engines = engines

    def run(self, path: Annotated[Path, typer.Argument(help="Agent folder")]) -> None:
        project = AgentProject.load(self.require_project_dir(path))
        show_settings(self.ui, project)
        if project.databases:
            rows = [
                [d.name, d.engine, self.engines.get(d.engine).describe(d)]
                for d in project.databases
            ]
            self.ui.table(["Name", "Engine", "Where"], rows, title="DATABASES")
        else:
            self.ui.hint("No database yet: portabase agent db add")


class AgentCommands(CommandGroup):
    name, help, panel = "agent", "Create and manage Portabase agents.", "Components"

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
        self._create = AgentCreateCommand(
            ui, telemetry, docker, templates, renderer, engines, ports
        )
        self._templates, self._renderer, self._engines = templates, renderer, engines
        self.db = DbCommands(ui, telemetry, engines, ports, templates, renderer, docker)

    @property
    def commands(self) -> list[Command]:
        shared = (
            self.ui,
            self.telemetry,
            self._templates,
            AgentProject.load,
            self._renderer.render_agent,
        )
        return [
            self._create,
            AgentShowCommand(self.ui, self.telemetry, self._engines),
            SetCommand(*shared),
            UnsetCommand(*shared),
        ]

    @property
    def groups(self) -> list[CommandGroup]:
        return [self.db]
