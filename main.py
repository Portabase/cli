from typing import Optional

import typer

from commands import agent, common, config, dashboard, db
from core.updater import check_for_updates, update_cli
from core.utils import console, current_version

app = typer.Typer(
    help="Portabase CLI - Manage your Portabase components.",
    no_args_is_help=True,
    add_completion=False,
)


def version_callback(value: bool):
    if value:
        console.print(f"Portabase CLI version: {current_version()}")
        check_for_updates(force=True)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    _: Optional[bool] = typer.Option(
        None,
        "--version",
        help="Show the version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
):
    """
    Portabase CLI to manage agents, dashboards and databases.
    """
    if ctx.invoked_subcommand != "update":
        check_for_updates()


@app.command(help="Update the CLI to the latest version.", rich_help_panel="System")
def update():
    update_cli()


app.command(
    help="Create a new Portabase Agent instance.",
    rich_help_panel="Creation",
    no_args_is_help=True,
)(agent.agent)
app.command(
    help="Create a new Portabase Dashboard instance.",
    rich_help_panel="Creation",
    no_args_is_help=True,
)(dashboard.dashboard)
app.command(
    help="Start a Portabase component.",
    rich_help_panel="Lifecycle",
    no_args_is_help=True,
)(common.start)
app.command(
    help="Stop a Portabase component.",
    rich_help_panel="Lifecycle",
    no_args_is_help=True,
)(common.stop)
app.command(
    help="Restart a Portabase component.",
    rich_help_panel="Lifecycle",
    no_args_is_help=True,
)(common.restart)
app.command(
    help="View logs of a Portabase component.",
    rich_help_panel="Lifecycle",
    no_args_is_help=True,
)(common.logs)
app.command(
    help="Uninstall and delete a Portabase component.",
    rich_help_panel="Lifecycle",
    no_args_is_help=True,
)(common.uninstall)

app.add_typer(db.app, name="db", rich_help_panel="Configuration")
app.add_typer(config.app, name="config", rich_help_panel="Configuration")

if __name__ == "__main__":
    app()
