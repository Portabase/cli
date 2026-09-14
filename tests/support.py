from __future__ import annotations

import json
import os
import struct
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.errors import NetworkError
from core.fields import Field
from core.specs import DatabaseSpec

ROOT = Path(__file__).resolve().parent.parent

EDGE_KEY_PAYLOAD = {"serverUrl": "http://x", "agentId": "a", "masterKeyB64": "k"}
AGENT_ENV = {"TZ": "UTC", "EDGE_KEY": "x", "LOG_LEVEL": "info", "POLLING": "5"}
DASHBOARD_BASE = {
    "HOST_PORT": "8887",
    "PROJECT_SECRET": "s",
    "PROJECT_URL": "http://localhost:8887",
    "PROJECT_NAME": "pb",
    "TZ": "UTC",
    "LOG_LEVEL": "info",
}
DASHBOARD_PG = {
    "POSTGRES_DB": "pb",
    "POSTGRES_USER": "pb",
    "POSTGRES_PASSWORD": "p",
    "PG_PORT": "5433",
    "DATABASE_URL": "postgresql://pb:p@db:5432/pb",
}
DASHBOARD_MODES = {
    "external": {**DASHBOARD_BASE, **DASHBOARD_PG, "POSTGRES_HOST": "db"},
    "internal": DASHBOARD_BASE,
    "custom": {**DASHBOARD_BASE, **DASHBOARD_PG, "POSTGRES_HOST": "remote"},
}
EXISTING_ANSWERS = {
    "host": "db.example",
    "port": "1234",
    "database": "app",
    "username": "u",
    "password": "p",
}


@dataclass
class FakeHttp:
    json: dict[str, Any] = field(default_factory=dict)
    text: dict[str, str] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def _lookup(self, table: dict[str, Any], url: str) -> Any:
        self.calls.append(url)
        if url not in table:
            raise NetworkError(f"GET {url} failed: 404")
        return table[url]

    def get_json(self, url: str) -> Any:
        return self._lookup(self.json, url)

    def get_text(self, url: str) -> str:
        return self._lookup(self.text, url)

    def download(
        self,
        url: str,
        dest: Path,
        on_progress: Callable[[int], None] | None = None,
        *,
        timeout: float = 30.0,
    ) -> int:
        data = self._lookup(self.files, url)
        dest.write_bytes(data)
        if on_progress:
            on_progress(len(data))
        return len(data)

    def content_length(self, url: str) -> int | None:
        data = self.files.get(url)
        return len(data) if data is not None else None


@dataclass
class Rendered:
    spec: DatabaseSpec
    doc: dict[str, Any]
    env: dict[str, str]
    databases: list[dict[str, Any]]

    @property
    def agent(self) -> dict[str, Any]:
        return self.doc["services"]["agent"]

    @property
    def service(self) -> dict[str, Any]:
        return self.doc["services"][self.spec.host]

    def var(self, suffix: str) -> str:
        return f"${{{self.spec.env_prefix}_{suffix}}}"


def encrypt(plain: bytes, key: bytes, chunk_size: int = 4) -> bytes:
    """Build a .enc file the way the Portabase agent writes one."""
    base_nonce = os.urandom(8)
    header = {
        "cipher": "AES-256-GCM",
        "base_nonce": list(base_nonce),
        "chunk_size": chunk_size,
    }
    out = json.dumps(header).encode() + b"\n"
    aes = AESGCM(key)
    for index, start in enumerate(range(0, len(plain), chunk_size)):
        nonce = base_nonce + struct.pack(">I", index)
        ciphertext = aes.encrypt(nonce, plain[start : start + chunk_size], None)
        out += struct.pack(">I", len(ciphertext)) + ciphertext
    return out


def field_specs(fields: Iterable[Field]) -> list[tuple[str, str, Any]]:
    return [(field.name, field.kind, field.default) for field in fields]


def agent_service(*volumes: str, inline: bool = False) -> dict[str, Any]:
    """The agent service as rendered with no option turned on."""
    environment = (
        dict(AGENT_ENV) if inline else {key: f"${{{key}}}" for key in AGENT_ENV}
    )
    return {
        "restart": "unless-stopped",
        "image": "portabase/agent:latest",
        "volumes": ["./databases.json:/config/config.json", *volumes],
        "environment": environment,
        "networks": ["portabase"],
    }
