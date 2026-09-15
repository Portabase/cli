from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.config import GlobalConfig
from core.errors import NetworkError, UpdateError
from core.version import UNKNOWN, is_prerelease, parse_version
from services.http import HttpClient

GITHUB_REPO = "Portabase/cli"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
CACHE_TTL = 24 * 3600


@dataclass(frozen=True)
class Release:
    tag: str
    assets: dict[str, str]
    prerelease: bool

    @classmethod
    def from_api(cls, data: dict) -> Release:
        return cls(
            tag=str(data.get("tag_name", "")).lstrip("v"),
            assets={
                asset["name"]: asset["browser_download_url"]
                for asset in data.get("assets", [])
            },
            prerelease=bool(data.get("prerelease", False)),
        )


def platform_asset_name() -> str:
    system = platform.system().lower()
    system = "macos" if system == "darwin" else system
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    name = f"portabase_{system}_{arch}"
    return name + ".exe" if system == "windows" else name


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


class UpdateChecker:
    def __init__(self, http: HttpClient, config: GlobalConfig, current: str) -> None:
        self.http = http
        self.config = config
        self.current = current
        self.cache_file = config.cache_dir / "release.json"

    @property
    def include_prerelease(self) -> bool:
        channel = self.config.update_channel
        if channel:
            return channel == "beta"
        return is_prerelease(self.current)

    def fetch_latest(self) -> Release | None:
        if self.include_prerelease:
            releases = self.http.get_json(RELEASES_URL)
            return Release.from_api(releases[0]) if releases else None
        return Release.from_api(self.http.get_json(f"{RELEASES_URL}/latest"))

    def latest(self, *, force: bool = False) -> Release | None:
        if not force:
            cached = self._read_cache()
            if cached is not None:
                return cached
        try:
            release = self.fetch_latest()
        except NetworkError:
            return None
        if release is not None:
            self._write_cache(release)
        return release

    def available(self, *, force: bool = False) -> str | None:
        if self.current == UNKNOWN:
            return None
        release = self.latest(force=force)
        if release is None:
            return None
        if parse_version(release.tag) > parse_version(self.current):
            return release.tag
        return None

    def _read_cache(self) -> Release | None:
        try:
            with open(self.cache_file, encoding="utf-8") as file:
                data = json.load(file)
            if time.time() - float(data.get("checked_at", 0)) > CACHE_TTL:
                return None
            if data.get("channel_pre") != self.include_prerelease:
                return None
            return Release(
                tag=data["tag"],
                assets=data.get("assets", {}),
                prerelease=bool(data.get("prerelease")),
            )
        except (OSError, ValueError, KeyError):
            return None

    def _write_cache(self, release: Release) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as file:
                json.dump(
                    {
                        "checked_at": time.time(),
                        "channel_pre": self.include_prerelease,
                        "tag": release.tag,
                        "assets": release.assets,
                        "prerelease": release.prerelease,
                    },
                    file,
                )
        except OSError:
            pass


class Updater:
    CHECKSUMS_ASSET = "checksums.txt"

    def __init__(self, http: HttpClient, current: str) -> None:
        self.http = http
        self.current = current

    def target_path(self) -> Path:
        if is_frozen():
            return Path(sys.executable).resolve()
        if platform.system().lower() == "windows":
            return Path(os.environ.get("APPDATA", "")) / "Portabase" / "portabase.exe"
        default = Path("/usr/local/bin/portabase")
        if default.exists():
            return default
        return Path.home() / ".local" / "bin" / "portabase"

    def download(
        self, release: Release, on_progress: Callable[[int], None] | None = None
    ) -> Path:
        name = platform_asset_name()
        url = release.assets.get(name)
        if url is None:
            available = ", ".join(sorted(release.assets))
            raise UpdateError(
                f"No binary for this platform ({name}) in release {release.tag}.",
                hint=f"Available: {available}" if available else None,
            )
        fd, tmp = tempfile.mkstemp(prefix="portabase_update_")
        os.close(fd)
        tmp_path = Path(tmp)
        try:
            self.http.download(url, tmp_path, on_progress, timeout=60)
            self._verify(release, name, tmp_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        return tmp_path

    def expected_size(self, release: Release) -> int | None:
        url = release.assets.get(platform_asset_name())
        return self.http.content_length(url) if url else None

    def _verify(self, release: Release, name: str, path: Path) -> None:
        url = release.assets.get(self.CHECKSUMS_ASSET)
        if url is None:
            raise UpdateError(
                f"Release {release.tag} has no {self.CHECKSUMS_ASSET}; "
                "refusing to install."
            )
        expected = None
        for line in self.http.get_text(url).splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                expected = parts[0].lower()
        if expected is None:
            raise UpdateError(
                f"{name} not listed in {self.CHECKSUMS_ASSET}; refusing to install."
            )
        digest = hashlib.sha256()
        with open(path, "rb") as file:
            for chunk in iter(lambda: file.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise UpdateError(
                "Checksum mismatch for downloaded binary; refusing to install."
            )

    def install(self, tmp: Path, target: Path) -> None:
        system = platform.system().lower()
        if system != "windows":
            tmp.chmod(0o755)
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = target.with_name(target.name + ".old")
        writable = os.access(target.parent, os.W_OK) and (
            not target.exists() or os.access(target, os.W_OK)
        )
        try:
            if writable or system == "windows":
                if target.exists():
                    backup.unlink(missing_ok=True)
                    target.rename(backup)
                shutil.move(str(tmp), str(target))
            else:
                if target.exists():
                    subprocess.run(["sudo", "mv", str(target), str(backup)], check=True)
                subprocess.run(["sudo", "mv", str(tmp), str(target)], check=True)
                subprocess.run(["sudo", "chmod", "+x", str(target)], check=True)
        except (OSError, subprocess.CalledProcessError) as error:
            raise UpdateError(
                f"Could not install to {target}: {error}", cause=error
            ) from error
