from __future__ import annotations

import inspect
import secrets
import sys
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

import typer

from commands.base import Command, CommandGroup
from commands.dashboard_auth import DashboardAuthCommands
from commands.db import report_write
from core.errors import ValidationError
from core.utils import generate_password, slugify_project_name
from services import dashboard_settings as ds
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


def _flag(name: str) -> str:
    return "--" + name.replace("_", "-")


def settings_parameters() -> list[inspect.Parameter]:
    params: list[inspect.Parameter] = []
    for setting in ds.SETTINGS:
        field = setting.field
        flag = _flag(setting.name)
        if field.kind == "bool":
            ann: Any = Annotated[
                bool | None, typer.Option(f"{flag}/--no-{flag[2:]}", help=field.prompt)
            ]
        else:
            note = " (prefer the -stdin variant)" if setting.secret else ""
            ann = Annotated[str | None, typer.Option(flag, help=field.prompt + note)]
        params.append(
            inspect.Parameter(
                setting.name,
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=ann,
            )
        )
        if setting.secret:
            params.append(
                inspect.Parameter(
                    f"{setting.name}_stdin",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=False,
                    annotation=Annotated[
                        bool,
                        typer.Option(
                            f"{flag}-stdin",
                            help=f"Read {field.prompt.lower()} from stdin",
                        ),
                    ],
                )
            )
    return params


def read_secret_flags(values: dict[str, Any]) -> dict[str, Any]:
    out = dict(values)
    for setting in ds.SETTINGS:
        if setting.secret and out.pop(f"{setting.name}_stdin", False):
            out[setting.name] = sys.stdin.readline().rstrip("\n")
    return out


def display(name: str, value: Any) -> str:
    if ds.get(name).secret:
        return "••••••••"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


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

    def apply_settings(self, project: DashboardProject, values: dict[str, Any]) -> None:
        form = self.ui.form()
        for name, raw in values.items():
            if raw is not None:
                project.set(name, form.ask(ds.get(name).field, raw))


class DashboardCreateCommand(_DashboardCommand):
    name, help = "create", "Create a new Portabase Dashboard instance."

    def register(self, app: typer.Typer) -> None:
        def entry(*args: Any, **kwargs: Any) -> None:
            self.run(*args, **kwargs)

        static = [
            p
            for p in inspect.signature(self.run, eval_str=True).parameters.values()
            if p.kind is not inspect.Parameter.VAR_KEYWORD
        ]
        signature = inspect.Signature(static + settings_parameters())
        entry.__signature__ = signature  # type: ignore[attr-defined]
        entry.__annotations__ = {
            name: param.annotation for name, param in signature.parameters.items()
        }
        app.command(
            self.name, help=self.help, rich_help_panel=self.panel, no_args_is_help=True
        )(self._traced(entry))

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

        provided = read_secret_flags(settings)
        self.apply_settings(project, provided)
        explicit = any(v is not None for v in provided.values())
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
            (ds.get(k).field.prompt, display(k, v))
            for k, v in project.settings().items()
            if k != "url" and project.env.get(ds.get(k).env) is not None
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
        self.ui.hint(
            f"Add a login provider with: portabase dashboard auth add {name} oidc <id> ..."
        )

        if start or (
            not self.ui.non_interactive
            and self.ui.confirm("Start dashboard now?", default=False)
        ):
            with self.ui.status("Starting..."):
                self.docker.compose(path, ["up", "-d"])
            self.ui.success(f"Live at: {project.setting('url')}")
        else:
            self.ui.info(f"Run: portabase start {name}")

    def _wizard(self, form: Form, project: DashboardProject) -> None:
        for section, names in ds.WIZARD_SECTIONS:
            self.ui.section(ds.SECTION_TITLES[section])
            for setting_name in names:
                needs_account = (
                    section == "onboarding" and setting_name != "skip_onboarding"
                )
                if needs_account and not project.setting("skip_onboarding"):
                    continue
                setting = ds.get(setting_name)
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
        values = project.settings()
        for section, title in ds.SECTION_TITLES.items():
            rows = [
                (s.field.prompt, display(s.name, values[s.name]))
                for s in ds.SETTINGS
                if s.section == section and values[s.name] not in (None, "")
            ]
            if rows:
                self.ui.summary(rows, title=title.upper())
        providers = project.providers
        if providers:
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
                title="LOGIN PROVIDERS",
            )
        else:
            state = "enabled." if values["password_auth"] else "disabled!"
            self.ui.hint(f"No login provider. Password login is {state}")


class DashboardSetCommand(_DashboardCommand):
    name, help = "set", "Change dashboard settings: KEY VALUE [KEY VALUE ...]."

    def run(
        self,
        path: PathArg,
        pairs: Annotated[
            list[str],
            typer.Argument(help="KEY VALUE pairs; keys as in 'dashboard show'"),
        ],
    ) -> None:
        if len(pairs) % 2:
            raise ValidationError(
                "Expected KEY VALUE pairs.", hint="Known keys: " + ", ".join(ds.BY_NAME)
            )
        project_path = self.require_project_dir(path)
        self.templates.resolve()
        project = DashboardProject.load(project_path)
        self.apply_settings(project, dict(zip(pairs[::2], pairs[1::2], strict=True)))
        self.write(project)
        for key in pairs[::2]:
            self.ui.success(f"{key} = {display(key, project.setting(key))}")
        self.ui.info(f"Apply with: portabase restart {project_path.name}")


class DashboardUnsetCommand(_DashboardCommand):
    name, help = "unset", "Reset dashboard settings to their default: KEY [KEY ...]."

    def run(
        self,
        path: PathArg,
        keys: Annotated[list[str], typer.Argument(help="Setting keys")],
    ) -> None:
        project_path = self.require_project_dir(path)
        self.templates.resolve()
        project = DashboardProject.load(project_path)
        for key in keys:
            project.unset(key)
        self.write(project)
        self.ui.success("Reset: " + ", ".join(keys))
        self.ui.info(f"Apply with: portabase restart {project_path.name}")


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
        return [
            DashboardCreateCommand(*self._deps),
            DashboardShowCommand(*self._deps),
            DashboardSetCommand(*self._deps),
            DashboardUnsetCommand(*self._deps),
        ]

    @property
    def groups(self) -> list[CommandGroup]:
        return [self.auth]
