import pytest

from core.specs import DatabaseSpec


def _spec(**kwargs):
    return DatabaseSpec(id="id-1", engine="postgresql", name="db", **kwargs)


def env_prefix_uppercases_and_replaces_dashes():
    assert _spec(host="db-pg-ab12").env_prefix == "DB_PG_AB12"


def env_prefix_requires_host():
    with pytest.raises(ValueError, match="host"):
        _ = _spec().env_prefix


@pytest.mark.parametrize(
    ("password", "expected"), [("s3cret", True), ("", False), (None, False)]
)
def auth_follows_password(password, expected):
    assert _spec(password=password).auth is expected


def with_options_returns_a_copy():
    original = _spec(options={"a": 1})
    options = {"b": 2}
    updated = original.with_options(options)
    options["c"] = 3
    assert updated.options == {"b": 2}
    assert original.options == {"a": 1}
    assert updated.id == original.id
