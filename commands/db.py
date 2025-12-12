import typer
import uuid
from pathlib import Path
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from core.utils import console, validate_work_dir
from core.config import load_db_config, save_db_config, add_db_to_json

app = typer.Typer(help="Manage databases configuration.")

@app.command("list")
def list_dbs(name: str = typer.Argument(..., help="Name of the agent")):
    path = Path(name).resolve()
    validate_work_dir(path)
    
    config = load_db_config(path)
    dbs = config.get("databases", [])
    
    if not dbs:
        console.print("[warning]No databases configured.[/warning]")
        return

    table = Table(title=f"Databases for {name}")
    table.add_column("DB Name", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Host:Port", style="green")
    table.add_column("User", style="white")
    table.add_column("ID", style="dim")

    for db in dbs:
        table.add_row(
            db.get("name", "N/A"),
            db.get("type", "N/A"),
            f"{db.get('host', 'N/A')}:{db.get('port', 'N/A')}",
            db.get("username", "N/A"),
            db.get("generatedId", "")[:8] + "..."
        )
    console.print(table)

@app.command("add")
def add_db(name: str = typer.Argument(..., help="Name of the agent")):
    path = Path(name).resolve()
    validate_work_dir(path)

    console.print(Panel("Add External Database Connection", style="bold blue"))
    
    db_type = Prompt.ask("Type", choices=["postgresql", "mysql", "mariadb"], default="postgresql")
    db_name = Prompt.ask("Database Name")
    host = Prompt.ask("Host", default="localhost")
    port = IntPrompt.ask("Port", default=5432 if db_type == "postgresql" else 3306)
    user = Prompt.ask("Username")
    password = Prompt.ask("Password", password=True)

    entry = {
        "name": db_name,
        "type": db_type,
        "username": user,
        "password": password,
        "port": port,
        "host": host,
        "generatedId": str(uuid.uuid4())
    }
    
    add_db_to_json(path, entry)
    console.print("[success]✔ Database added to configuration.[/success]")
    console.print("[info]Restart the agent to apply changes: [/info]" + f"portabase restart {name}")

@app.command("remove")
def remove_db(name: str = typer.Argument(..., help="Name of the agent")):
    path = Path(name).resolve()
    validate_work_dir(path)
    
    config = load_db_config(path)
    dbs = config.get("databases", [])
    
    if not dbs:
        console.print("[warning]No databases to remove.[/warning]")
        return

    options = [f"{db['name']} ({db['type']})" for db in dbs]
    choice = Prompt.ask("Which database to remove?", choices=options)
    
    index = options.index(choice)
    removed = dbs.pop(index)
    
    config["databases"] = dbs
    save_db_config(path, config)
    
    console.print(f"[success]✔ Removed {removed['name']}[/success]")
    console.print("[info]Restart the agent to apply changes.[/info]")