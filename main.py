import typer
from typing import Optional
from commands import agent, dashboard, common, db, config
from core.utils import console, current_version
from core.updater import check_for_updates, update_cli

app = typer.Typer(no_args_is_help=True, add_completion=False)

def version_callback(value: bool):
    if value:
        console.print(f"Portabase CLI version: {current_version()}")
        check_for_updates(force=True)
        raise typer.Exit()

@app.callback()
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        help="Show the version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
):
    if ctx.invoked_subcommand != "update":
        check_for_updates()

@app.command()
def update():
    update_cli()

app.command()(agent.agent)
app.command()(dashboard.dashboard)
app.command()(common.start)
app.command()(common.stop)
app.command()(common.restart)
app.command()(common.logs)
app.command()(common.uninstall)

app.add_typer(db.app, name="db")
app.add_typer(config.app, name="config")

if __name__ == "__main__":
    app()
