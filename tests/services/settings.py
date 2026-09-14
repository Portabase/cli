import base64
import json

import pytest

from core.errors import ValidationError
from core.fields import Field
from services import settings as cfg
from tests.support import EDGE_KEY_PAYLOAD


def _setting(kind, default=None):
    return cfg.Setting(Field("x", "X", kind, default=default), "X", "s")


def strong_password_accepts():
    assert cfg.strong_password("Abcdef1!") == "Abcdef1!"


@pytest.mark.parametrize(
    ("value", "missing"),
    [
        ("Ab1!", "at least 8 characters"),
        ("ABCDEFG1!", "a lowercase letter"),
        ("abcdefg1!", "an uppercase letter"),
        ("Abcdefgh!", "a digit"),
        ("Abcdefgh1", "a special character"),
    ],
)
def strong_password_rejects(value, missing):
    with pytest.raises(ValidationError) as exc:
        cfg.strong_password(value)
    assert missing in (exc.value.hint or "")


def strong_password_lists_every_missing_rule():
    with pytest.raises(ValidationError) as exc:
        cfg.strong_password("")
    assert exc.value.hint == (
        "It needs at least 8 characters, a lowercase letter, an uppercase letter, "
        "a digit, a special character."
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://portabase.example", "https://portabase.example"),
        ("https://portabase.example/", "https://portabase.example"),
        ("http://localhost:8887", "http://localhost:8887"),
        ("https://x.example/sub/", "https://x.example/sub"),
    ],
)
def public_url_accepts(value, expected):
    assert cfg.public_url(value) == expected


@pytest.mark.parametrize(
    "value", ["", "portabase.example", "ftp://x", "https://", "https:// x"]
)
def public_url_rejects(value):
    with pytest.raises(ValidationError, match="Invalid URL"):
        cfg.public_url(value)


def edge_key_validator():
    key = base64.b64encode(json.dumps(EDGE_KEY_PAYLOAD).encode()).decode()
    assert cfg.edge_key(key) == key
    with pytest.raises(ValidationError, match="Invalid Edge Key"):
        cfg.edge_key("bad")


def positive_validator():
    assert cfg.positive(1) == 1
    for value in (0, -5):
        with pytest.raises(ValidationError):
            cfg.positive(value)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("true", True),
        ("TRUE", True),
        (" yes ", True),
        ("1", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("", False),
    ],
)
def bool_from_env(raw, expected):
    assert _setting("bool").from_env(raw) is expected


def bool_to_env():
    assert _setting("bool").to_env(True) == "true"
    assert _setting("bool").to_env(False) == "false"


@pytest.mark.parametrize(
    ("raw", "expected"), [("42", 42), (" 7 ", 7), ("-3", -3), ("abc", "abc")]
)
def int_from_env(raw, expected):
    assert _setting("int").from_env(raw) == expected


@pytest.mark.parametrize("kind", ["bool", "int", "text"])
def from_env_none_is_the_default(kind):
    assert _setting(kind, default="d").from_env(None) == "d"


def text_round_trip():
    assert _setting("text").to_env(5) == "5"
    assert _setting("text").from_env(" raw ") == " raw "


@pytest.mark.parametrize(
    "registry", [cfg.AGENT, cfg.DASHBOARD], ids=["agent", "dashboard"]
)
def registry_is_consistent(registry):
    names = [setting.name for setting in registry]
    envs = [setting.env for setting in registry if setting.env]
    assert len(names) == len(set(names))
    assert len(envs) == len(set(envs))
    assert registry.names() == names
    for setting in registry:
        assert setting.section in registry.sections
        assert registry.get(setting.name) is setting
    assert sum(len(registry.in_section(key)) for key in registry.sections) == len(names)


def registry_unknown_setting():
    with pytest.raises(ValidationError, match="Unknown setting 'nope'") as exc:
        cfg.AGENT.get("nope")
    assert "polling" in (exc.value.hint or "")


def dashboard_wizard_names_exist():
    for section, names in cfg.DASHBOARD_WIZARD:
        assert section in cfg.DASHBOARD.sections
        for name in names:
            assert cfg.DASHBOARD.get(name).section == section
