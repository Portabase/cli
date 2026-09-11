import os
import platform
import re
import sys
from dataclasses import dataclass
from typing import Annotated

import click
import typer

from commands.agent import AgentCommands
from commands.base import DeprecatedAlias
from commands.build import BuildCommand
from commands.config import ConfigCommands
from commands.dashboard import DashboardCommands
from commands.decrypt import DecryptCommand
from commands.lifecycle import (
    LogsCommand,
    RestartCommand,
    StartCommand,
    StopCommand,
    UninstallCommand,
)
from commands.update import UpdateCommand
from core.config import GlobalConfig
from core.errors import PortabaseError, UserAbort, ValidationError
from core.version import current_version
from engines import registry as engine_registry
from services.docker import DockerRunner
from services.http import HttpClient
from services.ports import PortAllocator
from services.renderer import ComposeRenderer
from services.telemetry import NoopTelemetry, Telemetry
from services.templates import TemplateRepository
from services.updater import UpdateChecker, Updater, is_frozen
from ui import UI


@dataclass
class Settings:
    non_interactive: bool = False
    verbose: bool = False
    no_color: bool = False

    @classmethod
    def from_env(cls, argv: list[str]) -> "Settings":
        env_flag = os.environ.get("PORTABASE_NON_INTERACTIVE", "").lower()
        settings = cls(
            non_interactive=env_flag in ("1", "true", "yes") or not sys.stdin.isatty(),
            no_color=bool(os.environ.get("NO_COLOR")) or "--no-color" in argv,
        )
        if settings.no_color:
            # Typer renders --help with its own Rich console, which only honors
            # the NO_COLOR convention; --help is handled before any callback runs.
            os.environ["NO_COLOR"] = "1"
        return settings


def build_app(
    ui: UI, telemetry: Telemetry, config: GlobalConfig, settings: Settings
) -> tuple[typer.Typer, UpdateChecker]:
    app = typer.Typer(
        no_args_is_help=True, add_completion=False, rich_markup_mode="rich"
    )
    http = HttpClient()
    docker = DockerRunner()
    version = current_version()
    checker = UpdateChecker(http, config, version)
    updater = Updater(http, version)
    templates = TemplateRepository.bundled()
    ports = PortAllocator()
    renderer = ComposeRenderer(templates, engine_registry, version)

    def version_callback(value: bool) -> None:
        if value:
            ui.print(f"Portabase CLI version: {version}")
            latest = checker.available(force=True)
            if latest:
                ui.warning(f"A new version is available: [bold]{latest}[/bold]")
            raise typer.Exit()

    @app.callback(
        help="Portabase CLI to manage agents, dashboards and databases.",
        invoke_without_command=True,
    )
    def root(
        ctx: typer.Context,
        _version: Annotated[
            bool | None,
            typer.Option(
                "--version",
                help="Show the version and exit.",
                callback=version_callback,
                is_eager=True,
            ),
        ] = None,
        verbose: Annotated[
            bool, typer.Option("--verbose", help="Show error causes and tracebacks.")
        ] = False,
        no_color: Annotated[
            bool, typer.Option("--no-color", help="Disable colors.")
        ] = False,
        non_interactive: Annotated[
            bool,
            typer.Option(
                "--non-interactive",
                envvar="PORTABASE_NON_INTERACTIVE",
                help="Never prompt; fail on missing input.",
            ),
        ] = False,
    ) -> None:
        settings.verbose = verbose
        settings.no_color = settings.no_color or no_color
        settings.non_interactive = settings.non_interactive or non_interactive
        ui.configure(
            verbose=settings.verbose,
            no_color=settings.no_color,
            non_interactive=settings.non_interactive,
        )
        if ctx.invoked_subcommand is None:
            ui.out(ctx.get_help() + "\n")
            raise typer.Exit()

    agent = AgentCommands(
        ui, telemetry, docker, templates, renderer, engine_registry, ports
    )
    commands = [
        StartCommand(ui, telemetry, docker),
        StopCommand(ui, telemetry, docker),
        RestartCommand(ui, telemetry, docker),
        LogsCommand(ui, telemetry, docker),
        UninstallCommand(ui, telemetry, docker),
        BuildCommand(ui, telemetry, templates, renderer),
        DecryptCommand(ui, telemetry),
        UpdateCommand(ui, telemetry, checker, updater),
    ]
    agent.register(app)
    DashboardCommands(ui, telemetry, docker, templates, renderer, ports).register(app)
    for cmd in commands:
        cmd.register(app)
    DeprecatedAlias(ui, telemetry, agent.db, name="db", use="agent db").register(app)
    ConfigCommands(ui, telemetry, config).register(app)
    return app, checker


def _usage_hint(error: click.UsageError) -> str:
    group = error.ctx.command.name if error.ctx and error.ctx.command else None
    match = re.match(r"No such command '(.+)'", error.format_message())
    if group in ("agent", "dashboard") and match:
        return f"Did you mean: portabase {group} create {match.group(1)}?"
    return "Run 'portabase --help' for usage."


def _notify_update(
    ui: UI, checker: UpdateChecker, settings: Settings, invoked: str | None
) -> None:
    if not is_frozen() or settings.non_interactive or invoked in ("update", None):
        return
    if "--stdout" in sys.argv:
        return
    latest = checker.available()
    if latest:
        ui.print("")
        ui.warning(
            f"A new version of Portabase CLI is available: [bold]{latest}[/bold] "
            f"(current: {checker.current})"
        )
        ui.info("Run [bold]portabase update[/bold] to update.")


def main() -> None:
    settings = Settings.from_env(sys.argv[1:])
    config = GlobalConfig()
    ui = UI(non_interactive=settings.non_interactive, no_color=settings.no_color)
    telemetry = NoopTelemetry()
    app, checker = build_app(ui, telemetry, config, settings)
    invoked = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    exit_code = 0

    try:
        with telemetry.session(cli_version=current_version(), os=platform.system()):
            result = app(standalone_mode=False)
            if isinstance(result, int):
                exit_code = result
    except UserAbort as e:
        ui.warning(e.message)
        telemetry.event("abort")
        exit_code = e.exit_code
    except PortabaseError as e:
        ui.error(e)
        telemetry.error(e)
        exit_code = e.exit_code
    except click.exceptions.NoArgsIsHelpError:
        exit_code = 0
    except click.exceptions.Exit as e:
        exit_code = e.exit_code
    except click.UsageError as e:
        err = ValidationError(e.format_message(), hint=_usage_hint(e))
        ui.error(err)
        telemetry.error(err)
        exit_code = err.exit_code
    except KeyboardInterrupt:
        ui.print("")
        ui.warning("Canceled.")
        exit_code = 130
    except Exception as e:  # noqa: BLE001 — last resort: a bug, not an expected error
        wrapped = PortabaseError("Unexpected error: " + str(e), cause=e)
        ui.error(wrapped, unexpected=True)
        telemetry.error(e, unexpected=True)
        exit_code = 1
    finally:
        telemetry.flush()

    if exit_code == 0:
        _notify_update(ui, checker, settings, invoked)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
