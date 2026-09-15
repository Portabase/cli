from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from commands.base import Command, CommandGroup
from commands.flows.add_database import AddDatabaseFlow
from engines import EngineRegistry
from services.docker import DockerRunner
from services.ports import PortAllocator
from services.project import AgentProject
from services.renderer import ComposeRenderer, WriteReport
from services.telemetry import Telemetry
from services.templates import TemplateRepository
from ui import UI

NameArg = Annotated[Path, typer.Argument(help="Agent folder")]


def report_write(ui: UI, report: WriteReport) -> None:
    if report.backed_up:
        ui.warning(
            f"Legacy compose backed up to {report.backed_up.name}. "
            "Manual edits belong in docker-compose.override.yml."
        )


class _DbCommand(Command):
    panel = "Configuration"
    no_args_is_help = True

    def __init__(
        self,
        ui: UI,
        telemetry: Telemetry,
        engines: EngineRegistry,
        ports: PortAllocator,
        templates: TemplateRepository,
        renderer: ComposeRenderer,
        docker: DockerRunner,
    ) -> None:
        super().__init__(ui, telemetry)
        self.engines = engines
        self.ports = ports
        self.templates = templates
        self.renderer = renderer
        self.docker = docker

    def render_and_write(self, project: AgentProject) -> None:
        with self.ui.status("Rendering configuration..."):
            result = self.renderer.render_agent(project)
            project.save_state()
            report = result.write(project.path)
        report_write(self.ui, report)


class DbAddCommand(_DbCommand):
    name, help = "add", "Add a database to an agent."

    def run(
        self,
        name: NameArg,
        engine: Annotated[
            str | None, typer.Option("--engine", "-e", help="Database engine")
        ] = None,
        mode: Annotated[
            str | None, typer.Option("--mode", help="new (container) or existing")
        ] = None,
        auth: Annotated[
            bool | None,
            typer.Option(
                "--auth/--no-auth", help="Auth variant for mongodb/redis/valkey"
            ),
        ] = None,
        label: Annotated[
            str | None, typer.Option("--label", help="Display name")
        ] = None,
        host: Annotated[
            str | None, typer.Option("--host", help="Host of an existing database")
        ] = None,
        port: Annotated[
            int | None,
            typer.Option("--port", help="Port of an existing database"),
        ] = None,
        database: Annotated[
            str | None, typer.Option("--database", help="Database name")
        ] = None,
        user: Annotated[str | None, typer.Option("--user", help="Username")] = None,
        password: Annotated[
            str | None, typer.Option("--password", help="Prefer --password-stdin")
        ] = None,
        password_stdin: Annotated[
            bool, typer.Option("--password-stdin", help="Read password from stdin")
        ] = False,
        path: Annotated[
            str | None, typer.Option("--path", help="SQLite file path (existing)")
        ] = None,
        db_name: Annotated[
            str | None, typer.Option("--name", help="SQLite file name (new)")
        ] = None,
        volume: Annotated[
            str | None, typer.Option("--volume", help="Docker volume name")
        ] = None,
        container: Annotated[
            str | None,
            typer.Option("--container", help="Container to restart after restore"),
        ] = None,
        option: Annotated[
            list[str] | None,
            typer.Option("--option", "-o", help="Engine option KEY=VALUE (repeatable)"),
        ] = None,
    ) -> None:
        if password_stdin:
            password = sys.stdin.readline().rstrip("\n")
        elif password is not None:
            self.ui.warning(
                "--password is visible in shell history; prefer --password-stdin."
            )

        project_path = self.require_project_dir(name)
        self.templates.resolve()
        project = AgentProject.load(project_path)

        flow = AddDatabaseFlow(self.ui, self.engines, self.ports)
        values = {
            "engine": engine,
            "mode": mode,
            "auth": auth,
            "label": label,
            "host": host,
            "port": port,
            "database": database,
            "username": user,
            "password": password,
            "path": path,
            "name": db_name,
            "volume": volume,
            "container": container,
            "options": flow.parse_options(option),
        }
        spec, eng = flow.collect(values)
        flow.apply(project, spec, eng)
        self.render_and_write(project)

        self.ui.success(
            f"Added {eng.display} database '{spec.name}' ({eng.describe(spec)})."
        )
        self.ui.info(
            f"Restart the agent to apply changes: portabase restart {project_path.name}"
        )


class DbRemoveCommand(_DbCommand):
    name, help = "remove", "Remove a database from an agent."

    def run(
        self,
        name: NameArg,
        target: Annotated[
            str | None,
            typer.Option(
                "--id", "--name", "-i", help="Database id (or prefix) or display name"
            ),
        ] = None,
        purge_volume: Annotated[
            bool,
            typer.Option(
                "--purge-volume",
                help="Also delete the Docker volume of a managed database",
            ),
        ] = False,
        yes: Annotated[
            bool, typer.Option("--yes", "-y", help="Skip confirmation")
        ] = False,
    ) -> None:
        project_path = self.require_project_dir(name)
        self.templates.resolve()
        project = AgentProject.load(project_path)
        if not project.databases:
            self.ui.warning("No databases to remove.")
            return

        if target is None:
            choices = [
                f"{database.name} ({database.engine}) [{database.id[:8]}]"
                for database in project.databases
            ]
            picked = self.ui.form().choice(
                "Which database to remove?", choices, name="id"
            )
            spec = project.databases[choices.index(picked)]
        else:
            spec = project.find(target)
        engine = self.engines.get(spec.engine)

        if not yes:
            extra = " and its Docker volume" if (purge_volume and spec.managed) else ""
            self.confirm_or_abort(
                f"Remove '{spec.name}' ({engine.describe(spec)}){extra}?", default=False
            )

        project.remove(spec, engine)
        self.render_and_write(project)
        self.ui.success(f"Removed {spec.name}")

        if spec.managed:
            volume_name = f"{self.docker.project_name(project_path)}_{spec.host}-data"
            if purge_volume:
                self.require_docker(self.docker)
                removed = self.docker.remove_volume(volume_name)
                self.ui.success(
                    f"Deleted volume {volume_name}"
                    if removed
                    else f"Volume {volume_name} did not exist"
                )
            else:
                self.ui.info(
                    f"Data volume kept: {volume_name}. "
                    f"Delete it with: docker volume rm {volume_name}"
                )
        self.ui.info(
            f"Restart the agent to apply changes: portabase restart {project_path.name}"
        )


class DbListCommand(_DbCommand):
    name, help = "list", "List an agent's databases."

    def run(self, name: NameArg) -> None:
        project = AgentProject.load(self.require_project_dir(name))
        if not project.databases:
            self.ui.warning("No databases configured.")
            return
        rows = []
        for database in project.databases:
            engine = self.engines.get(database.engine)
            opts = ", ".join(
                f"{key}={value}"
                for key, value in engine.non_default_options(database).items()
            )
            user = (
                "N/A"
                if database.engine in ("sqlite", "docker-volume")
                else (database.username or "")
            )
            rows.append(
                [
                    database.name,
                    database.database or "",
                    database.engine,
                    engine.describe(database),
                    user,
                    opts,
                    database.id[:8] + "...",
                ]
            )
        self.ui.table(
            ["Display Name", "Database", "Type", "Host:Port", "User", "Options", "ID"],
            rows,
            title=f"Databases for {project.path.name}",
        )


class DbCommands(CommandGroup):
    name, help, panel = "db", "Manage an agent's databases.", "Components"

    def __init__(
        self,
        ui: UI,
        telemetry: Telemetry,
        engines: EngineRegistry,
        ports: PortAllocator,
        templates: TemplateRepository,
        renderer: ComposeRenderer,
        docker: DockerRunner,
    ) -> None:
        super().__init__(ui, telemetry)
        self._deps = (ui, telemetry, engines, ports, templates, renderer, docker)

    @property
    def commands(self) -> list[Command]:
        return [
            DbAddCommand(*self._deps),
            DbRemoveCommand(*self._deps),
            DbListCommand(*self._deps),
        ]
