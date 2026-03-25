import secrets
from pathlib import Path

import typer
import yaml
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from core.config import write_env_file
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
    raw_template = raw_template.replace("${PROJECT_NAME}", project_name)

    try:
        compose_data = yaml.safe_load(raw_template) or {}
    except yaml.YAMLError as exc:
        console.print(f"[danger]Error parsing dashboard template : {exc}[/danger]")
        raise typer.Exit(1)

    auth_secret = secrets.token_hex(32)
    base_url = f"http://localhost:{port}"

    env_vars = {
        "HOST_PORT": port,
        "PROJECT_SECRET": auth_secret,
        "PROJECT_URL": base_url,
        "PROJECT_NAME": project_name,
    }

    console.print()
    console.print(
        Panel(
            "• [bold cyan]internal[/bold cyan] : Embedded database\n"
            "• [bold cyan]compose[/bold cyan]  : Dedicated local PostgreSQL container\n"
            "• [bold cyan]external[/bold cyan] : Existing external database",
            title="[bold white]Database Mode Selection[/bold white]",
            border_style="cyan",
            expand=False,
            padding=(1, 2),
        )
    )
    console.print()

    mode = Prompt.ask(
        "Database System Setup",
        choices=["internal", "compose", "external"],
        default="internal",
    )

    if mode == "internal":
        console.print("[info]Using embedded internal database.[/info]")

        if "services" in compose_data and "db" in compose_data["services"]:
            del compose_data["services"]["db"]

        if "services" in compose_data and "app" in compose_data["services"]:
            if "depends_on" in compose_data["services"]["app"]:
                depends_on_data = compose_data["services"]["app"]["depends_on"]

                if isinstance(depends_on_data, dict) and "db" in depends_on_data:
                    del compose_data["services"]["app"]["depends_on"]["db"]
                elif isinstance(depends_on_data, list) and "db" in depends_on_data:
                    compose_data["services"]["app"]["depends_on"].remove("db")

                if not compose_data["services"]["app"]["depends_on"]:
                    del compose_data["services"]["app"]["depends_on"]

        if "volumes" in compose_data and "postgres-data" in compose_data["volumes"]:
            del compose_data["volumes"]["postgres-data"]

    elif mode == "compose":
        console.print("[info]Creating a dedicated local PostgreSQL container.[/info]")
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

        if "services" in compose_data and "db" in compose_data["services"]:
            del compose_data["services"]["db"]

        if "services" in compose_data and "app" in compose_data["services"]:
            if "depends_on" in compose_data["services"]["app"]:
                depends_on_data = compose_data["services"]["app"]["depends_on"]

                if isinstance(depends_on_data, dict) and "db" in depends_on_data:
                    del compose_data["services"]["app"]["depends_on"]["db"]
                elif isinstance(depends_on_data, list) and "db" in depends_on_data:
                    compose_data["services"]["app"]["depends_on"].remove("db")

                if not compose_data["services"]["app"]["depends_on"]:
                    del compose_data["services"]["app"]["depends_on"]

        if "volumes" in compose_data and "postgres-data" in compose_data["volumes"]:
            del compose_data["volumes"]["postgres-data"]

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("Property", style="bold cyan")
    summary.add_column("Value", style="white")

    summary.add_row("Dashboard Name", name)
    summary.add_row("Path", str(path))
    summary.add_row("Access URL", f"[bold green]http://localhost:{port}[/bold green]")

    if mode == "internal":
        summary.add_row("Database Setup", "Embedded database")
    elif mode == "compose":
        summary.add_row("Database Setup", "Dedicated Local")
        summary.add_row("Internal Port", env_vars["PG_PORT"])
    else:
        summary.add_row("Database Setup", "External Database")
        summary.add_row("DB Host", env_vars["POSTGRES_HOST"])
        summary.add_row("DB Name", env_vars["POSTGRES_DB"])
        import re

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

    with open(path / "docker-compose.yml", "w") as f:
        yaml.safe_dump(compose_data, f, default_flow_style=False, sort_keys=False)

    write_env_file(path, env_vars)

    db_info = ""
    if mode == "compose":
        db_info = f"\n[dim]DB Port: {env_vars.get('PG_PORT')}[/dim]"
    elif mode == "external":
        db_info = f"\n[dim]External DB: {env_vars.get('POSTGRES_HOST')}[/dim]"

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
