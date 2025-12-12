import subprocess
import typer
from core.utils import console
from pathlib import Path

def ensure_network(name: str):
    try:
        subprocess.run(["docker", "network", "inspect", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        subprocess.run(["docker", "network", "create", name], stdout=subprocess.DEVNULL, check=True)

def run_compose(cwd: Path, args: list):
    try:
        project_name = cwd.name.lower().replace(" ", "_")
        cmd = ["docker", "compose", "-p", project_name] + args
        subprocess.run(cmd, cwd=cwd, check=True)
    except subprocess.CalledProcessError:
        console.print("[danger]Command failed.[/danger]")
        raise typer.Exit(1)