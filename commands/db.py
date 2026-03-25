import secrets
import uuid
from pathlib import Path

import typer
import yaml
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from core.config import add_db_to_json, load_db_config, save_db_config, write_env_file
from core.docker import run_compose, update_compose_file
from core.utils import console, get_free_port, validate_work_dir
from templates.compose import (
    AGENT_MARIADB_SNIPPET,
    AGENT_MONGODB_AUTH_SNIPPET,
    AGENT_MONGODB_SNIPPET,
    AGENT_POSTGRES_SNIPPET,
    AGENT_REDIS_AUTH_SNIPPET,
    AGENT_REDIS_SNIPPET,
    AGENT_VALKEY_AUTH_SNIPPET,
    AGENT_VALKEY_SNIPPET,
)

app = typer.Typer(
    help="Manage databases configuration.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


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
    table.add_column("Display Name", style="cyan")
    table.add_column("Database", style="blue")
    table.add_column("Type", style="magenta")
    table.add_column("Host:Port", style="green")
    table.add_column("User", style="white")
    table.add_column("ID", style="dim")

    for db in dbs:
        db_type = db.get("type", "N/A")
        host_port = (
            "Local File"
            if db_type == "sqlite"
            else f"{db.get('host', 'N/A')}:{db.get('port', 'N/A')}"
        )
        username = "N/A" if db_type == "sqlite" else db.get("username", "N/A")

        table.add_row(
            db.get("name", "N/A"),
            db.get("database", db.get("name", "N/A")),
            db_type,
            host_port,
            username,
            db.get("generated_id", "")[:8] + "...",
        )
    console.print(table)


@app.command("add")
def add_db(name: str = typer.Argument(..., help="Name of the agent")):
    path = Path(name).resolve()
    validate_work_dir(path)

    console.print(Panel("Add Database Connection", style="bold blue"))

    mode = Prompt.ask(
        "Configuration Mode", choices=["new", "existing"], default="existing"
    )

    table = Table(
        title="Supported Databases", show_header=True, header_style="bold magenta"
    )
    table.add_column("Type", style="cyan")
    table.add_column("Engine", style="green")
    table.add_column("Description", style="dim")

    table.add_row("SQL", "postgresql", "PostgreSQL Database")
    table.add_row("SQL", "mysql", "MySQL Database")
    table.add_row("SQL", "mariadb", "MariaDB Database")
    table.add_row("SQL", "sqlite", "SQLite Database")
    table.add_row("", "", "")
    table.add_row("NoSQL", "mongodb", "MongoDB NoSQL")
    table.add_row("NoSQL", "redis", "Redis Key-Value Store")
    table.add_row("NoSQL", "valkey", "Valkey Key-Value Store")

    console.print(table)

    category = Prompt.ask("Category", choices=["SQL", "NoSQL"], default="SQL")

    if mode == "existing":
        if category == "SQL":
            db_type = Prompt.ask(
                "Type",
                choices=["postgresql", "mysql", "mariadb", "sqlite"],
                default="postgresql",
            )
        else:
            db_type = Prompt.ask(
                "Type",
                choices=["mongodb", "redis", "valkey"],
                default="mongodb",
            )

        friendly_name = Prompt.ask("Display Name", default="External DB")

        if db_type == "sqlite":
            db_name = Prompt.ask("Database Path (e.g. /data/db.sqlite)")
            entry = {
                "name": friendly_name,
                "database": db_name,
                "type": db_type,
                "generated_id": str(uuid.uuid4()),
            }
        else:
            db_name = Prompt.ask("Database Name")
            host = Prompt.ask("Host", default="localhost")

            default_port = 5432
            if db_type in ["mysql", "mariadb"]:
                default_port = 3306
            elif db_type == "mongodb":
                default_port = 27017
            elif db_type in ["redis", "valkey"]:
                default_port = 6379

            port = IntPrompt.ask("Port", default=default_port)
            user = Prompt.ask("Username")
            password = Prompt.ask("Password", password=True)

            entry = {
                "name": friendly_name,
                "database": db_name,
                "type": db_type,
                "username": user,
                "password": password,
                "port": port,
                "host": host,
                "generated_id": str(uuid.uuid4()),
            }

        add_db_to_json(path, entry)
    else:
        if category == "SQL":
            db_engine = Prompt.ask(
                "Engine",
                choices=["postgresql", "mysql", "mariadb", "sqlite"],
                default="postgresql",
            )
            db_variant = "standard"
        else:
            db_engine = Prompt.ask(
                "Engine",
                choices=["mongodb", "redis", "valkey"],
                default="mongodb",
            )
            db_variant = Prompt.ask(
                "Variant", choices=["standard", "with-auth"], default="standard"
            )
            if db_variant == "with-auth":
                db_engine = f"{db_engine}-auth"

        env_vars = {}
        snippet = ""
        service_name = ""
        db_name = ""
        db_user = ""
        db_pass = ""
        db_port = 0

        if db_engine == "sqlite":
            db_name = Prompt.ask("Database Name", default="local")
            if not db_name.endswith(".sqlite"):
                db_name += ".sqlite"

            compose_path = path / "docker-compose.yml"
            if compose_path.exists():
                try:
                    with open(compose_path, "r") as f:
                        data = yaml.safe_load(f) or {}

                    if "services" in data and "app" in data["services"]:
                        app_service = data["services"]["app"]

                        if (
                            "volumes" not in app_service
                            or app_service["volumes"] is None
                        ):
                            app_service["volumes"] = []

                        new_volume = f"./{db_name}:/config/{db_name}"
                        if new_volume not in app_service["volumes"]:
                            app_service["volumes"].append(new_volume)

                    with open(compose_path, "w") as f:
                        yaml.safe_dump(
                            data, f, default_flow_style=False, sort_keys=False
                        )
                except Exception as e:
                    console.print(
                        f"[danger]Error while updating the SQLite database : {e}[/danger]"
                    )
                    raise typer.Exit(1)

            add_db_to_json(
                path,
                {
                    "name": db_name,
                    "database": f"/config/{db_name}",
                    "type": "sqlite",
                    "generated_id": str(uuid.uuid4()),
                },
            )
            console.print(f"[success]✔ Added SQLite database ({db_name})[/success]")

        elif db_engine == "postgresql":
            db_port = get_free_port()
            db_user = "admin"
            db_pass = secrets.token_hex(8)
            db_name = f"pg_{secrets.token_hex(4)}"
            service_name = f"db-pg-{secrets.token_hex(2)}"
            var_prefix = service_name.upper().replace("-", "_")
            env_vars[f"{var_prefix}_PORT"] = str(db_port)
            env_vars[f"{var_prefix}_DB"] = db_name
            env_vars[f"{var_prefix}_USER"] = db_user
            env_vars[f"{var_prefix}_PASS"] = db_pass
            snippet = (
                AGENT_POSTGRES_SNIPPET.replace("${SERVICE_NAME}", service_name)
                .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                .replace("${VOL_NAME}", f"{service_name}-data")
                .replace("${DB_NAME}", f"${{{var_prefix}_DB}}")
                .replace("${USER}", f"${{{var_prefix}_USER}}")
                .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
            )

        elif db_engine in ["mysql", "mariadb"]:
            db_port = get_free_port()
            db_user = "admin"
            db_pass = secrets.token_hex(8)
            db_name = f"mysql_{secrets.token_hex(4)}"
            service_name = f"db-mariadb-{secrets.token_hex(2)}"
            var_prefix = service_name.upper().replace("-", "_")
            env_vars[f"{var_prefix}_PORT"] = str(db_port)
            env_vars[f"{var_prefix}_DB"] = db_name
            env_vars[f"{var_prefix}_USER"] = db_user
            env_vars[f"{var_prefix}_PASS"] = db_pass
            snippet = (
                AGENT_MARIADB_SNIPPET.replace("${SERVICE_NAME}", service_name)
                .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                .replace("${VOL_NAME}", f"{service_name}-data")
                .replace("${DB_NAME}", f"${{{var_prefix}_DB}}")
                .replace("${USER}", f"${{{var_prefix}_USER}}")
                .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
            )

        elif db_engine == "mongodb":
            db_port = get_free_port()
            db_name = f"mongo_{secrets.token_hex(4)}"
            if db_variant == "with-auth":
                db_user = "admin"
                db_pass = secrets.token_hex(8)
                service_name = f"db-mongo-auth-{secrets.token_hex(2)}"
                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(db_port)
                env_vars[f"{var_prefix}_DB"] = db_name
                env_vars[f"{var_prefix}_USER"] = db_user
                env_vars[f"{var_prefix}_PASS"] = db_pass
                snippet = (
                    AGENT_MONGODB_AUTH_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                    .replace("${DB_NAME}", f"${{{var_prefix}_DB}}")
                    .replace("${USER}", f"${{{var_prefix}_USER}}")
                    .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                )
            else:
                service_name = f"db-mongo-{secrets.token_hex(2)}"
                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(db_port)
                env_vars[f"{var_prefix}_DB"] = db_name
                snippet = (
                    AGENT_MONGODB_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                    .replace("${DB_NAME}", f"${{{var_prefix}_DB}}")
                )

        elif "redis" in db_engine:
            db_port = get_free_port()
            db_name = f"redis_{secrets.token_hex(4)}"
            service_name = f"db-redis-{'auth-' if 'auth' in db_engine else ''}{secrets.token_hex(2)}"
            var_prefix = service_name.upper().replace("-", "_")
            env_vars[f"{var_prefix}_PORT"] = str(db_port)

            if "auth" in db_engine:
                db_pass = secrets.token_hex(8)
                env_vars[f"{var_prefix}_PASS"] = db_pass
                snippet = (
                    AGENT_REDIS_AUTH_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                    .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                )
            else:
                snippet = (
                    AGENT_REDIS_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                )

        elif "valkey" in db_engine:
            db_port = get_free_port()
            db_name = f"valkey_{secrets.token_hex(4)}"
            service_name = f"db-valkey-{'auth-' if 'auth' in db_engine else ''}{secrets.token_hex(2)}"
            var_prefix = service_name.upper().replace("-", "_")
            env_vars[f"{var_prefix}_PORT"] = str(db_port)

            if "auth" in db_engine:
                db_pass = secrets.token_hex(8)
                env_vars[f"{var_prefix}_PASS"] = db_pass
                snippet = (
                    AGENT_VALKEY_AUTH_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                    .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                )
            else:
                snippet = (
                    AGENT_VALKEY_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                )

        if snippet:
            update_compose_file(path, snippet, f"{service_name}-data")
            write_env_file(path, env_vars)

            db_type_for_json = db_engine.split("-")[0]
            add_db_to_json(
                path,
                {
                    "name": db_name,
                    "database": "0"
                    if db_type_for_json in ["redis", "valkey"]
                    else db_name,
                    "type": db_type_for_json,
                    "username": db_user,
                    "password": db_pass,
                    "port": db_port,
                    "host": "localhost",
                    "generated_id": str(uuid.uuid4()),
                },
            )

    console.print("[success]✔ Database added to configuration.[/success]")
    console.print(
        "[info]Restart the agent to apply changes: [/info]"
        + f"portabase restart {name}"
    )


@app.command("remove")
def remove_db(name: str = typer.Argument(..., help="Name of the agent")):
    """Remove a database connection from configuration."""
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
