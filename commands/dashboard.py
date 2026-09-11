from __future__ import annotations

import secrets
import sys
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import typer

from commands.base import Command
from commands.db import report_write
from core.utils import generate_password, slugify_project_name
from services.docker import DockerRunner
from services.ports import PortAllocator
from services.project import DashboardProject
from services.renderer import ComposeRenderer
from services.telemetry import Telemetry
from services.templates import TemplateRepository
from ui import UI

DB_MODES = ("external", "internal", "custom")
MODE_LABELS = {
    "external": "Dedicated Docker Container (Recommended)",
    "internal": "Embedded Database (In-container)",
    "custom": "Custom/Existing Database",
}


class DashboardCommand(Command):
    name = "dashboard"
    help = "Create a new Portabase Dashboard instance."
    panel = "Creation"
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
            ("Access URL", env_vars["PROJECT_URL"]),
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

        rows.append(("Files to Create", "docker-compose.yml, .env"))
        self.ui.summary(rows, title="PROPOSED CONFIGURATION")
        if not yes:
            self.confirm_or_abort(
                "Apply this configuration and generate files?", default=True
            )

        project = DashboardProject.create(path, env_vars)
        with self.ui.status("Rendering configuration..."):
            result = self.renderer.render_dashboard(project)
            project.save_state()
            report = result.write(path)
        report_write(self.ui, report)
        self.ui.success(f"Dashboard '{name}' created in {path}")

        if start or (
            not self.ui.non_interactive
            and self.ui.confirm("Start dashboard now?", default=False)
        ):
            with self.ui.status("Starting..."):
                self.docker.compose(path, ["up", "-d"])
            self.ui.success(f"Live at: {env_vars['PROJECT_URL']}")
        else:
            self.ui.info(f"Run: portabase start {name}")

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
