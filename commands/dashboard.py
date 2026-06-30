import re
import secrets
from pathlib import Path
from urllib.parse import quote

import questionary
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
    generate_password,
    get_free_port,
    get_random_hint,
    print_banner,
    questionary_style,
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
        "TZ": "Europe/Paris",
        "LOG_LEVEL": "info",
    }

    mode = questionary.select(
        "Database Setup",
        choices=[
            questionary.Choice(
                "external: create a dedicated container in the same docker-compose.yml (recommended)",
                value="external",
            ),
            questionary.Choice(
                "internal: use the database embedded in the Portabase container",
                value="internal",
            ),
            questionary.Choice(
                "custom: provide credentials of an existing database",
                value="custom",
            ),
        ],
        style=questionary_style,
    ).ask()

    if not mode:
        raise typer.Exit()

    if mode == "external":
        pg_port = get_free_port()
        pg_pass = generate_password(16)
        env_vars.update(
            {
                "POSTGRES_DB": "portabase",
                "POSTGRES_USER": "portabase",
                "POSTGRES_PASSWORD": pg_pass,
                "POSTGRES_HOST": "db",
                "DATABASE_URL": f"postgresql://portabase:{quote(pg_pass, safe='')}@db:5432/portabase?schema=public",
                "PG_PORT": str(pg_port),
            }
        )
        final_compose = raw_template.replace("${PROJECT_NAME}", project_name)
    elif mode == "custom":
        console.print("[info]External Database Configuration[/info]")
        db_host = Prompt.ask("Host", default="localhost")
        db_port = IntPrompt.ask("Port", default=5432)
        db_name = Prompt.ask("Database Name", default="portabase")
        db_user = Prompt.ask("Username")
        db_pass = questionary.password("Password", style=questionary_style).ask()
        if db_pass is None:
            raise typer.Exit()

        env_vars.update(
            {
                "POSTGRES_DB": db_name,
                "POSTGRES_USER": db_user,
                "POSTGRES_PASSWORD": db_pass,
                "POSTGRES_HOST": db_host,
                "DATABASE_URL": f"postgresql://{quote(db_user, safe='')}:{quote(db_pass, safe='')}@{db_host}:{db_port}/{db_name}?schema=public",
                "PG_PORT": str(db_port),
            }
        )

        final_compose = re.sub(
            r"[ ]{4}depends_on:\n[ ]{6}db:\n[ ]{8}condition: service_healthy\n",
            "",
            raw_template,
        )
        final_compose = re.sub(
            r"[ ]{2}db:.*?retries: 5\n", "", final_compose, flags=re.DOTALL
        )
        final_compose = re.sub(r"[ ]{2}postgres-data:\n", "", final_compose)
        final_compose = final_compose.replace("${PROJECT_NAME}", project_name)
    else:
        final_compose = re.sub(
            r"[ ]{4}depends_on:\n[ ]{6}db:\n[ ]{8}condition: service_healthy\n",
            "",
            raw_template,
        )
        final_compose = re.sub(
            r"[ ]{2}db:.*?retries: 5\n", "", final_compose, flags=re.DOTALL
        )
        final_compose = re.sub(r"[ ]{2}postgres-data:\n", "", final_compose)
        final_compose = final_compose.replace("${PROJECT_NAME}", project_name)

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("Property", style="bold cyan")
    summary.add_column("Value", style="white")

    summary.add_row("Dashboard Name", name)
    summary.add_row("Path", str(path))
    summary.add_row("Access URL", f"[bold green]http://localhost:{port}[/bold green]")

    db_setup_label = {
        "external": "Dedicated Docker Container (Recommended)",
        "internal": "Embedded Database (In-container)",
        "custom": "Custom/Existing Database",
    }
    summary.add_row("Database Setup", db_setup_label.get(mode))

    if mode == "external":
        summary.add_row("Internal Port", env_vars["PG_PORT"])
    elif mode == "custom":
        summary.add_row("DB Host", env_vars["POSTGRES_HOST"])
        summary.add_row("DB Name", env_vars["POSTGRES_DB"])
        masked_url = re.sub(r":.*?@", ":****@", env_vars["DATABASE_URL"])
        summary.add_row("Connection URL", f"[dim]{masked_url}[/dim]")

    summary.add_row("Files to Create", "• docker-compose.yml\n• .env")

    console.print("")
    console.print(
        Panel(
            summary,
            title="[bold white]PROPOSED CONFIGURATION[/bold white]",
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

    db_info = ""
    if mode == "external":
        db_info = f"\n[dim]DB Port: {env_vars.get('PG_PORT')}[/dim]"
    elif mode == "custom":
        db_info = f"\n[dim]External DB: {env_vars.get('POSTGRES_HOST')}[/dim]"
    else:
        db_info = "\n[dim]Embedded Database[/dim]"

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
