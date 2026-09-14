from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from commands.base import Command, CommandGroup
from commands.db import report_write
from core.errors import ValidationError
from services import auth_providers as ap
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
        kind: Annotated[
            str | None, typer.Argument(help="oidc | oauth (asked if omitted)")
        ] = None,
        provider_id: Annotated[
            str | None,
            typer.Argument(
                help="Provider id: any slug for oidc, a known name for oauth "
                "(google, github, discord, apple, linkedin, x, reddit)"
            ),
        ] = None,
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
        form = self.ui.form()
        picked = form.choice("Provider kind", list(KINDS), value=kind, name="kind")
        provider_kind: ProviderKind = "oidc" if picked == "oidc" else "oauth"
        if provider_kind == "oauth":
            provider_id = form.choice(
                "OAuth provider", list(ap.OAUTH_PROVIDERS), value=provider_id, name="id"
            )
        else:
            provider_id = form.text(
                "Provider id (slug, e.g. keycloak)", value=provider_id, name="id"
            )
        pid = ap.validate_provider_id(provider_kind, provider_id)
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
        fields = ap.OIDC_FIELDS if provider_kind == "oidc" else ap.OAUTH_FIELDS
        allowed = {field.name for field in fields}
        stray = sorted(
            key
            for key, value in values.items()
            if value is not None and key not in allowed
        )
        if stray:
            flags = ", ".join("--" + name for name in stray)
            raise ValidationError(f"Not applicable to {provider_kind}: {flags}.")

        project = self.load(path)
        answers = form.collect(list(fields), values)
        provider = AuthProvider(kind=provider_kind, id=pid, values=answers)
        project.add_provider(provider)
        self.write(project)
        self.ui.success(f"Added {provider_kind} provider '{pid}'.")
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
                    provider.kind,
                    provider.id,
                    provider.values.get("title", ""),
                    provider.values.get("issuer", provider.id),
                    project.callback_url(provider.id),
                ]
                for provider in providers
            ],
            title=f"Login providers for {project.path.name}",
        )


class AuthRemoveCommand(_AuthCommand):
    name, help = "remove", "Remove a login provider."

    def run(
        self,
        path: PathArg,
        provider_id: Annotated[
            str | None, typer.Argument(help="Provider id (asked if omitted)")
        ] = None,
        yes: Annotated[
            bool, typer.Option("--yes", "-y", help="Skip confirmation")
        ] = False,
    ) -> None:
        project = self.load(path)
        if provider_id is None:
            providers = project.providers
            if not providers:
                self.ui.warning("No login provider to remove.")
                return
            choices = [f"{provider.id} ({provider.kind})" for provider in providers]
            picked = self.ui.form().choice(
                "Which provider to remove?", choices, name="id"
            )
            provider_id = providers[choices.index(picked)].id
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
