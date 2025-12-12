import typer
from commands import agent, dashboard, common, db

app = typer.Typer(no_args_is_help=True, add_completion=False)

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