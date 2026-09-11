from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from commands.base import Command, CommandGroup
from commands.db import report_write
from core.errors import ValidationError
from services import dashboard_settings as ds
from services.docker import DockerRunner
from services.ports import PortAllocator
from services.project import AuthProvider, DashboardProject, ProviderKind
from services.renderer import ComposeRenderer
from services.telemetry import Telemetry
from services.templates import TemplateRepository
from ui import UI

PathArg = Annotated[Path, typer.Argument(help="Dashboard folder")]
KINDS: tuple[ProviderKind, ...] = ("oidc", "oauth")


class _AuthCommand(Command):
    panel = "Components"
    no_args_is_help = True

    def __init__(
        self,
        ui: UI,
        telemetry: Telemetry,
        docker: DockerRunner,
        templates: TemplateRepository,
        renderer: ComposeRenderer,
        ports: PortAllocator,
    ) -> None:
        super().__init__(ui, telemetry)
        self.templates = templates
        self.renderer = renderer

    def load(self, path: Path) -> DashboardProject:
        project_path = self.require_project_dir(path)
        self.templates.resolve()
        return DashboardProject.load(project_path)

    def write(self, project: DashboardProject) -> None:
        with self.ui.status("Rendering configuration..."):
            result = self.renderer.render_dashboard(project)
            project.save_state()
            report = result.write(project.path)
        report_write(self.ui, report)
        self.ui.info(f"Apply with: portabase restart {project.path.name}")


class AuthAddCommand(_AuthCommand):
    name, help = "add", "Add an OIDC or OAuth login provider."

    def run(
        self,
        path: PathArg,
        kind: Annotated[str, typer.Argument(help="oidc | oauth")],
        provider_id: Annotated[
            str,
            typer.Argument(
                help="Provider id: any slug for oidc, a known name for oauth "
                "(google, github, discord, apple, linkedin, x, reddit)"
            ),
        ],
        client: Annotated[
            str | None, typer.Option("--client", help="Client ID")
        ] = None,
        secret: Annotated[
            str | None,
            typer.Option("--secret", help="Client secret (prefer --secret-stdin)"),
        ] = None,
        secret_stdin: Annotated[
            bool,
            typer.Option("--secret-stdin", help="Read the client secret from stdin"),
        ] = False,
        issuer: Annotated[
            str | None, typer.Option("--issuer", help="OIDC issuer / discovery URL")
        ] = None,
        title: Annotated[
            str | None, typer.Option("--title", help="Display name")
        ] = None,
        scopes: Annotated[
            str | None, typer.Option("--scopes", help="OIDC scopes")
        ] = None,
        pkce: Annotated[
            bool | None, typer.Option("--pkce/--no-pkce", help="OIDC: use PKCE")
        ] = None,
        host: Annotated[
            str | None, typer.Option("--host", help="OIDC host override")
        ] = None,
    ) -> None:
        if kind not in KINDS:
            raise ValidationError(f"Unknown kind '{kind}'.", hint="Use oidc or oauth.")
        pid = ds.validate_provider_id(kind, provider_id)
        if secret_stdin:
            secret = sys.stdin.readline().rstrip("\n")
        elif secret is not None:
            self.ui.warning(
                "--secret is visible in shell history; prefer --secret-stdin."
            )

        values: dict[str, Any] = {
            "client": client,
            "secret": secret,
            "issuer": issuer,
            "title": title,
            "scopes": scopes,
            "pkce": pkce,
            "host": host,
        }
        fields = ds.OIDC_FIELDS if kind == "oidc" else ds.OAUTH_FIELDS
        allowed = {f.name for f in fields}
        stray = sorted(
            k for k, v in values.items() if v is not None and k not in allowed
        )
        if stray:
            flags = ", ".join("--" + k for k in stray)
            raise ValidationError(f"Not applicable to {kind}: {flags}.")

        project = self.load(path)
        answers = self.ui.form().collect(list(fields), values)
        provider = AuthProvider(kind=kind, id=pid, values=answers)
        project.add_provider(provider)
        self.write(project)
        self.ui.success(f"Added {kind} provider '{pid}'.")
        self.ui.info(
            f"Callback URL to register at the provider: {project.callback_url(pid)}"
        )


class AuthListCommand(_AuthCommand):
    name, help = "list", "List login providers."

    def run(self, path: PathArg) -> None:
        project = self.load(path)
        providers = project.providers
        if not providers:
            self.ui.warning("No login provider configured.")
            return
        self.ui.table(
            ["Kind", "Id", "Title", "Issuer / provider", "Callback"],
            [
                [
                    p.kind,
                    p.id,
                    p.values.get("title", ""),
                    p.values.get("issuer", p.id),
                    project.callback_url(p.id),
                ]
                for p in providers
            ],
            title=f"Login providers for {project.path.name}",
        )


class AuthRemoveCommand(_AuthCommand):
    name, help = "remove", "Remove a login provider."

    def run(
        self,
        path: PathArg,
        provider_id: Annotated[str, typer.Argument(help="Provider id")],
        yes: Annotated[
            bool, typer.Option("--yes", "-y", help="Skip confirmation")
        ] = False,
    ) -> None:
        project = self.load(path)
        if not yes:
            self.confirm_or_abort(
                f"Remove login provider '{provider_id}'?", default=False
            )
        removed = project.remove_provider(provider_id)
        self.write(project)
        self.ui.success(f"Removed {removed.kind} provider '{removed.id}'.")


class DashboardAuthCommands(CommandGroup):
    name, help, panel = "auth", "Manage a dashboard's login providers.", "Components"

    def __init__(
        self,
        ui: UI,
        telemetry: Telemetry,
        docker: DockerRunner,
        templates: TemplateRepository,
        renderer: ComposeRenderer,
        ports: PortAllocator,
    ) -> None:
        super().__init__(ui, telemetry)
        self._deps = (ui, telemetry, docker, templates, renderer, ports)

    @property
    def commands(self) -> list[Command]:
        return [
            AuthAddCommand(*self._deps),
            AuthListCommand(*self._deps),
            AuthRemoveCommand(*self._deps),
        ]
