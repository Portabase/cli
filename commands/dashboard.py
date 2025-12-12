import typer
import secrets
from pathlib import Path
from rich.panel import Panel
from rich.prompt import Confirm
from core.utils import console, print_banner, check_system, get_free_port
from core.config import write_file, write_env_file
from core.docker import run_compose
from core.network import fetch_template

def dashboard(
    name: str = typer.Argument(..., help="Name of the dashboard (creates a folder)"),
    port: str = typer.Option("8887", help="Web Port"),
    start: bool = typer.Option(False, "--start", "-s", help="Start immediately")
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
    pg_port = get_free_port()
    
    env_vars = {
        "PORT": port,
        "POSTGRES_DB": "portabase",
        "POSTGRES_USER": "portabase",
        "POSTGRES_PASSWORD": secrets.token_hex(16),
        "POSTGRES_HOST": "db",
        "DATABASE_URL": f"postgresql://portabase:PWD@db:5432/portabase?schema=public",
        "PROJECT_SECRET": auth_secret,
        "PROJECT_URL": base_url,
        "PROJECT_NAME": project_name,
        "PG_PORT": str(pg_port)
    }
    env_vars["DATABASE_URL"] = env_vars["DATABASE_URL"].replace("PWD", env_vars["POSTGRES_PASSWORD"])

    final_compose = raw_template.replace("${PROJECT_NAME}", project_name)
    
    write_file(path / "docker-compose.yml", final_compose)
    write_env_file(path, env_vars)
    
    console.print(Panel(f"[bold white]DASHBOARD CREATED: {name}[/bold white]\n[dim]Path: {path}[/dim]\n[dim]DB Port: {pg_port}[/dim]", style="bold #5f00d7"))

    if start or Confirm.ask("Start dashboard now?", default=False):
        with console.status("[bold magenta]Starting...[/bold magenta]", spinner="earth"):
            run_compose(path, ["up", "-d"])
        console.print(f"[bold green]✔ Live at: http://localhost:{port}[/bold green]")
    else:
        console.print(f"[info]Run: portabase start {name}[/info]")