from __future__ import annotations

import secrets
import sys
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import typer

from commands.auth import DashboardAuthCommands
from commands.base import Command, CommandGroup
from commands.db import report_write
from commands.settings import (
    SetCommand,
    UnsetCommand,
    apply_settings,
    display,
    read_secret_flags,
    show_settings,
    with_settings_flags,
)
from core.utils import generate_password, slugify_project_name
from services import settings as cfg
from services.docker import DockerRunner
from services.envfile import EnvFile
from services.ports import PortAllocator
from services.project import DashboardProject
from services.renderer import ComposeRenderer
from services.telemetry import Telemetry
from services.templates import TemplateRepository
from ui import UI
from ui.form import Form

DB_MODES = ("external", "internal", "custom")
MODE_LABELS = {
    "external": "Dedicated Docker Container (Recommended)",
    "internal": "Embedded Database (In-container)",
    "custom": "Custom/Existing Database",
}
PathArg = Annotated[Path, typer.Argument(help="Dashboard folder")]


class _DashboardCommand(Command):
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
        self.docker = docker
        self.templates = templates
        self.renderer = renderer
        self.ports = ports

    def write(self, project: DashboardProject) -> None:
        with self.ui.status("Rendering configuration..."):
            result = self.renderer.render_dashboard(project)
            project.save_state()
            report = result.write(project.path)
        report_write(self.ui, report)


class DashboardCreateCommand(_DashboardCommand):
    name, help = "create", "Create a new Portabase Dashboard instance."

    def register(self, app: typer.Typer) -> None:
        app.command(
            self.name, help=self.help, rich_help_panel=self.panel, no_args_is_help=True
        )(self._traced(with_settings_flags(self.run, cfg.DASHBOARD)))

    def run(
        self,
        name: Annotated[str, typer.Argument(help="Dashboard name (creates a folder)")],
        port: Annotated[int | None, typer.Option("--port", help="Web port")] = None,
        db_mode: Annotated[
            str | None, typer.Option("--db-mode", help="external | internal | custom")
        ] = None,
        db_host: Annotated[
            str | None, typer.Option("--db-host", help="Host of the existing database")
        ] = None,
        db_port: Annotated[
            int | None, typer.Option("--db-port", help="Port of the existing database")
        ] = None,
        db_name: Annotated[
            str | None, typer.Option("--db-name", help="Database name")
        ] = None,
        db_user: Annotated[
            str | None, typer.Option("--db-user", help="Username")
        ] = None,
        db_password_stdin: Annotated[
            bool,
            typer.Option(
                "--db-password-stdin", help="Read the custom DB password from stdin"
            ),
        ] = False,
        tz: Annotated[str | None, typer.Option("--tz", help="Timezone")] = None,
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
        self.templates.resolve()

        path = Path(name).resolve()
        if path.exists() and not force:
            self.ui.warning(f"Directory '{name}' already exists.")
            self.confirm_or_abort("Overwrite?", default=False)

        form = self.ui.form()
        web_port = form.integer("Web Port", value=port, default=8887, name="port")
        mode = form.choice(
            "Database Setup",
            list(DB_MODES),
            value=db_mode,
            default="external",
            name="db_mode",
        )
        project_name = slugify_project_name(path.name)

        env_vars = {
            "HOST_PORT": str(web_port),
            "PROJECT_SECRET": secrets.token_hex(32),
            "PROJECT_URL": f"http://localhost:{web_port}",
            "PROJECT_NAME": project_name,
            "TZ": form.text("Timezone", value=tz, default="Europe/Paris", name="tz"),
            "LOG_LEVEL": "info",
        }
        rows = [
            ("Dashboard Name", name),
            ("Path", str(path)),
            ("Database Setup", MODE_LABELS[mode]),
        ]

        if mode == "external":
            pg_pass, pg_port = generate_password(16), self.ports.free()
            env_vars.update(
                self._pg_env("portabase", "portabase", pg_pass, "db", 5432, pg_port)
            )
            rows.append(("Internal Port", str(pg_port)))
        elif mode == "custom":
            self.ui.info("External Database Configuration")
            host = form.text("Host", value=db_host, default="localhost", name="db_host")
            dport = form.integer("Port", value=db_port, default=5432, name="db_port")
            dbname = form.text(
                "Database Name", value=db_name, default="portabase", name="db_name"
            )
            user = form.text("Username", value=db_user, name="db_user")
            if db_password_stdin:
                password = sys.stdin.readline().rstrip("\n")
            else:
                password = form.secret("Password", name="db_password")
            env_vars.update(self._pg_env(dbname, user, password, host, dport, dport))
            rows += [
                ("DB Host", host),
                ("DB Name", dbname),
                ("Connection URL", env_vars["DATABASE_URL"]),
            ]

        env = EnvFile(path / ".env")
        env.merge(env_vars)
        project = DashboardProject(path, env)

        provided = read_secret_flags(cfg.DASHBOARD, settings)
        apply_settings(self.ui, project, provided)
        explicit = any(value is not None for value in provided.values())
        if (
            not self.ui.non_interactive
            and not explicit
            and self.ui.confirm(
                "Configure API, MCP and authentication now?", default=False
            )
        ):
            self._wizard(form, project)

        rows.append(("Access URL", project.setting("url")))
        rows += [
            (setting.field.prompt, display(setting, project.setting(setting.name)))
            for setting in cfg.DASHBOARD
            if setting.name != "url" and project.env.get(setting.env or "") is not None
        ]
        rows.append(("Files to Create", "docker-compose.yml, .env"))
        self.ui.summary(rows, title="SUMMARY")
        if not yes:
            self.confirm_or_abort(
                "Apply this configuration and generate files?", default=True
            )

        path.mkdir(parents=True, exist_ok=True)
        self.write(project)
        self.ui.success(f"Dashboard '{name}' created in {path}")

        if start or (
            not self.ui.non_interactive
            and self.ui.confirm("Start dashboard now?", default=False)
        ):
            with self.ui.status("Starting..."):
                self.docker.compose(path, ["up", "-d"])
            self.ui.success(f"Live at: {project.setting('url')}")
        else:
            self.ui.info(f"Run: portabase start {name}")

        self.ui.print("")
        self.ui.hint("Single sign-on (OIDC / OAuth) can be added at any time:")
        self.ui.hint(f"  portabase dashboard set {name} url https://your.domain")
        self.ui.hint(
            f"  portabase dashboard auth add {name} oidc keycloak --issuer URL ..."
        )
        self.ui.hint(
            f"  portabase dashboard auth add {name} oauth github --client ID ..."
        )

    def _wizard(self, form: Form, project: DashboardProject) -> None:
        for section, names in cfg.DASHBOARD_WIZARD:
            self.ui.section(cfg.DASHBOARD.sections[section])
            for setting_name in names:
                needs_account = (
                    section == "onboarding" and setting_name != "skip_onboarding"
                )
                if needs_account and not project.setting("skip_onboarding"):
                    continue
                setting = cfg.DASHBOARD.get(setting_name)
                value = form.ask(setting.field)
                if value != setting.field.default or needs_account:
                    project.set(setting_name, value)

    @staticmethod
    def _pg_env(
        db: str, user: str, password: str, host: str, port: int, host_port: int
    ) -> dict[str, str]:
        url = (
            f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
            f"@{host}:{port}/{db}?schema=public"
        )
        return {
            "POSTGRES_DB": db,
            "POSTGRES_USER": user,
            "POSTGRES_PASSWORD": password,
            "POSTGRES_HOST": host,
            "DATABASE_URL": url,
            "PG_PORT": str(host_port),
        }


class DashboardShowCommand(_DashboardCommand):
    name, help = "show", "Show a dashboard's settings and login providers."

    def run(self, path: PathArg) -> None:
        project = DashboardProject.load(self.require_project_dir(path))
        show_settings(self.ui, project)
        providers = project.providers
        if providers:
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
                title="LOGIN PROVIDERS",
            )
        else:
            state = "enabled." if project.setting("password_auth") else "disabled!"
            self.ui.hint(f"No login provider. Password login is {state}")


class DashboardCommands(CommandGroup):
    name, help, panel = (
        "dashboard",
        "Create and manage Portabase dashboards.",
        "Components",
    )

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
        self.auth = DashboardAuthCommands(*self._deps)

    @property
    def commands(self) -> list[Command]:
        ui, telemetry, _docker, templates, renderer, _ports = self._deps
        shared = (
            ui,
            telemetry,
            templates,
            DashboardProject.load,
            renderer.render_dashboard,
        )
        return [
            DashboardCreateCommand(*self._deps),
            DashboardShowCommand(*self._deps),
            SetCommand(*shared),
            UnsetCommand(*shared),
        ]

    @property
    def groups(self) -> list[CommandGroup]:
        return [self.auth]
