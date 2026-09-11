from __future__ import annotations

import platform
import shutil
import subprocess
import time
from pathlib import Path

from core.errors import DockerError
from core.utils import slugify_project_name

_START_COMMANDS = {
    "Linux": ["sudo", "systemctl", "start", "docker"],
    "Darwin": ["open", "--background", "-a", "Docker"],
    "Windows": ["cmd", "/c", "start", "docker"],
}


class DockerRunner:
    def __init__(self, docker_bin: str | None = None) -> None:
        self._bin = docker_bin

    @property
    def binary(self) -> str:
        if self._bin is None:
            found = shutil.which("docker")
            if found is None:
                raise DockerError(
                    "Docker not found (binary missing).",
                    hint="Install Docker: https://docs.docker.com/get-docker/",
                )
            self._bin = found
        return self._bin

    def available(self) -> bool:
        return shutil.which("docker") is not None

    def daemon_running(self) -> bool:
        try:
            subprocess.run(
                [self.binary, "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, OSError):
            return False

    def start_daemon(self, *, wait_seconds: int = 20) -> bool:
        cmd = _START_COMMANDS.get(platform.system())
        if cmd is None:
            return False
        try:
            subprocess.run(cmd, check=True)
        except (subprocess.CalledProcessError, OSError) as e:
            raise DockerError(f"Failed to start Docker: {e}", cause=e) from e
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if self.daemon_running():
                return True
            time.sleep(2)
        return False

    def ensure_network(self, name: str) -> None:
        inspect = subprocess.run(
            [self.binary, "network", "inspect", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if inspect.returncode == 0:
            return
        try:
            subprocess.run(
                [self.binary, "network", "create", name],
                stdout=subprocess.DEVNULL,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise DockerError(
                f"Could not create Docker network '{name}'.", cause=e
            ) from e

    def remove_volume(self, name: str) -> bool:
        proc = subprocess.run(
            [self.binary, "volume", "rm", name],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return True
        if "no such volume" in (proc.stderr or "").lower():
            return False
        raise DockerError(f"Could not remove volume '{name}': {proc.stderr.strip()}")

    @staticmethod
    def project_name(cwd: Path) -> str:
        return slugify_project_name(cwd.resolve().name)

    def compose(
        self,
        cwd: Path,
        args: list[str],
        *,
        check: bool = True,
        capture: bool = False,
    ) -> subprocess.CompletedProcess:
        cmd = [self.binary, "compose", "-p", self.project_name(cwd), *args]
        try:
            return subprocess.run(
                cmd,
                cwd=cwd,
                check=check,
                capture_output=capture,
                text=capture,
            )
        except subprocess.CalledProcessError as e:
            raise DockerError(
                f"docker compose {' '.join(args)} failed (exit {e.returncode}).",
                hint=f"Run it manually in {cwd} to see the full output.",
                cause=e,
            ) from e
        except OSError as e:
            raise DockerError(f"Could not run docker: {e}", cause=e) from e
