from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from core.errors import ConfigError, ValidationError
from core.specs import DatabaseSpec
from engines.base import DbEngine
from engines.sqlite import SqliteEngine
from services import auth_providers as ap
from services import settings as cfg
from services.compose_facts import CA_BUNDLE_IN_CONTAINER, ComposeFacts
from services.envfile import EnvFile

ProjectKind = Literal["agent", "dashboard"]
ProviderKind = Literal["oidc", "oauth"]
DATABASES_FILE = "databases.json"
COMPOSE_FILE = "docker-compose.yml"
ENV_FILE = ".env"


def detect_kind(path: Path) -> ProjectKind:
    if (path / DATABASES_FILE).exists():
        return "agent"
    env = EnvFile.load(path / ENV_FILE)
    if env.get("PROJECT_SECRET") is not None:
        return "dashboard"
    raise ConfigError(
        f"{path} is not a Portabase agent or dashboard folder.",
        hint="Expected databases.json (agent) or a .env with PROJECT_SECRET (dashboard).",
    )


def _opt_str(entry: dict[str, Any], key: str) -> str | None:
    value = entry.get(key)
    return str(value) if value not in (None, "") else None


def spec_from_entry(entry: dict[str, Any], env: EnvFile) -> DatabaseSpec:
    engine = str(entry.get("type", ""))
    host = entry.get("host")
    managed, host_port, root_password = False, None, None
    if host:
        prefix = str(host).upper().replace("-", "_")
        raw_port = env.get(f"{prefix}_PORT")
        if raw_port and raw_port.isdigit():
            managed, host_port = True, int(raw_port)
            root_password = env.get(f"{prefix}_ROOT_PASS")
    port = entry.get("port")
    return DatabaseSpec(
        id=str(entry.get("generated_id") or DbEngine.new_id()),
        engine=engine,
        name=str(entry.get("name", "")),
        managed=managed,
        host=str(host) if host else None,
        port=int(port) if port not in (None, "") else None,
        host_port=host_port,
        database=str(entry["database"]) if entry.get("database") is not None else None,
        username=str(entry["username"]) if entry.get("username") is not None else None,
        password=_opt_str(entry, "password"),
        root_password=root_password,
        path=_opt_str(entry, "database") if engine == "sqlite" else None,
        volume=_opt_str(entry, "volume_name"),
        container=_opt_str(entry, "container_name"),
        options=dict(entry.get("options") or {}),
    )


@dataclass
class AgentProject:
    path: Path
    env: EnvFile
    databases: list[DatabaseSpec] = field(default_factory=list)
    host_gateway: bool = False

    @classmethod
    def load(cls, path: Path) -> AgentProject:
        path = path.resolve()
        env_path, db_path = path / ENV_FILE, path / DATABASES_FILE
        if not env_path.exists() or not db_path.exists():
            raise ConfigError(
                f"Not a Portabase agent folder: {path}",
                hint=f"Expected {ENV_FILE} and {DATABASES_FILE}.",
            )
        env = EnvFile.load(env_path)
        try:
            data = json.loads(db_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ConfigError(f"{db_path} is not valid JSON.", cause=e) from e
        entries = data.get("databases", []) if isinstance(data, dict) else []
        databases = [spec_from_entry(e, env) for e in entries if isinstance(e, dict)]
        facts = ComposeFacts(path / COMPOSE_FILE)
        project = cls(path, env, databases, facts.host_gateway)
        project._ca_bundle = facts.ca_bundle
        project.validate()
        return project

    @classmethod
    def create(
        cls, path: Path, env_vars: dict[str, str], *, host_gateway: bool
    ) -> AgentProject:
        path.mkdir(parents=True, exist_ok=True)
        env = EnvFile.load(path / ENV_FILE)
        env.merge(env_vars)
        return cls(path, env, [], host_gateway)

    @property
    def managed(self) -> list[DatabaseSpec]:
        return [d for d in self.databases if d.managed]

    @property
    def needs_docker_socket(self) -> bool:
        return any(d.engine == "docker-volume" for d in self.databases)

    @property
    def sqlite_mounts(self) -> list[tuple[str, str]]:
        mounts: list[tuple[str, str]] = []
        for d in self.databases:
            if d.engine == "sqlite":
                m = SqliteEngine.mount_for(d)
                if m and m not in mounts:
                    mounts.append(m)
        return mounts

    def validate(self) -> None:
        bundle = self.ca_bundle
        if bundle and not (self.path / bundle).exists() and not Path(bundle).exists():
            raise ValidationError(
                f"CA bundle not found: {bundle}",
                hint=f"Path is resolved from {self.path}; use an absolute path otherwise.",
            )
        seen: set[str] = set()
        for d in self.managed:
            if d.host in seen:
                raise ConfigError(
                    f"Two managed databases share the service name '{d.host}'."
                )
            seen.add(d.host or "")

    def add(self, spec: DatabaseSpec, engine: DbEngine) -> None:
        if spec.managed:
            self.env.merge(engine.env_vars(spec))
        self.databases.append(spec)
        self.validate()

    def remove(self, spec: DatabaseSpec, engine: DbEngine) -> None:
        self.databases = [d for d in self.databases if d.id != spec.id]
        if spec.managed and spec.host:
            self.env.remove_prefix(spec.env_prefix)

    registry = cfg.AGENT

    def setting(self, name: str) -> Any:
        setting = self.registry.get(name)
        if setting.env is None:
            return getattr(self, name)
        return setting.from_env(self.env.get(setting.env))

    def settings(self) -> dict[str, Any]:
        return {s.name: self.setting(s.name) for s in self.registry}

    def set(self, name: str, value: Any) -> None:
        setting = self.registry.get(name)
        if setting.env is None:
            setattr(self, name, value)
        else:
            self.env.set(setting.env, setting.to_env(value))

    def unset(self, name: str) -> None:
        setting = self.registry.get(name)
        if setting.core:
            raise ValidationError(f"'{name}' is required and cannot be unset.")
        if setting.env is None:
            setattr(self, name, None)
        else:
            self.env.remove(setting.env)

    @property
    def extra_env(self) -> list[str]:
        return [
            s.env
            for s in self.registry
            if s.env and not s.core and self.env.get(s.env) is not None
        ]

    _ca_bundle: str | None = None

    @property
    def ca_bundle(self) -> str | None:
        return self._ca_bundle

    @ca_bundle.setter
    def ca_bundle(self, host_path: str | None) -> None:
        self._ca_bundle = host_path or None
        if host_path:
            self.env.set("SSL_CERT_FILE", CA_BUNDLE_IN_CONTAINER)
        else:
            self.env.remove("SSL_CERT_FILE")

    def find(self, id_or_name: str) -> DatabaseSpec:
        matches = [
            d
            for d in self.databases
            if d.id == id_or_name or d.id.startswith(id_or_name) or d.name == id_or_name
        ]
        if not matches:
            raise ValidationError(
                f"No database matching '{id_or_name}'.",
                hint="See: portabase agent db list",
            )
        if len(matches) > 1:
            raise ValidationError(
                f"'{id_or_name}' matches several databases; use the id."
            )
        return matches[0]

    def save_state(self) -> None:
        self.validate()
        self.env.save()


@dataclass
class DashboardProject:
    path: Path
    env: EnvFile

    @classmethod
    def load(cls, path: Path) -> DashboardProject:
        path = path.resolve()
        env = EnvFile.load(path / ENV_FILE)
        if env.get("PROJECT_SECRET") is None:
            raise ConfigError(
                f"Not a Portabase dashboard folder: {path}",
                hint="Expected a .env with PROJECT_SECRET.",
            )
        return cls(path, env)

    @classmethod
    def create(cls, path: Path, env_vars: dict[str, str]) -> DashboardProject:
        path.mkdir(parents=True, exist_ok=True)
        env = EnvFile.load(path / ENV_FILE)
        env.merge(env_vars)
        return cls(path, env)

    @property
    def db_mode(self) -> Literal["external", "internal", "custom"]:
        host = self.env.get("POSTGRES_HOST")
        if host is None:
            return "internal"
        return "external" if host == "db" else "custom"

    @property
    def project_name(self) -> str:
        return self.env.get("PROJECT_NAME") or self.path.name

    registry = cfg.DASHBOARD

    def setting(self, name: str) -> Any:
        setting = self.registry.get(name)
        return setting.from_env(self.env.get(setting.env or ""))

    def settings(self) -> dict[str, Any]:
        return {s.name: self.setting(s.name) for s in self.registry}

    def set(self, name: str, value: Any) -> None:
        setting = self.registry.get(name)
        self.env.set(setting.env or "", setting.to_env(value))

    def unset(self, name: str) -> None:
        self.env.remove(self.registry.get(name).env or "")

    @property
    def providers(self) -> list[AuthProvider]:
        found: dict[tuple[ProviderKind, str], dict[str, str]] = {}
        kinds: tuple[tuple[ProviderKind, str], ...] = (
            ("oidc", "AUTH_OIDC_"),
            ("oauth", "AUTH_SOCIAL_"),
        )
        for key, value in self.env.as_dict().items():
            for kind, prefix in kinds:
                if not key.startswith(prefix):
                    continue
                rest = key[len(prefix) :]
                env_map = ap.OIDC_ENV if kind == "oidc" else ap.OAUTH_ENV
                for field_name, suffix in env_map.items():
                    if rest.endswith("_" + suffix):
                        slug = rest[: -len(suffix) - 1]
                        found.setdefault((kind, slug), {})[field_name] = value
                        break
                else:
                    if kind == "oidc" and rest.endswith("_ID"):
                        found.setdefault((kind, rest[:-3]), {})["id"] = value
        providers = []
        for (kind, slug), values in sorted(found.items()):
            pid = values.pop("id", slug.lower().replace("_", "-"))
            providers.append(AuthProvider(kind=kind, id=pid, values=values))
        return providers

    def add_provider(self, provider: AuthProvider) -> None:
        if any(p.id == provider.id for p in self.providers):
            raise ValidationError(
                f"A provider named '{provider.id}' already exists.",
                hint="Remove it first: portabase dashboard auth remove",
            )
        prefix = ap.provider_prefix(provider.kind, provider.id)
        env_map = ap.OIDC_ENV if provider.kind == "oidc" else ap.OAUTH_ENV
        if provider.kind == "oidc":
            self.env.set(f"{prefix}_ID", provider.id)
        for field_name, value in provider.values.items():
            if value in ("", None, False):
                continue
            raw = "true" if value is True else str(value)
            self.env.set(f"{prefix}_{env_map[field_name]}", raw)

    def remove_provider(self, provider_id: str) -> AuthProvider:
        match = next((p for p in self.providers if p.id == provider_id), None)
        if match is None:
            raise ValidationError(
                f"No provider named '{provider_id}'.",
                hint="See: portabase dashboard auth list",
            )
        self.env.remove_prefix(ap.provider_prefix(match.kind, match.id))
        return match

    def callback_url(self, provider_id: str) -> str:
        return f"{self.setting('url')}/api/auth/sso/callback/{provider_id}"

    def validate(self) -> None:
        values = self.settings()
        providers = self.providers
        if values["skip_onboarding"] and not (
            values["admin_email"] and values["admin_password"]
        ):
            raise ValidationError(
                "Skipping onboarding needs an initial account.",
                hint="Set admin_email and admin_password.",
            )
        if not values["password_auth"] and not providers:
            raise ValidationError(
                "Disabling password login with no OIDC or OAuth provider "
                "would lock everyone out.",
                hint="Add a provider first: portabase dashboard auth add",
            )
        url = values["url"] or ""
        if providers and ("localhost" in url or "127.0.0.1" in url):
            raise ValidationError(
                f"Login providers need a public URL for their callback "
                f"(currently {url}).",
                hint="portabase dashboard set NAME url https://your.domain",
            )

    def save_state(self) -> None:
        self.validate()
        self.env.save()


@dataclass(frozen=True)
class AuthProvider:
    kind: ProviderKind
    id: str
    values: dict[str, Any]
