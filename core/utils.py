import socket
import shutil
import typer
from pathlib import Path
from rich.console import Console, Theme
from rich.align import Align
import subprocess

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

BANNER = """
[bold #ff6600]█▀█ █▀█ █▀█ ▀█▀ ▄▀█ █▄▄ ▄▀█ █▀ █▀▀[/bold #ff6600]
[bold #ff6600]█▀▀ █▄█ █▀▄  █  █▀█ █▄█ █▀█ ▄█ ██▄[/bold #ff6600]
[dim]Deploy your infrastructure anywhere.[/dim]
"""

def print_banner():
    console.print(Align.center(BANNER))

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def check_system():
    docker_path = shutil.which("docker")
    
    if docker_path is None:
        console.print("[danger]✖ Docker not found (binary missing).[/danger]")
        raise typer.Exit(1)

    try:
        subprocess.run(
            [docker_path, "info"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            check=True
        )
    except subprocess.CalledProcessError:
        console.print("[danger]✖ Docker is installed but the Daemon is not running.[/danger]")
        console.print("[dim]Please start Docker Desktop or the docker service.[/dim]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[danger]✖ Critical Error executing Docker:[/danger] {e}")
        raise typer.Exit(1)

def validate_work_dir(path: Path):
    if not (path / "docker-compose.yml").exists():
        console.print(f"[danger]No Portabase configuration found in: {path}[/danger]")
        raise typer.Exit(1)
    return path

def current_version() -> str: 

    try:
        import tomllib
        import sys
        from pathlib import Path
        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent.parent
        with open(base_path / "pyproject.toml", "rb") as f:
            __version__ = tomllib.load(f)["project"]["version"]
    except (FileNotFoundError, KeyError, ImportError, AttributeError):
        __version__ = "unknown"
    return __version__
