import base64
import json
import string

import pytest

from core.utils import (
    escape_yaml_double_quoted,
    generate_password,
    slugify_project_name,
    validate_edge_key,
)
from tests.support import EDGE_KEY_PAYLOAD

SYMBOLS = "!@#%^&*()-_=+[]{}|;:,.<>?"


@pytest.mark.parametrize(
    ("length", "expected"), [(16, 16), (8, 8), (40, 40), (7, 8), (0, 8)]
)
def generate_password_length(length, expected):
    assert len(generate_password(length)) == expected


def generate_password_has_every_character_class():
    for _ in range(100):
        password = generate_password(8)
        assert any(char in string.ascii_lowercase for char in password)
        assert any(char in string.ascii_uppercase for char in password)
        assert any(char in string.digits for char in password)
        assert any(char in SYMBOLS for char in password)


def generate_password_is_random():
    assert len({generate_password() for _ in range(20)}) == 20


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("my-agent", "my-agent"),
        ("My Agent", "my-agent"),
        ("--Prod_DB--", "prod_db"),
        ("_-x", "x"),
        ("été 2026", "t-2026"),
        ("a  b", "a-b"),
        ("!!!", "portabase"),
        ("", "portabase"),
    ],
)
def slugify_project_name_cases(value, expected):
    assert slugify_project_name(value) == expected


def slugify_project_name_fallback():
    assert slugify_project_name("***", fallback="agent") == "agent"


def validate_edge_key_accepts_base64_json():
    key = base64.b64encode(json.dumps(EDGE_KEY_PAYLOAD).encode()).decode()
    assert validate_edge_key(key)


def validate_edge_key_accepts_raw_json():
    assert validate_edge_key(json.dumps(EDGE_KEY_PAYLOAD))


@pytest.mark.parametrize("missing", ["serverUrl", "agentId", "masterKeyB64"])
def validate_edge_key_rejects_missing_field(missing):
    payload = {key: value for key, value in EDGE_KEY_PAYLOAD.items() if key != missing}
    key = base64.b64encode(json.dumps(payload).encode()).decode()
    assert not validate_edge_key(key)


@pytest.mark.parametrize(
    "key",
    ["", "not a key", "1234", base64.b64encode(b"hello").decode(), "{broken json"],
)
def validate_edge_key_rejects_garbage(key):
    assert not validate_edge_key(key)


@pytest.mark.parametrize(
    "data",
    [list(EDGE_KEY_PAYLOAD), "serverUrl agentId masterKeyB64", None, 42],
    ids=["list", "string", "null", "number"],
)
def validate_edge_key_requires_an_object(data):
    raw = json.dumps(data)
    assert not validate_edge_key(raw)
    assert not validate_edge_key(base64.b64encode(raw.encode()).decode())


@pytest.mark.parametrize(
    ("value", "expected"),
    [("plain", "plain"), ('a"b', 'a\\"b'), ("a\\b", "a\\\\b"), ('\\"', '\\\\\\"')],
)
def escape_yaml_double_quoted_cases(value, expected):
    assert escape_yaml_double_quoted(value) == expected
