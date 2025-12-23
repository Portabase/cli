import typer
from typing import Optional
from commands import agent, dashboard, common, db
from __init__ import __version__

app = typer.Typer(no_args_is_help=True, add_completion=False)

def version_callback(value: bool):
    if value:
        typer.echo(f"{__version__}")
        raise typer.Exit()

@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        help="Show the version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
):
    pass

app.command()(agent.agent)
app.command()(dashboard.dashboard)
app.command()(common.start)
app.command()(common.stop)
app.command()(common.restart)
app.command()(common.logs)
app.command()(common.uninstall)

app.add_typer(db.app, name="db")

if __name__ == "__main__":
    app()