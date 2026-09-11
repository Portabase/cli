from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from core.errors import ValidationError
from core.fields import Field
from core.utils import validate_edge_key


def strong_password(value: str) -> str:
    checks = (
        (len(value) >= 8, "at least 8 characters"),
        (re.search(r"[a-z]", value), "a lowercase letter"),
        (re.search(r"[A-Z]", value), "an uppercase letter"),
        (re.search(r"\d", value), "a digit"),
        (re.search(r"[^A-Za-z0-9]", value), "a special character"),
    )
    missing = [label for ok, label in checks if not ok]
    if missing:
        raise ValidationError(
            "Password too weak.", hint="It needs " + ", ".join(missing) + "."
        )
    return value


def public_url(value: str) -> str:
    if not re.match(r"^https?://[^/\s]+", value):
        raise ValidationError(
            f"Invalid URL: {value!r}", hint="Expected http(s)://host[:port]"
        )
    return value.rstrip("/")


def edge_key(value: str) -> str:
    if not validate_edge_key(value):
        raise ValidationError(
            "Invalid Edge Key.",
            hint="Expected Base64 or JSON with serverUrl, agentId, masterKeyB64.",
        )
    return value


def positive(value: int) -> int:
    if value < 1:
        raise ValidationError("Expected a positive number.")
    return value


@dataclass(frozen=True)
class Setting:
    field: Field
    env: str | None
    section: str
    secret: bool = False
    core: bool = False
    container_env: bool = True

    @property
    def name(self) -> str:
        return self.field.name

    def to_env(self, value: Any) -> str:
        if self.field.kind == "bool":
            return "true" if value else "false"
        return str(value)

    def from_env(self, raw: str | None) -> Any:
        if raw is None:
            return self.field.default
        if self.field.kind == "bool":
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if self.field.kind == "int":
            return int(raw) if raw.strip().lstrip("-").isdigit() else raw
        return raw


class Registry:
    def __init__(self, settings: tuple[Setting, ...], sections: dict[str, str]) -> None:
        self._settings = settings
        self._by_name = {s.name: s for s in settings}
        self.sections = sections

    def __iter__(self) -> Iterator[Setting]:
        return iter(self._settings)

    def names(self) -> list[str]:
        return list(self._by_name)

    def get(self, name: str) -> Setting:
        try:
            return self._by_name[name]
        except KeyError:
            raise ValidationError(
                f"Unknown setting '{name}'.", hint="Known: " + ", ".join(self._by_name)
            ) from None

    def in_section(self, section: str) -> list[Setting]:
        return [s for s in self._settings if s.section == section]


AGENT = Registry(
    (
        Setting(
            Field("key", "Edge Key", "text", validator=edge_key),
            "EDGE_KEY",
            "agent",
            secret=True,
            core=True,
        ),
        Setting(
            Field("tz", "Timezone", "text", default="UTC"), "TZ", "agent", core=True
        ),
        Setting(
            Field(
                "polling",
                "Polling frequency (seconds)",
                "int",
                default=5,
                validator=positive,
            ),
            "POLLING",
            "agent",
            core=True,
        ),
        Setting(
            Field(
                "log_level",
                "Log level",
                "choice",
                default="info",
                choices=("debug", "info", "warn", "error"),
            ),
            "LOG_LEVEL",
            "agent",
            core=True,
        ),
        Setting(
            Field(
                "host_gateway",
                "Map localhost to the Docker host?",
                "bool",
                default=False,
                help="Adds extra_hosts localhost:host-gateway so the agent reaches services on the host.",
            ),
            None,
            "network",
            core=True,
        ),
        Setting(
            Field("data_path", "Data path inside the container", "text"),
            "DATA_PATH",
            "storage",
        ),
        Setting(
            Field("tmpdir", "Temporary archives path", "text"), "TMPDIR", "storage"
        ),
        Setting(
            Field(
                "retry_attempts",
                "Retry attempts for database operations",
                "int",
                validator=positive,
            ),
            "RETRY_ATTEMPTS",
            "resilience",
        ),
        Setting(
            Field(
                "retry_backoff_ms",
                "Base delay between retries (ms)",
                "int",
                validator=positive,
            ),
            "RETRY_BACKOFF_MS",
            "resilience",
        ),
        Setting(
            Field(
                "ca_bundle",
                "CA bundle on this host (for an internal CA)",
                "path",
                help=(
                    "The file is mounted read-only and SSL_CERT_FILE points at it. "
                    "It REPLACES the root store, so concatenate the Mozilla roots "
                    "with your CA: cat /etc/ssl/certs/ca-certificates.crt my-ca.crt "
                    "> ca-bundle.crt"
                ),
            ),
            "CA_BUNDLE",
            "network",
            container_env=False,
        ),
    ),
    {
        "agent": "Agent",
        "network": "Network",
        "storage": "Storage",
        "resilience": "Resilience",
    },
)

DASHBOARD = Registry(
    (
        Setting(
            Field(
                "url",
                "Public URL",
                "text",
                validator=public_url,
                help="Used for links and OAuth/OIDC callbacks.",
            ),
            "PROJECT_URL",
            "network",
        ),
        Setting(
            Field("behind_proxy", "Behind a reverse proxy?", "bool", default=False),
            "TUSD_BEHIND_PROXY",
            "network",
        ),
        Setting(
            Field("trusted_domains", "Trusted domains (comma-separated)", "text"),
            "TRUSTED_DOMAINS",
            "network",
        ),
        Setting(
            Field("api", "Enable the REST API (/api/v1)?", "bool", default=False),
            "API_ENABLED",
            "api",
        ),
        Setting(
            Field(
                "openapi", "Enable OpenAPI spec and Swagger UI?", "bool", default=False
            ),
            "OPENAPI_ENABLED",
            "api",
        ),
        Setting(
            Field("mcp", "Enable the MCP server (/api/v1/mcp)?", "bool", default=False),
            "MCP_ENABLED",
            "api",
        ),
        Setting(
            Field(
                "skip_onboarding",
                "Skip the onboarding wizard?",
                "bool",
                default=False,
                help="Requires an initial account: admin_email and admin_password.",
            ),
            "SKIP_ONBOARDING",
            "onboarding",
        ),
        Setting(
            Field("admin_name", "Initial user name", "text"),
            "AUTH_DEFAULT_USER_NAME",
            "onboarding",
        ),
        Setting(
            Field("admin_email", "Initial user email", "text"),
            "AUTH_DEFAULT_USER",
            "onboarding",
        ),
        Setting(
            Field(
                "admin_password",
                "Initial user password",
                "secret",
                validator=strong_password,
            ),
            "AUTH_DEFAULT_PASSWORD",
            "onboarding",
            secret=True,
        ),
        Setting(
            Field(
                "password_auth",
                "Allow email/password login?",
                "bool",
                default=True,
                help="Disable only with at least one OIDC or OAuth provider configured.",
            ),
            "AUTH_EMAIL_PASSWORD_ENABLED",
            "auth",
        ),
        Setting(
            Field("signup", "Allow self sign-up?", "bool"),
            "AUTH_SIGNUP_ENABLED",
            "auth",
        ),
        Setting(
            Field("passkey", "Allow passkey login?", "bool"),
            "AUTH_PASSKEY_ENABLED",
            "auth",
        ),
        Setting(
            Field("account_linking", "Allow linking provider accounts?", "bool"),
            "AUTH_ALLOW_LINKING",
            "auth",
        ),
        Setting(
            Field("account_unlinking", "Allow unlinking provider accounts?", "bool"),
            "AUTH_ALLOW_UNLINKING",
            "auth",
        ),
        Setting(
            Field("sync_oidc_roles", "Sync roles from OIDC on login?", "bool"),
            "AUTH_SYNC_OIDC_ROLES_ON_LOGIN",
            "auth",
        ),
        Setting(
            Field("role_map", "Role map (remote:portabase,...)", "text"),
            "AUTH_ROLE_MAP",
            "auth",
        ),
        Setting(
            Field("allowed_group", "Restrict access to this group", "text"),
            "ALLOWED_GROUP",
            "auth",
        ),
    ),
    {
        "network": "Network",
        "api": "API & MCP",
        "onboarding": "Onboarding",
        "auth": "Authentication",
    },
)

DASHBOARD_WIZARD: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("api", ("api", "openapi", "mcp")),
    ("onboarding", ("skip_onboarding", "admin_name", "admin_email", "admin_password")),
    ("auth", ("password_auth", "signup", "passkey")),
)
