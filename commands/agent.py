import typer
import secrets
import uuid
import os
from pathlib import Path
from typing import Optional
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt
from core.utils import console, print_banner, check_system, get_free_port
from core.config import write_file, write_env_file, add_db_to_json
from core.docker import ensure_network, run_compose
from core.network import fetch_template
from templates.compose import AGENT_POSTGRES_SNIPPET, AGENT_MARIADB_SNIPPET


def agent(
        name: str = typer.Argument(..., help="Name of the agent (creates a folder)"),
        key: Optional[str] = typer.Option(None, "--key", "-k", help="Edge Key"),
        start: bool = typer.Option(False, "--start", "-s", help="Start immediately")
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

    raw_template = fetch_template("agent.yml")

    env_vars = {
        "EDGE_KEY": key,
        "PROJECT_NAME": project_name
    }

    extra_services = ""
    extra_volumes = "volumes:\n"
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
        mode = Prompt.ask("Configuration Mode", choices=["new", "existing"], default="docker")

        if mode == "new":
            console.print("[info]External/Existing Database Configuration[/info]")
            db_type = Prompt.ask("Type", choices=["postgresql", "mysql", "mariadb", "mongodb"], default="postgresql")
            friendly_name = Prompt.ask("Display Name", default="External DB")
            db_name = Prompt.ask("Database Name")
            host = Prompt.ask("Host", default="localhost")
            port = IntPrompt.ask("Port", default=5432 if db_type == "postgresql" else 3306)
            user = Prompt.ask("Username")
            password = Prompt.ask("Password", password=True)

            add_db_to_json(path, {
                "name": friendly_name,
                "database": db_name,
                "type": db_type,
                "username": user,
                "password": password,
                "port": port,
                "host": host,
                "generated_id": str(uuid.uuid4())
            })
            console.print("[success]✔ Added to config[/success]")

        else:
            console.print("[info]New Local Docker Container[/info]")
            db_engine = Prompt.ask("Engine", choices=["postgresql", "mysql", "mariadb", "mongodb-auth", "mongodb"], default="postgresql")

            if db_engine == "postgresql":
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

                snippet = AGENT_POSTGRES_SNIPPET \
                    .replace("${SERVICE_NAME}", service_name) \
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}") \
                    .replace("${VOL_NAME}", f"{service_name}-data") \
                    .replace("${DB_NAME}", f"${{{var_prefix}_DB}}") \
                    .replace("${USER}", f"${{{var_prefix}_USER}}") \
                    .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")

                extra_services += snippet
                volumes_list.append(f"{service_name}-data")

                add_db_to_json(path, {
                    "name": db_name,
                    "database": db_name,
                    "type": "postgresql",
                    "username": db_user,
                    "password": db_pass,
                    "port": pg_port,
                    "host": "localhost",
                    "generated_id": str(uuid.uuid4())
                })
                console.print(f"[success]✔ Added Postgres container (Port {pg_port})[/success]")

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

                snippet = AGENT_MARIADB_SNIPPET \
                    .replace("${SERVICE_NAME}", service_name) \
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}") \
                    .replace("${VOL_NAME}", f"{service_name}-data") \
                    .replace("${DB_NAME}", f"${{{var_prefix}_DB}}") \
                    .replace("${USER}", f"${{{var_prefix}_USER}}") \
                    .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")

                extra_services += snippet
                volumes_list.append(f"{service_name}-data")

                add_db_to_json(path, {
                    "name": db_name,
                    "database": db_name,
                    "type": db_engine,
                    "username": db_user,
                    "password": db_pass,
                    "port": mysql_port,
                    "host": "localhost",
                    "generated_id": str(uuid.uuid4())
                })
                console.print(f"[success]✔ Added MariaDB container (Port {mysql_port})[/success]")

            elif db_engine == "mongodb-auth":
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

                snippet = AGENT_MARIADB_SNIPPET \
                    .replace("${SERVICE_NAME}", service_name) \
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}") \
                    .replace("${VOL_NAME}", f"{service_name}-data") \
                    .replace("${DB_NAME}", f"${{{var_prefix}_DB}}") \
                    .replace("${USER}", f"${{{var_prefix}_USER}}") \
                    .replace("${PASSWORD}", f"${{{var_prefix}_PASS}}")

                extra_services += snippet
                volumes_list.append(f"{service_name}-data")

                add_db_to_json(path, {
                    "name": db_name,
                    "database": db_name,
                    "type": "mongodb",
                    "username": db_user,
                    "password": db_pass,
                    "port": mongo_port,
                    "host": "localhost",
                    "generated_id": str(uuid.uuid4())
                })
                console.print(f"[success]✔ Added MongoDB Auth container (Port {mongo_port})[/success]")


            elif db_engine == "mongodb":
                mongo_port = get_free_port()
                db_name = f"mongo_{secrets.token_hex(4)}"
                service_name = f"db-mongo-{secrets.token_hex(2)}"

                var_prefix = service_name.upper().replace("-", "_")
                env_vars[f"{var_prefix}_PORT"] = str(mongo_port)
                env_vars[f"{var_prefix}_DB"] = db_name

                snippet = AGENT_MARIADB_SNIPPET \
                    .replace("${SERVICE_NAME}", service_name) \
                    .replace("${PORT}", f"${{{var_prefix}_PORT}}") \
                    .replace("${VOL_NAME}", f"{service_name}-data") \
                    .replace("${DB_NAME}", f"${{{var_prefix}_DB}}") \

                extra_services += snippet
                volumes_list.append(f"{service_name}-data")

                add_db_to_json(path, {
                    "name": db_name,
                    "database": db_name,
                    "type": "mongodb",
                    "username": "",
                    "password": "",
                    "port": mongo_port,
                    "host": "localhost",
                    "generated_id": str(uuid.uuid4())
                })
                console.print(f"[success]✔ Added MongoDB container (Port {mongo_port})[/success]")



    if volumes_list:
        for vol in volumes_list:
            extra_volumes += f"  {vol}:\n"

    final_compose = raw_template.replace("{{EXTRA_SERVICES}}", extra_services)
    final_compose = final_compose.replace("{{EXTRA_VOLUMES}}", extra_volumes)

    final_compose = final_compose.replace("${PROJECT_NAME}", project_name)

    write_file(path / "docker-compose.yml", final_compose)
    write_env_file(path, env_vars)

    console.print(Panel(f"[bold white]AGENT READY: {name}[/bold white]", style="bold #5f00d7"))

    if start or Confirm.ask("Start agent now?", default=False):
        with console.status("[bold magenta]Starting...[/bold magenta]", spinner="earth"):
            run_compose(path, ["up", "-d"])
        console.print(f"[bold green]✔ Agent {name} is running[/bold green]")
    else:
        console.print(f"[info]Run: portabase start {name}[/info]")
