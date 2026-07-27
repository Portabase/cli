import typer

from core.config import get_config_value, set_config_value
from core.utils import console

app = typer.Typer(help="Manage global CLI configuration.")


@app.command()
def channel(
    name: str = typer.Argument(..., help="Update channel name (stable or beta)"),
):
    name = name.lower()
    if name not in ["stable", "beta"]:
        console.print(
            "[danger]✖ Invalid channel. Choose either 'stable' or 'beta'.[/danger]"
        )
        raise typer.Exit(1)

    set_config_value("update_channel", name)
    console.print(f"[success]✔ Update channel set to: [bold]{name}[/bold][/success]")


@app.command()
def engine(
    name: str = typer.Argument(
        ..., help="Container engine to use (docker, podman, or auto)"
    ),
):
    name = name.lower()
    if name not in ["docker", "podman", "auto"]:
        console.print(
            "[danger]✖ Invalid engine. Choose 'docker', 'podman', or 'auto'.[/danger]"
        )
        raise typer.Exit(1)

    if name == "auto":
        set_config_value("container_engine", None)
        console.print(
            "[success]✔ Container engine set to: [bold]auto[/bold] "
            "(prefers Docker, falls back to Podman)[/success]"
        )
    else:
        set_config_value("container_engine", name)
        console.print(
            f"[success]✔ Container engine set to: [bold]{name}[/bold][/success]"
        )


@app.command()
def show():
    channel = get_config_value("update_channel", "auto (based on current version)")
    engine = get_config_value("container_engine") or "auto (prefers Docker)"
    console.print(f"[info]Current Configuration:[/info]")
    console.print(f"  [bold]Update Channel:[/bold] {channel}")
    console.print(f"  [bold]Container Engine:[/bold] {engine}")
