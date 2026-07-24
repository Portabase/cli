import os
import shutil
import subprocess
from pathlib import Path

import typer

from core.config import get_config_value
from core.utils import console

# In-container path the agent app always talks to. Podman's socket is
# Docker-API-compatible, so we map the host socket to this path regardless
# of the engine.
CONTAINER_SOCKET = "/var/run/docker.sock"

# Memoized runtime description so we probe subprocess only once per invocation.
_runtime = None


def _detect_podman_socket() -> str:
    """Best-effort resolution of the host Podman socket path."""
    try:
        result = subprocess.run(
            ["podman", "info", "--format", "{{.Host.RemoteSocket.Path}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        path = result.stdout.strip()
        if path:
            return path
    except Exception:
        pass

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return f"{runtime_dir}/podman/podman.sock"
    return "/run/podman/podman.sock"


def _compose_command(engine: str, binary: str) -> list:
    """Prefer `<engine> compose`; fall back to standalone `podman-compose`."""
    try:
        subprocess.run(
            [binary, "compose", "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return [binary, "compose"]
    except Exception:
        if engine == "podman":
            standalone = shutil.which("podman-compose")
            if standalone:
                return [standalone]
        # Fall back to the plugin form; the actual command will surface any
        # missing-provider error to the user at run time.
        return [binary, "compose"]


def _build_runtime(engine: str, binary: str) -> dict:
    if engine == "podman":
        socket = _detect_podman_socket()
    else:
        socket = "/var/run/docker.sock"
    return {
        "engine": engine,
        "bin": binary,
        "compose": _compose_command(engine, binary),
        "socket": socket,
    }


def get_runtime() -> dict:
    """Resolve the active container engine + compose command. Memoized.

    Returns a dict like::

        {"engine": "docker", "bin": "/usr/bin/docker",
         "compose": ["docker", "compose"], "socket": "/var/run/docker.sock"}
    """
    global _runtime
    if _runtime is not None:
        return _runtime

    override = os.environ.get("PORTABASE_ENGINE") or get_config_value(
        "container_engine"
    )
    if override:
        engine = override.lower()
        if engine not in ("docker", "podman"):
            console.print(
                f"[danger]✖ Invalid container engine '[bold]{override}[/bold]'. "
                "Use 'docker' or 'podman'.[/danger]"
            )
            raise typer.Exit(1)
        binary = shutil.which(engine)
        if binary is None:
            console.print(
                f"[danger]✖ Configured engine '[bold]{engine}[/bold]' not found "
                "(binary missing).[/danger]"
            )
            raise typer.Exit(1)
        _runtime = _build_runtime(engine, binary)
        return _runtime

    for engine in ("docker", "podman"):
        binary = shutil.which(engine)
        if binary:
            _runtime = _build_runtime(engine, binary)
            return _runtime

    console.print(
        "[danger]✖ No container engine found. Docker or Podman is required.[/danger]"
    )
    raise typer.Exit(1)


def compose_cmd(project_name: str, args: list) -> list:
    """Full compose argv for the resolved engine, including project name."""
    rt = get_runtime()
    return rt["compose"] + ["-p", project_name] + args


def socket_mount() -> str:
    """Host:container bind-mount string for the resolved engine's socket."""
    rt = get_runtime()
    return f"{rt['socket']}:{CONTAINER_SOCKET}"


def ensure_network(name: str):
    rt = get_runtime()
    try:
        subprocess.run(
            [rt["bin"], "network", "inspect", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except subprocess.CalledProcessError:
        subprocess.run(
            [rt["bin"], "network", "create", name],
            stdout=subprocess.DEVNULL,
            check=True,
        )


def run_compose(cwd: Path, args: list):
    try:
        project_name = cwd.name.lower().replace(" ", "_")
        cmd = compose_cmd(project_name, args)
        subprocess.run(cmd, cwd=cwd, check=True)
    except subprocess.CalledProcessError:
        console.print("[danger]Command failed.[/danger]")
        raise typer.Exit(1)
