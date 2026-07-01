import re
import secrets
import uuid
from pathlib import Path

import questionary
import typer
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from core.config import add_db_to_json, load_db_config, save_db_config, write_env_file
from core.docker import ensure_network
from core.utils import (
    console,
    generate_password,
    get_free_port,
    questionary_style,
    validate_work_dir,
)
from templates.compose import (
    AGENT_FIREBIRD_SNIPPET,
    AGENT_MARIADB_SNIPPET,
    AGENT_MONGODB_AUTH_SNIPPET,
    AGENT_MONGODB_SNIPPET,
    AGENT_MSSQL_SNIPPET,
    AGENT_POSTGRES_SNIPPET,
    AGENT_REDIS_AUTH_SNIPPET,
    AGENT_REDIS_SNIPPET,
    AGENT_VALKEY_AUTH_SNIPPET,
    AGENT_VALKEY_SNIPPET,
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
    ensure_network("portabase_network")

    console.print(Panel("Add Database to Agent", style="bold blue"))

    while True:
        mode = Prompt.ask(
            "Configuration Mode",
            choices=["new", "existing", "back"],
            default="existing",
        )

        if mode == "back":
            break

        if mode == "existing":
            db_type = questionary.select(
                "Select Database Type",
                choices=[
                    "back",
                    "postgresql",
                    "postgresql-cluster",
                    "mysql",
                    "mariadb",
                    "sqlite",
                    "firebird",
                    "mongodb",
                    "mssql",
                ],
                style=questionary_style,
            ).ask()

            if db_type == "back":
                continue

            if not db_type:
                raise typer.Exit()

            if db_type == "postgresql-cluster":
                console.print(
                    "[warning]⚠ Postgres Cluster requires a superuser. "
                    "Cluster backup/restore uses pg_dumpall, which dumps all "
                    "databases and global objects (roles, tablespaces). "
                    "The provided user must be a Postgres superuser.[/warning]"
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
                port = IntPrompt.ask(
                    "Port",
                    default=5432
                    if db_type in ["postgresql", "postgresql-cluster"]
                    else (
                        3050
                        if db_type == "firebird"
                        else (
                            1433
                            if db_type == "mssql"
                            else (3306 if db_type in ["mysql", "mariadb"] else 27017)
                        )
                    ),
                )
                user = Prompt.ask("Username")
                password = questionary.password(
                    "Password", style=questionary_style
                ).ask()
                if password is None:
                    raise typer.Exit()

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
            break
        else:
            db_engine = questionary.select(
                "Select Database Engine",
                choices=[
                    "back",
                    "postgresql",
                    "postgresql-cluster",
                    "mysql",
                    "mariadb",
                    "sqlite",
                    "firebird",
                    "mongodb",
                    "redis",
                    "valkey",
                    "mssql",
                ],
                style=questionary_style,
            ).ask()

            if db_engine == "back":
                continue

            if not db_engine:
                raise typer.Exit()

            db_variant = "no-auth"
            if db_engine in ["mongodb", "redis", "valkey"]:
                engine_display = {
                    "mongodb": "MongoDB",
                    "redis": "Redis",
                    "valkey": "Valkey",
                }[db_engine]
                db_variant = questionary.select(
                    f"Select {engine_display} Variant",
                    choices=["back", "no-auth", "with-auth"],
                    default="no-auth",
                    style=questionary_style,
                ).ask()

                if db_variant == "back":
                    continue

                if not db_variant:
                    raise typer.Exit()

            env_vars = {}
            snippet = ""
            service_name = ""
            db_name = ""
            db_container_path = ""
            db_user = ""
            db_pass = ""
            db_port = 0

            if db_engine == "sqlite":
                db_name = Prompt.ask("Database Name", default="local")
                if not db_name.endswith(".sqlite"):
                    db_name += ".sqlite"

                compose_path = path / "docker-compose.yml"
                if compose_path.exists():
                    content = compose_path.read_text()
                    lines = content.splitlines(keepends=True)
                    new_lines = []
                    in_app_service = False
                    inserted = False

                    for line in lines:
                        new_lines.append(line)
                        if not inserted:
                            if re.search(r"^  app:", line):
                                in_app_service = True
                            elif in_app_service and re.search(r"^    volumes:", line):
                                new_lines.append(
                                    f"      - ./{db_name}:/config/{db_name}\n"
                                )
                                in_app_service = False
                                inserted = True
                            elif in_app_service and re.search(r"^  [a-zA-Z]", line):
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

            elif db_engine in ["postgresql", "postgresql-cluster"]:
                db_port = get_free_port()
                db_user = "admin"
                db_pass = generate_password(16)
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
                db_pass = generate_password(16)
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
                    db_pass = generate_password(16)
                    service_name = f"db-mongo-auth-{secrets.token_hex(2)}"
                    var_prefix = service_name.upper().replace("-", "_")
                    env_vars[f"{var_prefix}_PORT"] = str(db_port)
                    env_vars[f"{var_prefix}_DB"] = db_name
                    env_vars[f"{var_prefix}_USER"] = db_user
                    env_vars[f"{var_prefix}_PASS"] = db_pass
                    snippet = (
                        AGENT_MONGODB_AUTH_SNIPPET.replace(
                            "${SERVICE_NAME}", service_name
                        )
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
                db_pass = generate_password(16)
                db_root_pass = generate_password(16)
                db_name = "mirror.fdb"
                db_container_path = f"/var/lib/firebird/data/{db_name}"
                service_name = f"db-firebird-{secrets.token_hex(2)}"
                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(db_port)
                env_vars[f"{var_prefix}_DB"] = db_name
                env_vars[f"{var_prefix}_USER"] = db_user
                env_vars[f"{var_prefix}_PASS"] = db_pass
                env_vars[f"{var_prefix}_ROOT_PASS"] = db_root_pass
                snippet = (
                    AGENT_FIREBIRD_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                    .replace("${DB_NAME}", f"${{{var_prefix}_DB}}")
                    .replace("${USER}", f"${{{var_prefix}_USER}}")
                    .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                    .replace("${ROOT_PASSWORD}", f"${{{var_prefix}_ROOT_PASS}}")
                )

            elif db_engine == "redis":
                db_port = get_free_port()
                db_name = f"redis_{secrets.token_hex(4)}"
                if db_variant == "with-auth":
                    db_pass = generate_password(16)
                    service_name = f"db-redis-auth-{secrets.token_hex(2)}"
                    var_prefix = service_name.upper().replace("-", "_")
                    env_vars[f"{var_prefix}_PORT"] = str(db_port)
                    env_vars[f"{var_prefix}_PASS"] = db_pass
                    snippet = (
                        AGENT_REDIS_AUTH_SNIPPET.replace(
                            "${SERVICE_NAME}", service_name
                        )
                        .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                        .replace("${VOL_NAME}", f"{service_name}-data")
                        .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                    )
                else:
                    service_name = f"db-redis-{secrets.token_hex(2)}"
                    var_prefix = service_name.upper().replace("-", "_")
                    env_vars[f"{var_prefix}_PORT"] = str(db_port)
                    snippet = (
                        AGENT_REDIS_SNIPPET.replace("${SERVICE_NAME}", service_name)
                        .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                        .replace("${VOL_NAME}", f"{service_name}-data")
                    )

            elif db_engine == "valkey":
                db_port = get_free_port()
                db_name = f"valkey_{secrets.token_hex(4)}"
                if db_variant == "with-auth":
                    db_pass = generate_password(16)
                    service_name = f"db-valkey-auth-{secrets.token_hex(2)}"
                    var_prefix = service_name.upper().replace("-", "_")
                    env_vars[f"{var_prefix}_PORT"] = str(db_port)
                    env_vars[f"{var_prefix}_PASS"] = db_pass
                    snippet = (
                        AGENT_VALKEY_AUTH_SNIPPET.replace(
                            "${SERVICE_NAME}", service_name
                        )
                        .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                        .replace("${VOL_NAME}", f"{service_name}-data")
                        .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                    )
                else:
                    service_name = f"db-valkey-{secrets.token_hex(2)}"
                    var_prefix = service_name.upper().replace("-", "_")
                    env_vars[f"{var_prefix}_PORT"] = str(db_port)
                    snippet = (
                        AGENT_VALKEY_SNIPPET.replace("${SERVICE_NAME}", service_name)
                        .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                        .replace("${VOL_NAME}", f"{service_name}-data")
                    )

            elif db_engine == "mssql":
                db_port = get_free_port()
                db_pass = generate_password(16)
                db_name = "master"
                service_name = f"db-mssql-{secrets.token_hex(2)}"
                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(db_port)
                env_vars[f"{var_prefix}_PASS"] = db_pass
                snippet = (
                    AGENT_MSSQL_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                    .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                )

            compose_path = path / "docker-compose.yml"
            if compose_path.exists():
                content = compose_path.read_text()

                vol_match = re.search(r"^volumes:", content, re.MULTILINE)
                net_match = re.search(r"^networks:", content, re.MULTILINE)

                if vol_match:
                    insert_pos = vol_match.start()
                elif net_match:
                    insert_pos = net_match.start()
                else:
                    insert_pos = len(content)

                content = content[:insert_pos] + snippet + "\n" + content[insert_pos:]

                vol_match = re.search(r"^volumes:", content, re.MULTILINE)
                net_match = re.search(r"^networks:", content, re.MULTILINE)
                vol_entry = f"  {service_name}-data:\n"

                if vol_match:
                    if net_match and net_match.start() > vol_match.start():
                        content = (
                            content[: net_match.start()]
                            + vol_entry
                            + content[net_match.start() :]
                        )
                    else:
                        if not content.endswith("\n"):
                            content += "\n"
                        content += vol_entry
                else:
                    if not content.endswith("\n"):
                        content += "\n"
                    content += "\nvolumes:\n" + vol_entry

                with open(compose_path, "w") as f:
                    f.write(content)

        if db_engine != "sqlite":
            write_env_file(path, env_vars)
            add_db_to_json(
                path,
                {
                    "name": "mirror.fdb" if db_engine == "firebird" else db_name,
                    "database": db_container_path
                    if db_engine == "firebird"
                    else ("0" if db_engine in ["redis", "valkey"] else db_name),
                    "type": db_engine,
                    "username": "sa" if db_engine == "mssql" else db_user,
                    "password": db_pass,
                    "port": 5432
                    if db_engine in ["postgresql", "postgresql-cluster"]
                    else (
                        3050
                        if db_engine == "firebird"
                        else (
                            3306
                            if db_engine in ["mysql", "mariadb"]
                            else (
                                1433
                                if db_engine == "mssql"
                                else (
                                    6379 if db_engine in ["redis", "valkey"] else 27017
                                )
                            )
                        )
                    ),
                    "host": service_name,
                    "generated_id": str(uuid.uuid4()),
                },
            )
        break

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
