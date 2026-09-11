from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from core.errors import ValidationError
from core.fields import Field

Section = Literal["network", "api", "onboarding", "auth"]
SECTION_TITLES: dict[Section, str] = {
    "network": "Network",
    "api": "API & MCP",
    "onboarding": "Onboarding",
    "auth": "Authentication",
}


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


@dataclass(frozen=True)
class Setting:
    field: Field
    env: str
    section: Section
    secret: bool = False

    @property
    def name(self) -> str:
        return self.field.name


SETTINGS: tuple[Setting, ...] = (
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
        Field("openapi", "Enable OpenAPI spec and Swagger UI?", "bool", default=False),
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
)

BY_NAME: dict[str, Setting] = {s.name: s for s in SETTINGS}

WIZARD_SECTIONS: tuple[tuple[Section, tuple[str, ...]], ...] = (
    ("api", ("api", "openapi", "mcp")),
    ("onboarding", ("skip_onboarding", "admin_name", "admin_email", "admin_password")),
    ("auth", ("password_auth", "signup", "passkey")),
)


def get(name: str) -> Setting:
    try:
        return BY_NAME[name]
    except KeyError:
        raise ValidationError(
            f"Unknown setting '{name}'.",
            hint="Known: " + ", ".join(BY_NAME),
        ) from None


def to_env(setting: Setting, value: Any) -> str:
    if setting.field.kind == "bool":
        return "true" if value else "false"
    return str(value)


def from_env(setting: Setting, raw: str | None) -> Any:
    if raw is None:
        return setting.field.default
    if setting.field.kind == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return raw


OAUTH_PROVIDERS: tuple[str, ...] = (
    "google",
    "github",
    "discord",
    "apple",
    "linkedin",
    "x",
    "reddit",
)

OIDC_FIELDS: tuple[Field, ...] = (
    Field("issuer", "Issuer / discovery URL", "text", validator=public_url),
    Field("client", "Client ID", "text"),
    Field("secret", "Client secret", "secret"),
    Field("title", "Display name", "text", default=""),
    Field("scopes", "Scopes", "text", default=""),
    Field("pkce", "Use PKCE?", "bool", default=False),
    Field("host", "Host override", "text", default=""),
)

OAUTH_FIELDS: tuple[Field, ...] = (
    Field("client", "Client ID", "text"),
    Field("secret", "Client secret", "secret"),
    Field("title", "Display name", "text", default=""),
)

OIDC_ENV: dict[str, str] = {
    "issuer": "ISSUER_URL",
    "client": "CLIENT",
    "secret": "SECRET",
    "title": "TITLE",
    "scopes": "SCOPES",
    "pkce": "PKCE",
    "host": "HOST",
}
OAUTH_ENV: dict[str, str] = {"client": "CLIENT", "secret": "SECRET", "title": "TITLE"}


def provider_prefix(kind: str, provider_id: str) -> str:
    slug = re.sub(r"[^A-Z0-9]", "_", provider_id.upper())
    return f"AUTH_OIDC_{slug}" if kind == "oidc" else f"AUTH_SOCIAL_{slug}"


def validate_provider_id(kind: str, provider_id: str) -> str:
    pid = provider_id.strip().lower()
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", pid):
        raise ValidationError(
            f"Invalid provider id {provider_id!r}.",
            hint="Use lowercase letters, digits and dashes.",
        )
    if kind == "oauth" and pid not in OAUTH_PROVIDERS:
        raise ValidationError(
            f"Unknown OAuth provider '{pid}'.",
            hint="Supported: " + ", ".join(OAUTH_PROVIDERS),
        )
    return pid
