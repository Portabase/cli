from __future__ import annotations

import re

from core.errors import ValidationError
from core.fields import Field
from services.settings import public_url

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
