import typer
import subprocess
import shutil
import secrets
import socket
from pathlib import Path
from typing import Optional
from rich.console import Console, Theme
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.align import Align

custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "danger": "bold red",
    "success": "bold green",
    "title": "bold white on #5f00d7",
    "key": "bold #ff6600",
    "value": "white"
})
console = Console(theme=custom_theme)
app = typer.Typer(no_args_is_help=True, add_completion=False)

APP_NAME = "Portabase"
VERSION = "1.2.0"

BANNER = """
[bold #ff6600]█▀█ █▀█ █▀█ ▀█▀ ▄▀█ █▄▄ ▄▀█ █▀ █▀▀[/bold #ff6600]
[bold #ff6600]█▀▀ █▄█ █▀▄  █  █▀█ █▄█ █▀█ ▄█ ██▄[/bold #ff6600]
[dim]Deploy your infrastructure anywhere.[/dim]
"""

AGENT_TEMPLATE = """
name: ${PROJECT_NAME}
services:
  app:
    container_name: ${PROJECT_NAME}-app
    restart: always
    image: solucetechnologies/agent-portabase:latest
    volumes:
      - ./databases.json:/app/src/data/config/config.json
    environment:
      TZ: "Europe/Paris"
      EDGE_KEY: "${EDGE_KEY}"
    networks:
      - portabase
  db:
    container_name: ${PROJECT_NAME}-pg
    image: postgres:17-alpine
    networks:
      - portabase
      - default
    ports:
      - "${PG_PORT}:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=${DB_NAME}
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
  db2:
    container_name: ${PROJECT_NAME}-mariadb
    image: mariadb:latest
    ports:
      - "${MYSQL_PORT}:3306"
    environment:
      - MYSQL_DATABASE=${DB_NAME}
      - MYSQL_USER=${DB_USER}
      - MYSQL_PASSWORD=${DB_PASSWORD}
      - MYSQL_RANDOM_ROOT_PASSWORD=yes
    volumes:
      - mariadb-data:/var/lib/mysql
volumes:
  postgres-data:
  mariadb-data:
networks:
  portabase:
    name: portabase_network
    external: true
"""

DASHBOARD_TEMPLATE = """
name: ${PROJECT_NAME}
services:
  portabase:
    container_name: ${PROJECT_NAME}-app
    image: solucetechnologies/portabase:latest
    env_file:
      - .env
    ports:
      - '${PORT}:3000'
    environment:
      - TIME_ZONE=Europe/Paris
      - HOSTNAME=0.0.0.0
      - PORT=3000
    volumes:
      - portabase-private:/app/private
    depends_on:
      db:
        condition: service_healthy
  db:
    container_name: ${PROJECT_NAME}-pg
    image: postgres:17-alpine
    ports:
      - "${PG_PORT}:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=${POSTGRES_DB}
      - POSTGRES_USER=${POSTGRES_USER}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - PROJECT_NAME="Portabase"
      - PROJECT_URL=${PROJECT_URL}
    healthcheck:
      test: [ "CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}" ]
      interval: 10s
      timeout: 5s
      retries: 5
volumes:
  postgres-data:
  portabase-private:
"""

def print_banner():
    console.print(Align.center(BANNER))

def check_system():
    if shutil.which("docker") is None:
        console.print("[danger]✖ Docker not found.[/danger]")
        raise typer.Exit(1)
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except Exception:
        console.print("[danger]✖ Docker daemon is not running.[/danger]")
        raise typer.Exit(1)

def ensure_network(name: str):
    try:
        subprocess.run(["docker", "network", "inspect", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        subprocess.run(["docker", "network", "create", name], stdout=subprocess.DEVNULL, check=True)

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

def write_env_file(work_dir: Path, env_vars: dict):
    content = ""
    for k, v in env_vars.items():
        content += f'{k}="{v}"\n'
    write_file(work_dir / ".env", content)

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def validate_work_dir(path: Path):
    if not (path / "docker-compose.yml").exists():
        console.print(f"[danger]No Portabase configuration found in: {path}[/danger]")
        raise typer.Exit(1)

def run_compose(cwd: Path, args: list):
    try:
        project_name = cwd.name.lower().replace(" ", "_")
        cmd = ["docker", "compose", "-p", project_name] + args
        subprocess.run(cmd, cwd=cwd, check=True)
    except subprocess.CalledProcessError:
        console.print("[danger]Command failed.[/danger]")
        raise typer.Exit(1)

@app.command()
def agent(
    name: str = typer.Argument(..., help="Name of the agent (creates a folder)"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="Edge Key"),
    start: bool = typer.Option(False, "--start", "-s", help="Start immediately")
):
    print_banner()
    check_system()
    ensure_network("portabase_network")

    path = Path(name).resolve()
    if path.exists():
        console.print(f"[warning]Directory '{name}' already exists.[/warning]")
        if not Confirm.ask("Overwrite?"):
            raise typer.Exit()
    
    path.mkdir(parents=True, exist_ok=True)
    project_name = name.lower().replace(" ", "-")

    if not key:
        key = Prompt.ask("[key]Edge Key[/key]")

    pg_port = get_free_port()
    mysql_port = get_free_port()

    env_vars = {
        "EDGE_KEY": key,
        "DB_NAME": "portabase_agent_db",
        "DB_USER": "admin",
        "DB_PASSWORD": secrets.token_hex(8),
        "PROJECT_NAME": project_name,
        "PG_PORT": str(pg_port),
        "MYSQL_PORT": str(mysql_port)
    }

    json_path = path / "databases.json"
    if not json_path.exists():
        write_file(json_path, "[]")
        
    write_file(path / "docker-compose.yml", AGENT_TEMPLATE)
    write_env_file(path, env_vars)

    console.print(Panel(f"[bold white]AGENT CREATED: {name}[/bold white]\n[dim]Path: {path}[/dim]\n[dim]Ports: PG:{pg_port} MySQL:{mysql_port}[/dim]", style="bold #5f00d7"))

    if start or Confirm.ask("Start agent now?", default=False):
        with console.status("[bold magenta]Starting...[/bold magenta]", spinner="earth"):
            run_compose(path, ["up", "-d"])
        console.print(f"[bold green]✔ Agent {name} is running[/bold green]")
    else:
        console.print(f"[info]Run: portabase start {name}[/info]")

@app.command()
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
    
    write_file(path / "docker-compose.yml", DASHBOARD_TEMPLATE)
    write_env_file(path, env_vars)
    
    console.print(Panel(f"[bold white]DASHBOARD CREATED: {name}[/bold white]\n[dim]Path: {path}[/dim]\n[dim]DB Port: {pg_port}[/dim]", style="bold #5f00d7"))

    if start or Confirm.ask("Start dashboard now?", default=False):
        with console.status("[bold magenta]Starting...[/bold magenta]", spinner="earth"):
            run_compose(path, ["up", "-d"])
        console.print(f"[bold green]✔ Live at: http://localhost:{port}[/bold green]")
    else:
        console.print(f"[info]Run: portabase start {name}[/info]")

@app.command()
def start(path: Path = typer.Argument(..., help="Path to component folder")):
    path = path.resolve()
    validate_work_dir(path)
    with console.status(f"[bold magenta]Starting {path.name}...[/bold magenta]"):
        run_compose(path, ["up", "-d"])
    console.print("[success]✔ Started[/success]")

@app.command()
def stop(path: Path = typer.Argument(..., help="Path to component folder")):
    path = path.resolve()
    validate_work_dir(path)
    with console.status(f"[bold magenta]Stopping {path.name}...[/bold magenta]"):
        run_compose(path, ["stop"])
    console.print("[success]✔ Stopped[/success]")

@app.command()
def logs(
    path: Path = typer.Argument(..., help="Path to component folder"),
    follow: bool = typer.Option(True, "--follow/--no-follow", "-f")
):
    path = path.resolve()
    validate_work_dir(path)
    args = ["logs"]
    if follow:
        args.append("-f")
    try:
        project_name = path.name.lower().replace(" ", "_")
        subprocess.run(["docker", "compose", "-p", project_name] + args, cwd=path)
    except KeyboardInterrupt:
        pass

@app.command()
def uninstall(
    path: Path = typer.Argument(..., help="Path to component folder"),
    force: bool = typer.Option(False, "--force", "-f")
):
    path = path.resolve()
    validate_work_dir(path)
    
    if not force:
        console.print(f"[danger]⚠ WARNING: This will delete containers and data in {path}.[/danger]")
        if not Confirm.ask("Are you sure?"):
            raise typer.Exit()

    with console.status(f"[bold red]Uninstalling...[/bold red]"):
        run_compose(path, ["down", "-v"])
        try:
            shutil.rmtree(path)
        except Exception as e:
            console.print(f"[warning]Could not remove directory: {e}[/warning]")
            
    console.print(f"[success]✔ Uninstalled[/success]")

if __name__ == "__main__":
    app()