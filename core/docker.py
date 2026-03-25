import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import typer
import yaml

from core.utils import console


def ensure_network(name: str):
    try:
        subprocess.run(
            ["docker", "network", "inspect", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except subprocess.CalledProcessError:
        subprocess.run(
            ["docker", "network", "create", name], stdout=subprocess.DEVNULL, check=True
        )


def run_compose(cwd: Path, args: list):
    try:
        project_name = cwd.name.lower().replace(" ", "_")
        cmd = ["docker", "compose", "-p", project_name] + args
        subprocess.run(cmd, cwd=cwd, check=True)
    except subprocess.CalledProcessError:
        console.print("[danger]Command failed.[/danger]")
        raise typer.Exit(1)


def update_compose_file(path: Path, service_snippet: str, volume_name: str = None):
    compose_path = path / "docker-compose.yml"
    if not compose_path.exists():
        return

    try:
        with open(compose_path, "r") as f:
            data = yaml.safe_load(f) or {}

        snippet_data = yaml.safe_load(service_snippet)

        if "services" not in data or data["services"] is None:
            data["services"] = {}

        data["services"].update(snippet_data)

        if volume_name:
            if "volumes" not in data or data["volumes"] is None:
                data["volumes"] = {}

            if volume_name not in data["volumes"]:
                data["volumes"][volume_name] = {}

        with open(compose_path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

    except yaml.YAMLError as exc:
        console.print(f"[danger]Error while loading YAML : {exc}[/danger]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[danger]Unexpected error : {e}[/danger]")
        raise typer.Exit(1)


def create_compose_file(
    path: Path,
    base_template_content: str,
    extra_services: Optional[Dict] = None,
    named_volumes: Optional[List[str]] = None,
    app_volumes: Optional[List[str]] = None,
):
    compose_path = path / "docker-compose.yml"

    try:
        data = yaml.safe_load(base_template_content) or {}

        if extra_services:
            if "services" not in data or data["services"] is None:
                data["services"] = {}
            data["services"].update(extra_services)

        if named_volumes:
            if "volumes" not in data or data["volumes"] is None:
                data["volumes"] = {}
            for vol in named_volumes:
                data["volumes"][vol] = {}

        if app_volumes and "services" in data and "app" in data["services"]:
            app_service = data["services"]["app"]
            if "volumes" not in app_service or app_service["volumes"] is None:
                app_service["volumes"] = []

            for vol in app_volumes:
                if vol not in app_service["volumes"]:
                    app_service["volumes"].append(vol)

        with open(compose_path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)

    except yaml.YAMLError as exc:
        console.print(f"[danger]Error while creating YAML : {exc}[/danger]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[danger]Unexpected error : {e}[/danger]")
        raise typer.Exit(1)
