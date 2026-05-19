import base64
import binascii
import json
import platform
import random
import shutil
import socket
import subprocess
import time
from pathlib import Path

import typer
from rich.align import Align
from rich.console import Console, Theme
from rich.prompt import Confirm
from questionary import Style

questionary_style = Style(
    [
        ("pointer", "fg:#ff8800 bold"),
        ("highlighted", "fg:black bg:#ff8800 bold"),
        ("selected", "fg:#ff8800 bold"),
    ]
)

custom_theme = Theme(
    {
        "info": "dim cyan",
        "warning": "magenta",
        "danger": "bold red",
        "success": "bold green",
        "title": "bold white on #5f00d7",
        "key": "bold #ff6600",
        "value": "white",
        "hint": "italic dim white",
    }
)

HINTS = [
    "The Edge Key contains the connection details for dashboard and agent communication.",
    "Portabase uses Docker Compose to isolate your databases.",
    "You can list all configured databases using 'portabase db list <name>'.",
    "Running 'portabase stop' will gracefully shut down your containers.",
    "The agent polls the github for configuration updates.",
    "Logs can be viewed in real-time with 'portabase logs <name>'.",
    "Custom environment variables can be added to the generated .env file.",
    "Need to update? Use 'portabase update' to get the latest version.",
    "You can add multiple databases to a single agent during setup.",
    "Portabase Dashboard provides a web interface to manage your infrastructure.",
    "Is Docker not running? The CLI will offer to start it for you!",
    "All configurations are stored locally in the component's folder.",
    "The 'portabase restart' command is useful after manual .env modifications.",
    "Portabase is open-source! Check our GitHub to contribute.",
    "Using the --start flag with 'agent' or 'dashboard' skips the final prompt.",
    "Internal databases are automatically backed up when using volumes.",
    "The dashboard requires a PostgreSQL database to store its own data.",
    "You can change the update channel to 'beta' in the config for early features.",
    "Portabase network ensures secure communication between your containers.",
    "Lost your Edge Key? You can find it in the dashboard.",
    "The 'portabase uninstall' command safely removes containers and their data.",
    "Use 'portabase --version' to check your current installation details.",
    "The 'databases.json' file keeps track of all managed database instances.",
]


def get_random_hint():
    return f"[hint]{random.choice(HINTS)}[/hint]"


console = Console(theme=custom_theme)

BANNER = """
[bold #ff6600]█▀█ █▀█ █▀█ ▀█▀ ▄▀█ █▄▄ ▄▀█ █▀ █▀▀[/bold #ff6600]
[bold #ff6600]█▀▀ █▄█ █▀▄  █  █▀█ █▄█ █▀█ ▄█ ██▄[/bold #ff6600]
[dim]Deploy your infrastructure anywhere.[/dim]
"""


def print_banner():
    console.print(Align.center(BANNER))
    console.print(Align.center(get_random_hint() + "\n"))


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def start_docker():
    """Attempts to start the Docker daemon based on the OS."""
    os_type = platform.system()

    try:
        if os_type == "Linux":
            subprocess.run(["sudo", "systemctl", "start", "docker"], check=True)
        elif os_type == "Darwin":
            subprocess.run(["open", "--background", "-a", "Docker"], check=True)
        elif os_type == "Windows":
            subprocess.run(["start", "docker"], shell=True, check=True)

        console.print("[info]Waiting for Docker to start...[/info]")
        for _ in range(10):
            try:
                subprocess.run(
                    ["docker", "info"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                console.print("[success]✔ Docker started successfully.[/success]")
                return True
            except:
                time.sleep(2)
    except Exception as e:
        console.print(f"[danger]✖ Failed to start Docker:[/danger] {e}")

    return False


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
            check=True,
        )
    except subprocess.CalledProcessError:
        console.print(
            "[warning]⚠ Docker is installed but the Daemon is not running.[/warning]"
        )
        if Confirm.ask("Do you want to try starting Docker?"):
            if start_docker():
                return

        console.print("[danger]✖ Docker is required to continue.[/danger]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[danger]✖ Critical Error executing Docker:[/danger] {e}")
        raise typer.Exit(1)


def validate_work_dir(path: Path):
    if not (path / "docker-compose.yml").exists():
        console.print(f"[danger]No Portabase configuration found in: {path}[/danger]")
        raise typer.Exit(1)
    return path


def validate_edge_key(key: str) -> bool:
    """Validates the integrity of the EDGE_KEY (Base64 or JSON)."""
    try:
        try:
            decoded_bytes = base64.b64decode(key, validate=True)
            decoded_str = decoded_bytes.decode("utf-8")
            data = json.loads(decoded_str)
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
            try:
                data = json.loads(key)
            except json.JSONDecodeError:
                return False

        required_fields = ["serverUrl", "agentId", "masterKeyB64"]
        return all(field in data for field in required_fields)
    except Exception:
        return False


def current_version() -> str:

    try:
        import sys
        import tomllib
        from pathlib import Path

        if getattr(sys, "frozen", False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).parent.parent
        with open(base_path / "pyproject.toml", "rb") as f:
            __version__ = tomllib.load(f)["project"]["version"]
    except (FileNotFoundError, KeyError, ImportError, AttributeError):
        __version__ = "unknown"
    return __version__
