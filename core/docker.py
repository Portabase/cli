import subprocess
from pathlib import Path

import typer

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

    import re

    with open(compose_path, "r") as f:
        content = f.read()

    def find_top_level(text, key):
        match = re.search(rf"^{key}:", text, re.MULTILINE)
        return match.start() if match else -1

    networks_pos = find_top_level(content, "networks")
    volumes_pos = find_top_level(content, "volumes")

    insert_pos = networks_pos if networks_pos != -1 else volumes_pos
    if insert_pos == -1:
        insert_pos = len(content)

    new_content = (
        content[:insert_pos].rstrip()
        + "\n"
        + service_snippet
        + "\n"
        + content[insert_pos:]
    )

    if volume_name:
        vol_snippet = f"  {volume_name}:\n"
        volumes_pos = find_top_level(new_content, "volumes")
        if volumes_pos != -1:
            next_section = re.search(
                r"^[a-z]+:", new_content[volumes_pos + 8 :], re.MULTILINE
            )
            if next_section:
                v_insert_pos = volumes_pos + 8 + next_section.start()
            else:
                v_insert_pos = len(new_content)

            new_content = (
                new_content[:v_insert_pos].rstrip()
                + "\n"
                + vol_snippet
                + "\n"
                + new_content[v_insert_pos:]
            )
        else:
            new_content = new_content.rstrip() + f"\n\nvolumes:\n{vol_snippet}"

    with open(compose_path, "w") as f:
        f.write(new_content.replace("\n\n\n", "\n\n"))
