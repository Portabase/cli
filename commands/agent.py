import os
import secrets
import uuid
from pathlib import Path
from typing import Optional

import questionary
import typer
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from core.config import add_db_to_json, load_db_config, write_env_file, write_file
from core.docker import ensure_network, run_compose
from core.network import fetch_template
from core.utils import (
    check_system,
    console,
    generate_password,
    get_free_port,
    get_random_hint,
    print_banner,
    questionary_style,
    validate_edge_key,
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

    raw_template = fetch_template("agent.yml")

    if "{{EXTRA_SERVICES}}" not in raw_template:
        if "\nnetworks:" in raw_template:
            raw_template = raw_template.replace(
                "\nnetworks:", "\n\n{{EXTRA_SERVICES}}\n\nnetworks:"
            )
        else:
            raw_template += "\n\n{{EXTRA_SERVICES}}\n"

    if "{{EXTRA_VOLUMES}}" not in raw_template:
        if "\nnetworks:" in raw_template:
            raw_template = raw_template.replace(
                "\nnetworks:", "\n\n{{EXTRA_VOLUMES}}\n\nnetworks:"
            )
        else:
            raw_template += "\n\n{{EXTRA_VOLUMES}}\n"

    env_vars = {
        "EDGE_KEY": key,
        "TZ": tz,
        "POLLING": str(polling),
        "LOG_LEVEL": "info",
    }

    extra_services = ""
    extra_volumes = "volumes:\n"
    app_volumes = ["./databases.json:/config/config.json"]
    volumes_list = []

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
        while True:
            mode = Prompt.ask(
                "Configuration Mode", choices=["new", "existing"], default="new"
            )

            if mode == "existing":
                console.print("[info]External/Existing Database Configuration[/info]")
                db_type = questionary.select(
                    "Select Database Type",
                    choices=[
                        "back",
                        "postgresql",
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

                if db_type == "back":
                    continue

                if not db_type:
                    raise typer.Exit()

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
                    port = IntPrompt.ask(
                        "Port",
                        default=5432
                        if db_type == "postgresql"
                        else (
                            3050
                            if db_type == "firebird"
                            else (
                                1433
                                if db_type == "mssql"
                                else (
                                    3306 if db_type in ["mysql", "mariadb"] else 27017
                                )
                            )
                        ),
                    )
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
                break

            else:
                console.print("[info]New Local Docker Container[/info]")
                db_engine = questionary.select(
                    "Select Database Engine",
                    choices=[
                        "back",
                        "postgresql",
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
                        style=questionary_style,
                    ).ask()

                    if db_variant == "back":
                        continue

                    if not db_variant:
                        raise typer.Exit()

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
                    console.print(
                        f"[success]✔ Added SQLite database ({db_name})[/success]"
                    )

                elif db_engine == "postgresql":
                    pg_port = get_free_port()
                    db_user = "admin"
                    db_pass = generate_password(16)
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

                    extra_services += snippet
                    volumes_list.append(f"{service_name}-data")

                    add_db_to_json(
                        path,
                        {
                            "name": db_name,
                            "database": db_name,
                            "type": "postgresql",
                            "username": db_user,
                            "password": db_pass,
                            "port": 5432,
                            "host": service_name,
                            "generated_id": str(uuid.uuid4()),
                        },
                    )

                    console.print(
                        f"[success]✔ Added Postgres container (Port {pg_port})[/success]"
                    )

                elif db_engine == "mariadb" or db_engine == "mysql":
                    mysql_port = get_free_port()
                    db_user = "admin"
                    db_pass = generate_password(16)
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

                    extra_services += snippet
                    volumes_list.append(f"{service_name}-data")

                    add_db_to_json(
                        path,
                        {
                            "name": db_name,
                            "database": db_name,
                            "type": db_engine,
                            "username": db_user,
                            "password": db_pass,
                            "port": 3306,
                            "host": service_name,
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
                        db_pass = generate_password(16)
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

                        extra_services += snippet
                        volumes_list.append(f"{service_name}-data")

                        add_db_to_json(
                            path,
                            {
                                "name": db_name,
                                "database": db_name,
                                "type": "mongodb",
                                "username": db_user,
                                "password": db_pass,
                                "port": 27017,
                                "host": service_name,
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
                            AGENT_MONGODB_SNIPPET.replace(
                                "${SERVICE_NAME}", service_name
                            )
                            .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                            .replace("${VOL_NAME}", f"{service_name}-data")
                            .replace("${DB_NAME}", f"${{{var_prefix}_DB}}")
                        )
                        extra_services += snippet
                        volumes_list.append(f"{service_name}-data")

                        add_db_to_json(
                            path,
                            {
                                "name": db_name,
                                "database": db_name,
                                "type": "mongodb",
                                "username": "",
                                "password": "",
                                "port": 27017,
                                "host": service_name,
                                "generated_id": str(uuid.uuid4()),
                            },
                        )

                        console.print(
                            f"[success]✔ Added MongoDB container (Port {mongo_port})[/success]"
                        )

                elif db_engine == "redis":
                    if db_variant == "with-auth":
                        redis_port = get_free_port()
                        db_name = f"redis_{secrets.token_hex(4)}"
                        service_name = f"db-redis-auth-{secrets.token_hex(2)}"
                        db_pass = generate_password(16)

                        var_prefix = service_name.upper().replace("-", "_")
                        env_vars[f"{var_prefix}_PORT"] = str(redis_port)
                        env_vars[f"{var_prefix}_PASS"] = db_pass

                        snippet = (
                            AGENT_REDIS_AUTH_SNIPPET.replace(
                                "${SERVICE_NAME}", service_name
                            )
                            .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                            .replace("${VOL_NAME}", f"{service_name}-data")
                            .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                        )

                        extra_services += snippet
                        volumes_list.append(f"{service_name}-data")

                        add_db_to_json(
                            path,
                            {
                                "name": db_name,
                                "database": "0",
                                "type": "redis",
                                "username": "",
                                "password": db_pass,
                                "port": 6379,
                                "host": service_name,
                                "generated_id": str(uuid.uuid4()),
                            },
                        )
                        console.print(
                            f"[success]✔ Added Redis Auth container (Port {redis_port})[/success]"
                        )
                    else:
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

                        extra_services += snippet
                        volumes_list.append(f"{service_name}-data")

                        add_db_to_json(
                            path,
                            {
                                "name": db_name,
                                "database": "0",
                                "type": "redis",
                                "username": "",
                                "password": "",
                                "port": 6379,
                                "host": service_name,
                                "generated_id": str(uuid.uuid4()),
                            },
                        )
                        console.print(
                            f"[success]✔ Added Redis container (Port {redis_port})[/success]"
                        )

                elif db_engine == "valkey":
                    if db_variant == "with-auth":
                        valkey_port = get_free_port()
                        db_name = f"valkey_{secrets.token_hex(4)}"
                        service_name = f"db-valkey-auth-{secrets.token_hex(2)}"
                        db_pass = generate_password(16)

                        var_prefix = service_name.upper().replace("-", "_")
                        env_vars[f"{var_prefix}_PORT"] = str(valkey_port)
                        env_vars[f"{var_prefix}_PASS"] = db_pass

                        snippet = (
                            AGENT_VALKEY_AUTH_SNIPPET.replace(
                                "${SERVICE_NAME}", service_name
                            )
                            .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                            .replace("${VOL_NAME}", f"{service_name}-data")
                            .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                        )

                        extra_services += snippet
                        volumes_list.append(f"{service_name}-data")

                        add_db_to_json(
                            path,
                            {
                                "name": db_name,
                                "database": "0",
                                "type": "valkey",
                                "username": "",
                                "password": db_pass,
                                "port": 6379,
                                "host": service_name,
                                "generated_id": str(uuid.uuid4()),
                            },
                        )
                        console.print(
                            f"[success]✔ Added Valkey Auth container (Port {valkey_port})[/success]"
                        )
                    else:
                        valkey_port = get_free_port()
                        db_name = f"valkey_{secrets.token_hex(4)}"
                        service_name = f"db-valkey-{secrets.token_hex(2)}"

                        var_prefix = service_name.upper().replace("-", "_")
                        env_vars[f"{var_prefix}_PORT"] = str(valkey_port)

                        snippet = (
                            AGENT_VALKEY_SNIPPET.replace(
                                "${SERVICE_NAME}", service_name
                            )
                            .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                            .replace("${VOL_NAME}", f"{service_name}-data")
                        )

                        extra_services += snippet
                        volumes_list.append(f"{service_name}-data")

                        add_db_to_json(
                            path,
                            {
                                "name": db_name,
                                "database": "0",
                                "type": "valkey",
                                "username": "",
                                "password": "",
                                "port": 6379,
                                "host": service_name,
                                "generated_id": str(uuid.uuid4()),
                            },
                        )
                        console.print(
                            f"[success]✔ Added Valkey container (Port {valkey_port})[/success]"
                        )

                elif db_engine == "firebird":
                    fb_port = get_free_port()
                    db_user = "alice"
                    db_pass = generate_password(16)
                    db_root_pass = generate_password(16)
                    db_name = "mirror.fdb"
                    db_container_path = f"/var/lib/firebird/data/{db_name}"
                    service_name = f"db-firebird-{secrets.token_hex(2)}"

                    var_prefix = service_name.upper().replace("-", "_")
                    env_vars[f"{var_prefix}_PORT"] = str(fb_port)
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

                    extra_services += snippet
                    volumes_list.append(f"{service_name}-data")

                    add_db_to_json(
                        path,
                        {
                            "name": db_name,
                            "database": db_container_path,
                            "type": "firebird",
                            "username": db_user,
                            "password": db_pass,
                            "port": 3050,
                            "host": service_name,
                            "generated_id": str(uuid.uuid4()),
                        },
                    )
                    console.print(
                        f"[success]✔ Added Firebird container (Port {fb_port})[/success]"
                    )

                elif db_engine == "mssql":
                    mssql_port = get_free_port()
                    db_pass = generate_password(16)
                    db_name = "master"
                    service_name = f"db-mssql-{secrets.token_hex(2)}"

                    var_prefix = service_name.upper().replace("-", "_")
                    env_vars[f"{var_prefix}_PORT"] = str(mssql_port)
                    env_vars[f"{var_prefix}_PASS"] = db_pass

                    snippet = (
                        AGENT_MSSQL_SNIPPET.replace("${SERVICE_NAME}", service_name)
                        .replace("${PORT}", f"${{{var_prefix}_PORT}}")
                        .replace("${VOL_NAME}", f"{service_name}-data")
                        .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")
                    )

                    extra_services += snippet
                    volumes_list.append(f"{service_name}-data")

                    add_db_to_json(
                        path,
                        {
                            "name": "MSSQL",
                            "database": db_name,
                            "type": "mssql",
                            "username": "sa",
                            "password": db_pass,
                            "port": 1433,
                            "host": service_name,
                            "generated_id": str(uuid.uuid4()),
                        },
                    )
                    console.print(
                        f"[success]✔ Added MSSQL container (Port {mssql_port})[/success]"
                    )
                break

    if volumes_list:
        for vol in volumes_list:
            extra_volumes += f"  {vol}:\n"

    final_compose = raw_template.replace("{{EXTRA_SERVICES}}", extra_services)
    final_compose = final_compose.replace("{{EXTRA_VOLUMES}}", extra_volumes)

    vols_str = "\n".join([f"      - {v}" for v in app_volumes])
    final_compose = final_compose.replace(
        "      - ./databases.json:/config/config.json", vols_str
    )

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column("Property", style="bold cyan")
    summary.add_column("Value", style="white")

    summary.add_row("Agent Name", name)
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
            title="[bold white]PROPOSED CONFIGURATION[/bold white]",
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

    write_file(path / "docker-compose.yml", final_compose)
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
