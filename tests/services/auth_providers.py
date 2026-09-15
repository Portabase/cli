import pytest

from core.errors import ValidationError
from services import auth_providers as ap


@pytest.mark.parametrize(
    ("kind", "provider_id", "expected"),
    [
        ("oidc", "keycloak", "AUTH_OIDC_KEYCLOAK"),
        ("oidc", "my-kc", "AUTH_OIDC_MY_KC"),
        ("oauth", "github", "AUTH_SOCIAL_GITHUB"),
    ],
)
def provider_prefix_cases(kind, provider_id, expected):
    assert ap.provider_prefix(kind, provider_id) == expected


@pytest.mark.parametrize(
    ("kind", "provider_id", "expected"),
    [
        ("oidc", " KeyCloak ", "keycloak"),
        ("oidc", "my-kc-2", "my-kc-2"),
        ("oauth", "GitHub", "github"),
    ],
)
def validate_provider_id_accepts(kind, provider_id, expected):
    assert ap.validate_provider_id(kind, provider_id) == expected


@pytest.mark.parametrize("provider_id", ["", "-kc", "k_c", "k c", "kc!"])
def validate_provider_id_rejects_bad_ids(provider_id):
    with pytest.raises(ValidationError, match="Invalid provider id"):
        ap.validate_provider_id("oidc", provider_id)


def validate_provider_id_rejects_unknown_oauth():
    with pytest.raises(ValidationError, match="Unknown OAuth provider 'gitlab'") as exc:
        ap.validate_provider_id("oauth", "gitlab")
    assert "github" in (exc.value.hint or "")


@pytest.mark.parametrize(
    ("fields", "env"),
    [(ap.OIDC_FIELDS, ap.OIDC_ENV), (ap.OAUTH_FIELDS, ap.OAUTH_ENV)],
    ids=["oidc", "oauth"],
)
def every_field_has_an_env_suffix(fields, env):
    assert [field.name for field in fields] == list(env)
