import os
import secrets
import uuid
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from core.config import add_db_to_json, load_db_config, write_env_file, write_file
from core.docker import (
    create_compose_file,
    ensure_network,
    run_compose,
)
from core.network import fetch_template
from core.utils import (
    check_system,
    console,
    get_free_port,
    get_random_hint,
    print_banner,
    validate_edge_key,
)
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


def agent(
    name: str = typer.Argument(..., help="Name of the agent (creates a folder)"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="Edge Key"),
    tz: str = typer.Option("UTC", "--tz", help="Timezone"),
    polling: int = typer.Option(5, "--polling", help="Polling frequency in seconds"),
    start: bool = typer.Option(False, "--start", "-s", help="Start immediately"),
):
    print_banner()
    check_system()
    ensure_network("portabase_network")

    path = Path(name).resolve()
    if path.exists():
        console.print(f"[warning]Directory '{name}' already exists.[/warning]")
        if not Confirm.ask("Overwrite?"):
            raise typer.Exit()

    path.mkdir(parents=True, exist_ok=True)
    project_name = name.lower().replace(" ", "-")

    if not key:
        key = Prompt.ask("[key]Edge Key[/key]")

    if not validate_edge_key(key):
        console.print(
            "[danger]✖ Invalid Edge Key. Please check the format (Base64 or JSON).[/danger]"
        )
        raise typer.Exit(1)

    if not tz or tz == "UTC":
        tz = Prompt.ask("Timezone", default="UTC")

    if polling == 5:
        polling = IntPrompt.ask("Polling frequency (seconds)", default=5)

    env_vars = {
        "EDGE_KEY": key,
        "PROJECT_NAME": project_name,
        "TZ": tz,
        "POLLING": str(polling),
    }

    raw_template = fetch_template("agent.yml")
    raw_template = raw_template.replace("${PROJECT_NAME}", project_name)

    services_to_add = {}
    volumes_to_add = []
    app_volumes = ["./databases.json:/config/config.json"]

    json_path = path / "databases.json"
    if not json_path.exists():
        write_file(json_path, '{"databases": []}')
        try:
            os.chmod(json_path, 0o666)
        except:
            pass

    console.print("")
    console.print(Panel("[bold]Database Setup[/bold]", style="cyan"))

    while Confirm.ask("Do you want to configure a database?", default=True):
        mode = Prompt.ask(
            "Configuration Mode", choices=["new", "existing"], default="new"
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

        if mode == "existing":
            console.print("[info]External/Existing Database Configuration[/info]")
            category = Prompt.ask("Category", choices=["SQL", "NoSQL"], default="SQL")

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
                db_name = Prompt.ask("Database Path (relative or absolute)")
                if not db_name.startswith("/"):
                    app_volumes.append(f"./{db_name}:/config/{db_name}")
                    container_path = f"/config/{db_name}"
                else:
                    container_path = db_name

                add_db_to_json(
                    path,
                    {
                        "name": friendly_name,
                        "database": container_path,
                        "type": db_type,
                        "generated_id": str(uuid.uuid4()),
                    },
                )
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

                add_db_to_json(
                    path,
                    {
                        "name": friendly_name,
                        "database": db_name,
                        "type": db_type,
                        "username": user,
                        "password": password,
                        "port": port,
                        "host": host,
                        "generated_id": str(uuid.uuid4()),
                    },
                )
            console.print("[success]✔ Added to config[/success]")

        else:
            console.print("[info]New Local Docker Container[/info]")
            category = Prompt.ask("Category", choices=["SQL", "NoSQL"], default="SQL")

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

            if db_engine == "sqlite":
                db_name = Prompt.ask("Database Name", default="local")
                if not db_name.endswith(".sqlite"):
                    db_name += ".sqlite"

                app_volumes.append(f"./{db_name}:/config/{db_name}")

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
                pg_port = get_free_port()
                db_user = "admin"
                db_pass = secrets.token_hex(8)
                db_name = f"pg_{secrets.token_hex(4)}"
                service_name = f"db-pg-{secrets.token_hex(2)}"

                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(pg_port)
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

                snippet_data = yaml.safe_load(snippet)
                services_to_add.update(
                    snippet_data.get("services", snippet_data)
                    if isinstance(snippet_data, dict)
                    else snippet_data
                )
                volumes_to_add.append(f"{service_name}-data")

                add_db_to_json(
                    path,
                    {
                        "name": db_name,
                        "database": db_name,
                        "type": "postgresql",
                        "username": db_user,
                        "password": db_pass,
                        "port": pg_port,
                        "host": "localhost",
                        "generated_id": str(uuid.uuid4()),
                    },
                )
                console.print(
                    f"[success]✔ Added Postgres container (Port {pg_port})[/success]"
                )

            elif db_engine == "mariadb" or db_engine == "mysql":
                mysql_port = get_free_port()
                db_user = "admin"
                db_pass = secrets.token_hex(8)
                db_name = f"mysql_{secrets.token_hex(4)}"
                service_name = f"db-mariadb-{secrets.token_hex(2)}"

                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(mysql_port)
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

                snippet_data = yaml.safe_load(snippet)
                services_to_add.update(
                    snippet_data.get("services", snippet_data)
                    if isinstance(snippet_data, dict)
                    else snippet_data
                )
                volumes_to_add.append(f"{service_name}-data")

                add_db_to_json(
                    path,
                    {
                        "name": db_name,
                        "database": db_name,
                        "type": db_engine,
                        "username": db_user,
                        "password": db_pass,
                        "port": mysql_port,
                        "host": "localhost",
                        "generated_id": str(uuid.uuid4()),
                    },
                )
                console.print(
                    f"[success]✔ Added MariaDB container (Port {mysql_port})[/success]"
                )

            elif db_engine == "mongodb":
                if db_variant == "with-auth":
                    mongo_port = get_free_port()
                    db_user = "admin"
                    db_pass = secrets.token_hex(8)
                    db_name = f"mongo_{secrets.token_hex(4)}"
                    service_name = f"db-mongo-auth-{secrets.token_hex(2)}"

                    var_prefix = service_name.upper().replace("-", "_")
                    env_vars[f"{var_prefix}_PORT"] = str(mongo_port)
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

                    snippet_data = yaml.safe_load(snippet)
                    services_to_add.update(
                        snippet_data.get("services", snippet_data)
                        if isinstance(snippet_data, dict)
                        else snippet_data
                    )
                    volumes_to_add.append(f"{service_name}-data")

                    add_db_to_json(
                        path,
                        {
                            "name": db_name,
                            "database": db_name,
                            "type": "mongodb",
                            "username": db_user,
                            "password": db_pass,
                            "port": mongo_port,
                            "host": "localhost",
                            "generated_id": str(uuid.uuid4()),
                        },
                    )
                    console.print(
                        f"[success]✔ Added MongoDB Auth container (Port {mongo_port})[/success]"
                    )
                else:
                    mongo_port = get_free_port()
                    db_name = f"mongo_{secrets.token_hex(4)}"
                    service_name = f"db-mongo-{secrets.token_hex(2)}"

                    var_prefix = service_name.upper().replace("-", "_")
                    env_vars[f"{var_prefix}_PORT"] = str(mongo_port)
                    env_vars[f"{var_prefix}_DB"] = db_name

                    snippet = (
                        AGENT_MONGODB_SNIPPET.replace("${SERVICE_NAME}", service_name)
                        .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                        .replace("${VOL_NAME}", f"{service_name}-data")
                        .replace("${DB_NAME}", f"${{{var_prefix}_DB}}")
                    )

                    snippet_data = yaml.safe_load(snippet)
                    services_to_add.update(
                        snippet_data.get("services", snippet_data)
                        if isinstance(snippet_data, dict)
                        else snippet_data
                    )
                    volumes_to_add.append(f"{service_name}-data")

                    add_db_to_json(
                        path,
                        {
                            "name": db_name,
                            "database": db_name,
                            "type": "mongodb",
                            "username": "",
                            "password": "",
                            "port": mongo_port,
                            "host": "localhost",
                            "generated_id": str(uuid.uuid4()),
                        },
                    )
                    console.print(
                        f"[success]✔ Added MongoDB container (Port {mongo_port})[/success]"
                    )

            elif db_engine == "redis":
                redis_port = get_free_port()
                db_name = f"redis_{secrets.token_hex(4)}"
                service_name = f"db-redis-{secrets.token_hex(2)}"

                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(redis_port)

                snippet = (
                    AGENT_REDIS_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                )

                snippet_data = yaml.safe_load(snippet)
                services_to_add.update(
                    snippet_data.get("services", snippet_data)
                    if isinstance(snippet_data, dict)
                    else snippet_data
                )
                volumes_to_add.append(f"{service_name}-data")

                add_db_to_json(
                    path,
                    {
                        "name": db_name,
                        "database": "0",
                        "type": "redis",
                        "username": "",
                        "password": "",
                        "port": redis_port,
                        "host": "localhost",
                        "generated_id": str(uuid.uuid4()),
                    },
                )
                console.print(
                    f"[success]✔ Added Redis container (Port {redis_port})[/success]"
                )

            elif db_engine == "redis-auth":
                redis_port = get_free_port()
                db_name = f"redis_{secrets.token_hex(4)}"
                service_name = f"db-redis-auth-{secrets.token_hex(2)}"
                db_pass = secrets.token_hex(8)

                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(redis_port)
                env_vars[f"{var_prefix}_PASS"] = db_pass

                snippet = (
                    AGENT_REDIS_AUTH_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                    .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                )

                snippet_data = yaml.safe_load(snippet)
                services_to_add.update(
                    snippet_data.get("services", snippet_data)
                    if isinstance(snippet_data, dict)
                    else snippet_data
                )
                volumes_to_add.append(f"{service_name}-data")

                add_db_to_json(
                    path,
                    {
                        "name": db_name,
                        "database": "0",
                        "type": "redis",
                        "username": "",
                        "password": db_pass,
                        "port": redis_port,
                        "host": "localhost",
                        "generated_id": str(uuid.uuid4()),
                    },
                )
                console.print(
                    f"[success]✔ Added Redis Auth container (Port {redis_port})[/success]"
                )

            elif db_engine == "valkey":
                valkey_port = get_free_port()
                db_name = f"valkey_{secrets.token_hex(4)}"
                service_name = f"db-valkey-{secrets.token_hex(2)}"

                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(valkey_port)

                snippet = (
                    AGENT_VALKEY_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                )

                snippet_data = yaml.safe_load(snippet)
                services_to_add.update(
                    snippet_data.get("services", snippet_data)
                    if isinstance(snippet_data, dict)
                    else snippet_data
                )
                volumes_to_add.append(f"{service_name}-data")

                add_db_to_json(
                    path,
                    {
                        "name": db_name,
                        "database": "0",
                        "type": "valkey",
                        "username": "",
                        "password": "",
                        "port": valkey_port,
                        "host": "localhost",
                        "generated_id": str(uuid.uuid4()),
                    },
                )
                console.print(
                    f"[success]✔ Added Valkey container (Port {valkey_port})[/success]"
                )

            elif db_engine == "valkey-auth":
                valkey_port = get_free_port()
                db_name = f"valkey_{secrets.token_hex(4)}"
                service_name = f"db-valkey-auth-{secrets.token_hex(2)}"
                db_pass = secrets.token_hex(8)

                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(valkey_port)
                env_vars[f"{var_prefix}_PASS"] = db_pass

                snippet = (
                    AGENT_VALKEY_AUTH_SNIPPET.replace("${SERVICE_NAME}", service_name)
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                    .replace("${VOL_NAME}", f"{service_name}-data")
                    .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                )

                snippet_data = yaml.safe_load(snippet)
                services_to_add.update(
                    snippet_data.get("services", snippet_data)
                    if isinstance(snippet_data, dict)
                    else snippet_data
                )
                volumes_to_add.append(f"{service_name}-data")

                add_db_to_json(
                    path,
                    {
                        "name": db_name,
                        "database": "0",
                        "type": "valkey",
                        "username": "",
                        "password": db_pass,
                        "port": valkey_port,
                        "host": "localhost",
                        "generated_id": str(uuid.uuid4()),
                    },
                )
                console.print(
                    f"[success]✔ Added Valkey Auth container (Port {valkey_port})[/success]"
                )

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("Property", style="bold cyan")
    summary.add_column("Value", style="white")

    summary.add_row("Agent Name", name)
    summary.add_row("Project ID", project_name)
    summary.add_row("Path", str(path))
    summary.add_row("Edge Key", f"{key[:10]}...{key[-10:]}" if len(key) > 20 else key)
    summary.add_row("Timezone", tz)
    summary.add_row("Polling", f"{polling}s")

    db_config = load_db_config(path)
    dbs = db_config.get("databases", [])
    if dbs:
        db_details = []
        for db in dbs:
            if db.get("type") == "sqlite":
                db_details.append(f"• {db['name']} (sqlite: {db['database']})")
            else:
                db_details.append(
                    f"• {db['name']} ({db['type']} on port {db.get('port', 'N/A')})"
                )

        summary.add_row("Databases", "\n".join(db_details))
    else:
        summary.add_row("Databases", "[dim]None configured[/dim]")

    summary.add_row("Files to Create", "• docker-compose.yml\n• .env\n• databases.json")

    console.print("")
    console.print(
        Panel(
            summary,
            title="[bold white]SUMMARY[/bold white]",
            border_style="bold blue",
            expand=False,
        )
    )
    console.print(
        "[dim]The agent will be configured in the directory above and ready for deployment.[/dim]\n"
    )

    if not Confirm.ask(
        "[bold]Apply this configuration and generate files?[/bold]", default=True
    ):
        console.print("[warning]Configuration cancelled.[/warning]")
        raise typer.Exit()

    create_compose_file(
        path=path,
        base_template_content=raw_template,
        extra_services=services_to_add,
        named_volumes=volumes_to_add,
        app_volumes=app_volumes,
    )

    write_env_file(path, env_vars)

    console.print(
        Panel(f"[bold white]AGENT READY: {name}[/bold white]", style="bold #5f00d7")
    )

    if start or Confirm.ask("Start agent now?", default=False):
        status_msg = f"[bold magenta]Starting...[/bold magenta]\n{get_random_hint()}"
        with console.status(status_msg, spinner="earth"):
            run_compose(path, ["up", "-d"])
        console.print(f"[bold green]✔ Agent {name} is running[/bold green]")
    else:
        console.print(f"[info]Run: portabase start {name}[/info]")
