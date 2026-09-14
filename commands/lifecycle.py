from __future__ import annotations

import contextlib
import shutil
from pathlib import Path
from typing import Annotated

import typer

from commands.base import Command
from services.docker import DockerRunner
from services.telemetry import Telemetry
from ui import UI

PathArg = Annotated[Path, typer.Argument(help="Path to the component folder")]


class _ComposeCommand(Command):
    panel = "Lifecycle"
    no_args_is_help = True
    verb: str
    compose_args: list[str]
    done: str

    def __init__(self, ui: UI, telemetry: Telemetry, docker: DockerRunner) -> None:
        super().__init__(ui, telemetry)
        self.docker = docker

    def run(self, path: PathArg) -> None:
        path = self.require_project_dir(path)
        self.require_docker(self.docker)
        with self.ui.status(f"{self.verb} {path.name}..."):
            self.docker.compose(path, self.compose_args)
        self.ui.success(self.done)


class StartCommand(_ComposeCommand):
    name, help = "start", "Start a Portabase component."
    verb, compose_args, done = "Starting", ["up", "-d"], "Started"


class StopCommand(_ComposeCommand):
    name, help = "stop", "Stop a Portabase component."
    verb, compose_args, done = "Stopping", ["stop"], "Stopped"


class RestartCommand(_ComposeCommand):
    name, help = "restart", "Restart a Portabase component, applying config changes."
    verb, compose_args, done = "Restarting", ["up", "-d"], "Restarted"

    def run(self, path: PathArg) -> None:
        path = self.require_project_dir(path)
        self.require_docker(self.docker)
        with self.ui.status(f"{self.verb} {path.name}..."):
            # `compose restart` neither creates services added since the last
            # start nor rereads env_file; `up -d` converges first.
            self.docker.compose(path, ["up", "-d"])
            self.docker.compose(path, ["restart"])
        self.ui.success(self.done)


class LogsCommand(Command):
    name, help, panel = "logs", "Show the logs of a Portabase component.", "Lifecycle"
    no_args_is_help = True

    def __init__(self, ui: UI, telemetry: Telemetry, docker: DockerRunner) -> None:
        super().__init__(ui, telemetry)
        self.docker = docker

    def run(
        self,
        path: PathArg,
        follow: Annotated[
            bool, typer.Option("--follow/--no-follow", "-f", help="Follow log output")
        ] = True,
    ) -> None:
        path = self.require_project_dir(path)
        self.require_docker(self.docker)
        args = ["logs", "-f"] if follow else ["logs"]
        with contextlib.suppress(KeyboardInterrupt):
            self.docker.compose(path, args, check=False)


class UninstallCommand(Command):
    name = "uninstall"
    help = "Uninstall and delete a Portabase component."
    panel = "Lifecycle"
    no_args_is_help = True

    def __init__(self, ui: UI, telemetry: Telemetry, docker: DockerRunner) -> None:
        super().__init__(ui, telemetry)
        self.docker = docker

    def run(
        self,
        path: PathArg,
        force: Annotated[
            bool, typer.Option("--force", "-f", help="Skip confirmation")
        ] = False,
    ) -> None:
        path = self.require_project_dir(path)
        self.require_docker(self.docker)
        if not force:
            self.ui.warning(
                f"This will delete containers, volumes and all data in {path}."
            )
            self.confirm_or_abort("Are you sure?", default=False)
        with self.ui.status("Uninstalling..."):
            self.docker.compose(path, ["down", "-v"])
            try:
                shutil.rmtree(path)
            except OSError as error:
                self.ui.warning(f"Could not remove directory: {error}")
        self.ui.success("Uninstalled")
