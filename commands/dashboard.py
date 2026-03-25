import re
import secrets
from pathlib import Path

import typer
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from core.config import write_env_file, write_file
from core.docker import run_compose
from core.network import fetch_template
from core.utils import (
    check_system,
    console,
    get_free_port,
    get_random_hint,
    print_banner,
)


def dashboard(
    name: str = typer.Argument(..., help="Name of the dashboard (creates a folder)"),
    port: str = typer.Option("8887", help="Web Port"),
    start: bool = typer.Option(False, "--start", "-s", help="Start immediately"),
):
    print_banner()
    check_system()

    path = Path(name).resolve()
    if path.exists():
        console.print(f"[warning]Directory '{name}' already exists.[/warning]")
        if not Confirm.ask("Overwrite?"):
            raise typer.Exit()

    path.mkdir(parents=True, exist_ok=True)
    project_name = name.lower().replace(" ", "-")

    raw_template = fetch_template("dashboard.yml")

    auth_secret = secrets.token_hex(32)
    base_url = f"http://localhost:{port}"

    env_vars = {
        "HOST_PORT": port,
        "PROJECT_SECRET": auth_secret,
        "PROJECT_URL": base_url,
        "PROJECT_NAME": project_name,
    }

    mode = Prompt.ask(
        "Database Setup", choices=["internal", "external"], default="internal"
    )

    if mode == "internal":
        pg_port = get_free_port()
        pg_pass = secrets.token_hex(16)
        env_vars.update(
            {
                "POSTGRES_DB": "portabase",
                "POSTGRES_USER": "portabase",
                "POSTGRES_PASSWORD": pg_pass,
                "POSTGRES_HOST": "db",
                "DATABASE_URL": f"postgresql://portabase:{pg_pass}@db:5432/portabase?schema=public",
                "PG_PORT": str(pg_port),
            }
        )
        final_compose = raw_template.replace("${PROJECT_NAME}", project_name)
    else:
        console.print("[info]External Database Configuration[/info]")
        db_host = Prompt.ask("Host", default="localhost")
        db_port = IntPrompt.ask("Port", default=5432)
        db_name = Prompt.ask("Database Name", default="portabase")
        db_user = Prompt.ask("Username")
        db_pass = Prompt.ask("Password", password=True)

        env_vars.update(
            {
                "POSTGRES_DB": db_name,
                "POSTGRES_USER": db_user,
                "POSTGRES_PASSWORD": db_pass,
                "POSTGRES_HOST": db_host,
                "DATABASE_URL": f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}?schema=public",
                "PG_PORT": str(db_port),
            }
        )

        final_compose = re.sub(
            r"[ ]{8}depends_on:.*?service_healthy\n", "", raw_template, flags=re.DOTALL
        )
        final_compose = re.sub(
            r"[ ]{4}db:.*?retries: 5\n", "", final_compose, flags=re.DOTALL
        )
        final_compose = re.sub(r"[ ]{4}postgres-data:\n", "", final_compose)
        final_compose = final_compose.replace("${PROJECT_NAME}", project_name)

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("Property", style="bold cyan")
    summary.add_column("Value", style="white")

    summary.add_row("Dashboard Name", name)
    summary.add_row("Path", str(path))
    summary.add_row("Access URL", f"[bold green]http://localhost:{port}[/bold green]")
    summary.add_row(
        "Database Setup",
        "All-in-one (Internal Docker DB)"
        if mode == "internal"
        else "Custom (External Database)",
    )

    if mode == "internal":
        summary.add_row("Internal Port", env_vars["PG_PORT"])
    else:
        summary.add_row("DB Host", env_vars["POSTGRES_HOST"])
        summary.add_row("DB Name", env_vars["POSTGRES_DB"])
        masked_url = re.sub(r":.*?@", ":****@", env_vars["DATABASE_URL"])
        summary.add_row("Connection URL", f"[dim]{masked_url}[/dim]")

    summary.add_row("Files to Create", "• docker-compose.yml\n• .env")

    console.print("")
    console.print(
        Panel(
            summary,
            title="[bold white]SUMMARY[/bold white]",
            border_style="bold blue",
            expand=False,
        )
    )
    console.print(
        "[dim]The dashboard will be set up with the parameters above.[/dim]\n"
    )

    if not Confirm.ask(
        "[bold]Apply this configuration and generate files?[/bold]", default=True
    ):
        console.print("[warning]Configuration cancelled.[/warning]")
        raise typer.Exit()

    write_file(path / "docker-compose.yml", final_compose)
    write_env_file(path, env_vars)

    db_info = (
        f"\n[dim]DB Port: {env_vars.get('PG_PORT')}[/dim]"
        if mode == "internal"
        else f"\n[dim]External DB: {env_vars.get('POSTGRES_HOST')}[/dim]"
    )
    console.print(
        Panel(
            f"[bold white]DASHBOARD CREATED: {name}[/bold white]\n[dim]Path: {path}[/dim]{db_info}",
            style="bold #5f00d7",
        )
    )

    if start or Confirm.ask("Start dashboard now?", default=False):
        status_msg = f"[bold magenta]Starting...[/bold magenta]\n{get_random_hint()}"
        with console.status(status_msg, spinner="earth"):
            run_compose(path, ["up", "-d"])
        console.print(f"[bold green]✔ Live at: http://localhost:{port}[/bold green]")
    else:
        console.print(f"[info]Run: portabase start {name}[/info]")
