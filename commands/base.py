from __future__ import annotations

import functools
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

import typer

from core.errors import ConfigError, DockerError, UserAbort
from services.docker import DockerRunner
from services.telemetry import Telemetry
from ui import UI


class Command(ABC):
    name: str
    help: str
    panel: str = "General"
    no_args_is_help: bool = False

    def __init__(self, ui: UI, telemetry: Telemetry) -> None:
        self.ui = ui
        self.telemetry = telemetry

    def register(self, app: typer.Typer) -> None:
        app.command(
            self.name,
            help=self.help,
            rich_help_panel=self.panel,
            no_args_is_help=self.no_args_is_help,
        )(self._traced(self.run))

    def _traced(self, fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with self.telemetry.span(f"command.{self.name}"):
                return fn(*args, **kwargs)

        return wrapper

    @abstractmethod
    def run(self, *args, **kwargs) -> None: ...

    def require_docker(self, docker: DockerRunner) -> None:
        if not docker.available():
            raise DockerError(
                "Docker not found (binary missing).",
                hint="Install Docker: https://docs.docker.com/get-docker/",
            )
        if docker.daemon_running():
            return
        self.ui.warning("Docker is installed but the daemon is not running.")
        if self.ui.confirm("Do you want to try starting Docker?", default=False):
            with self.ui.status("Waiting for Docker to start..."):
                started = docker.start_daemon()
            if started:
                self.ui.success("Docker started successfully.")
                return
        raise DockerError(
            "Docker is required to continue.",
            hint="Start the Docker daemon and retry.",
        )

    @staticmethod
    def require_project_dir(path: Path) -> Path:
        path = path.resolve()
        if not (path / "docker-compose.yml").exists():
            raise ConfigError(
                f"No Portabase configuration found in: {path}",
                hint=(
                    "Expected a docker-compose.yml created by "
                    "'portabase agent' or 'portabase dashboard'."
                ),
            )
        return path

    def confirm_or_abort(
        self, question: str, *, default: bool = False, value: bool | None = None
    ) -> None:
        if not self.ui.confirm(question, default=default, value=value):
            raise UserAbort()


class CommandGroup(ABC):
    name: str
    help: str
    panel: str = "General"

    def __init__(self, ui: UI, telemetry: Telemetry) -> None:
        self.ui = ui
        self.telemetry = telemetry

    @property
    @abstractmethod
    def commands(self) -> list[Command]: ...

    def build_typer(self) -> typer.Typer:
        sub = typer.Typer(help=self.help, no_args_is_help=True)
        for cmd in self.commands:
            cmd.register(sub)
        return sub

    def register(self, app: typer.Typer) -> None:
        app.add_typer(self.build_typer(), name=self.name, rich_help_panel=self.panel)
