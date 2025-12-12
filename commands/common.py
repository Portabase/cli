import typer
import subprocess
import shutil
from pathlib import Path
from rich.prompt import Confirm
from core.utils import console, validate_work_dir
from core.docker import run_compose

def start(path: Path = typer.Argument(..., help="Path to component folder")):
    path = path.resolve()
    validate_work_dir(path)
    with console.status(f"[bold magenta]Starting {path.name}...[/bold magenta]"):
        run_compose(path, ["up", "-d"])
    console.print("[success]✔ Started[/success]")

def stop(path: Path = typer.Argument(..., help="Path to component folder")):
    path = path.resolve()
    validate_work_dir(path)
    with console.status(f"[bold magenta]Stopping {path.name}...[/bold magenta]"):
        run_compose(path, ["stop"])
    console.print("[success]✔ Stopped[/success]")

def restart(path: Path = typer.Argument(..., help="Path to component folder")):
    path = path.resolve()
    validate_work_dir(path)
    with console.status(f"[bold magenta]Restarting {path.name}...[/bold magenta]"):
        run_compose(path, ["restart"])
    console.print("[success]✔ Restarted[/success]")

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