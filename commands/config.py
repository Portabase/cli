import typer
from core.utils import console
from core.config import set_config_value, get_config_value

app = typer.Typer(help="Manage global CLI configuration.")

@app.command()
def channel(
    name: str = typer.Argument(..., help="Update channel name (stable or beta)")
):
    name = name.lower()
    if name not in ["stable", "beta"]:
        console.print("[danger]✖ Invalid channel. Choose either 'stable' or 'beta'.[/danger]")
        raise typer.Exit(1)
    
    set_config_value("update_channel", name)
    console.print(f"[success]✔ Update channel set to: [bold]{name}[/bold][/success]")

@app.command()
def show():
    channel = get_config_value("update_channel", "auto (based on current version)")
    console.print(f"[info]Current Configuration:[/info]")
    console.print(f"  [bold]Update Channel:[/bold] {channel}")
