import secrets
import uuid
from pathlib import Path

import typer
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from core.config import add_db_to_json, load_db_config, save_db_config, write_env_file
from core.utils import console, get_free_port, validate_work_dir
from templates.compose import (
    AGENT_FIREBIRD_SNIPPET,
    AGENT_MARIADB_SNIPPET,
    AGENT_MONGODB_AUTH_SNIPPET,
    AGENT_MONGODB_SNIPPET,
    AGENT_POSTGRES_SNIPPET,
)

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

    console.print(Panel("Add Database to Agent", style="bold blue"))

    mode = Prompt.ask(
        "Configuration Mode", choices=["new", "existing"], default="existing"
    )
    category = Prompt.ask("Category", choices=["SQL", "NoSQL"], default="SQL")

    if mode == "existing":
        if category == "SQL":
            db_type = Prompt.ask(
                "Type",
                choices=["postgresql", "mysql", "mariadb", "sqlite", "firebird"],
                default="postgresql",
            )
        else:
            db_type = Prompt.ask("Type", choices=["mongodb"], default="mongodb")

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
            port = IntPrompt.ask(
                "Port",
                default=5432
                if db_type == "postgresql"
                else (
                    3050
                    if db_type == "firebird"
                    else (3306 if db_type in ["mysql", "mariadb"] else 27017)
                ),
            )
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
                choices=["postgresql", "mysql", "mariadb", "sqlite", "firebird"],
                default="postgresql",
            )
        else:
            db_engine = Prompt.ask("Engine", choices=["mongodb"], default="mongodb")
            db_variant = Prompt.ask(
                "Type", choices=["standard", "with-auth"], default="standard"
            )

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
                with open(compose_path, "r") as f:
                    lines = f.readlines()

                new_lines = []
                in_app_service = False
                in_volumes = False
                for line in lines:
                    new_lines.append(line)
                    if "app:" in line:
                        in_app_service = True
                    if in_app_service and "volumes:" in line:
                        in_volumes = True
                    if in_volumes and "- ./databases.json" in line:
                        new_lines.append(f"      - ./{db_name}:/config/{db_name}\n")
                        in_volumes = False
                        in_app_service = False

                with open(compose_path, "w") as f:
                    f.writelines(new_lines)

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

        elif db_engine == "firebird":
            db_port = get_free_port()
            db_user = "alice"
            db_pass = secrets.token_hex(8)
            db_name = "mirror.fdb"
            service_name = f"db-firebird-{secrets.token_hex(2)}"
            var_prefix = service_name.upper().replace("-", "_")
            env_vars[f"{var_prefix}_PORT"] = str(db_port)
            env_vars[f"{var_prefix}_DB"] = db_name
            env_vars[f"{var_prefix}_USER"] = db_user
            env_vars[f"{var_prefix}_PASS"] = db_pass
            snippet = (
                AGENT_FIREBIRD_SNIPPET.replace("${SERVICE_NAME}", service_name)
                .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                .replace("${VOL_NAME}", f"{service_name}-data")
                .replace("${DB_NAME}", f"${{{var_prefix}_DB}}")
                .replace("${USER}", f"${{{var_prefix}_USER}}")
                .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
            )

        compose_path = path / "docker-compose.yml"
        if compose_path.exists():
            with open(compose_path, "r") as f:
                content = f.read()

            if "\nnetworks:" in content:
                insert_pos = content.find("\nnetworks:") + 1
            elif content.startswith("networks:"):
                insert_pos = 0
            else:
                insert_pos = len(content)

            new_content = content[:insert_pos] + snippet + "\n" + content[insert_pos:]

            vol_snippet = f"  {service_name}-data:\n"

            vol_pos = -1
            if "\nvolumes:" in new_content:
                vol_pos = new_content.find("\nvolumes:") + 1
            elif new_content.startswith("volumes:"):
                vol_pos = 0

            if vol_pos != -1:
                end_of_volumes = new_content.find("\nnetworks:", vol_pos)
                if end_of_volumes == -1:
                    end_of_volumes = len(new_content)
                else:
                    end_of_volumes += 1

                new_content = (
                    new_content[:end_of_volumes]
                    + vol_snippet
                    + new_content[end_of_volumes:]
                )
            else:
                new_content += f"\nvolumes:\n{vol_snippet}"

            with open(compose_path, "w") as f:
                f.write(new_content)

        write_env_file(path, env_vars)
        add_db_to_json(
            path,
            {
                "name": db_name,
                "database": db_name,
                "type": db_engine,
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
