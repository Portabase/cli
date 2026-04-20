import os
import secrets
import uuid
from pathlib import Path
from typing import Optional

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
    get_free_port,
    get_random_hint,
    print_banner,
    validate_edge_key,
)
from templates.compose import (
    AGENT_FIREBIRD_SNIPPET,
    AGENT_MARIADB_SNIPPET,
    AGENT_MONGODB_AUTH_SNIPPET,
    AGENT_MONGODB_SNIPPET,
    AGENT_POSTGRES_SNIPPET,
)


def agent(
    name: str = typer.Argument(..., help="Name of the agent (creates a folder)"),
    key: Optional[str] = typer.Option(None, "--key", "-k", help="Edge Key"),
    tz: str = typer.Option("UTC", "--tz", help="Timezone"),
    polling: int = typer.Option(5, "--polling", help="Polling frequency in seconds"),
    env: str = typer.Option("production", "--env", help="Application environment"),
    data_path: str = typer.Option("/data", "--data-path", help="Internal data path"),
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

    if env == "production":
        env = Prompt.ask(
            "Environment",
            choices=["production", "staging", "development"],
            default="production",
        )

    if data_path == "/data":
        data_path = Prompt.ask("Internal Data Path", default="/data")

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
        "PROJECT_NAME": project_name,
        "TZ": tz,
        "POLLING": str(polling),
        "APP_ENV": env,
        "DATA_PATH": data_path,
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
        mode = Prompt.ask(
            "Configuration Mode", choices=["new", "existing"], default="new"
        )

        if mode == "existing":
            console.print("[info]External/Existing Database Configuration[/info]")
            category = Prompt.ask("Category", choices=["SQL", "NoSQL"], default="SQL")

            if category == "SQL":
                db_type = Prompt.ask(
                    "Type",
                    choices=["postgresql", "mysql", "mariadb", "sqlite", "firebird"],
                    default="postgresql",
                )
            else:
                db_type = Prompt.ask(
                    "Type",
                    choices=["mongodb"],
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
                    choices=["postgresql", "mysql", "mariadb", "sqlite", "firebird"],
                    default="postgresql",
                )
                db_variant = "standard"
            else:
                db_engine = Prompt.ask(
                    "Engine",
                    choices=["mongodb"],
                    default="mongodb",
                )
                db_variant = Prompt.ask(
                    "Type", choices=["standard", "with-auth"], default="standard"
                )

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
                            "port": mongo_port,
                            "host": "localhost",
                            "generated_id": str(uuid.uuid4()),
                        },
                    )
                    console.print(
                        f"[success]✔ Added MongoDB container (Port {mongo_port})[/success]"
                    )

            elif db_engine == "firebird":
                fb_port = get_free_port()
                db_user = "alice"
                db_pass = secrets.token_hex(8)
                db_name = "mirror.fdb"
                service_name = f"db-firebird-{secrets.token_hex(2)}"

                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(fb_port)
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

                extra_services += snippet
                volumes_list.append(f"{service_name}-data")

                add_db_to_json(
                    path,
                    {
                        "name": db_name,
                        "database": db_name,
                        "type": "firebird",
                        "username": db_user,
                        "password": db_pass,
                        "port": fb_port,
                        "host": "localhost",
                        "generated_id": str(uuid.uuid4()),
                    },
                )
                console.print(
                    f"[success]✔ Added Firebird container (Port {fb_port})[/success]"
                )

    if volumes_list:
        for vol in volumes_list:
            extra_volumes += f"  {vol}:\n"

    final_compose = raw_template.replace("{{EXTRA_SERVICES}}", extra_services)
    final_compose = final_compose.replace("{{EXTRA_VOLUMES}}", extra_volumes)
    final_compose = final_compose.replace("${PROJECT_NAME}", project_name)

    vols_str = "\n".join([f"      - {v}" for v in app_volumes])
    final_compose = final_compose.replace(
        "      - ./databases.json:/config/config.json", vols_str
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
    summary.add_row("Environment", env)

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
