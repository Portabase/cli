import dataclasses
import re

import pytest

from core.specs import DatabaseSpec
from engines import registry
from engines.valkey import ValkeyEngine
from tests.support import EXISTING_ANSWERS, field_specs

VALKEY = registry.get("valkey")
HEALTH = {"interval": "10s", "timeout": "5s", "retries": 5}
AUTH = pytest.mark.parametrize("auth", [True, False], ids=["auth", "noauth"])


def attributes():
    assert type(VALKEY) is ValkeyEngine
    assert (VALKEY.key, VALKEY.display, VALKEY.default_port) == (
        "valkey",
        "Valkey",
        6379,
    )
    assert VALKEY.template == "engines/valkey.yml.j2"
    assert (VALKEY.auth_variants, VALKEY.has_modes, VALKEY.warning) == (
        True,
        True,
        None,
    )


@AUTH
def generate(ports, auth):
    spec = VALKEY.generate(auth=auth, ports=ports, answers={})
    suffix = "auth-" if auth else ""
    assert re.fullmatch(rf"db-valkey-{suffix}[0-9a-f]{{4}}", spec.host or "")
    assert re.fullmatch(r"valkey_[0-9a-f]{8}", spec.name)
    assert len(spec.password or "") == (16 if auth else 0)
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="valkey",
        name=spec.name,
        managed=True,
        host=spec.host,
        port=6379,
        host_port=40000,
        database="0",
        username="",
        password=spec.password,
    )
    assert VALKEY.describe(spec) == f"{spec.host}:6379"


@AUTH
def env_vars(ports, auth):
    spec = VALKEY.generate(auth=auth, ports=ports, answers={})
    prefix = spec.env_prefix
    expected = {f"{prefix}_PORT": "40000"}
    if auth:
        expected[f"{prefix}_PASS"] = spec.password or ""
    assert VALKEY.env_vars(spec) == expected


@AUTH
def agent_entry(ports, auth):
    spec = VALKEY.generate(auth=auth, ports=ports, answers={})
    assert VALKEY.agent_entry(spec) == {
        "name": spec.name,
        "database": "0",
        "type": "valkey",
        "username": "",
        "password": spec.password or "",
        "port": 6379,
        "host": spec.host,
        "generated_id": spec.id,
    }


def fields():
    assert field_specs(VALKEY.fields_existing()) == [
        ("host", "text", "localhost"),
        ("port", "int", 6379),
        ("database", "text", "0"),
        ("username", "text", ""),
        ("password", "text", ""),
    ]
    assert VALKEY.fields_new() == []
    assert VALKEY.option_fields() == []


def from_existing():
    spec = VALKEY.from_existing({**EXISTING_ANSWERS, "label": "Prod"})
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="valkey",
        name="Prod",
        host="db.example",
        port=1234,
        database="app",
        username="u",
        password="p",
    )
    assert VALKEY.from_existing(EXISTING_ANSWERS).name == "External DB"


@AUTH
def compose_service(render_engine, auth):
    rendered = render_engine("valkey", auth=auth)
    password = rendered.var("PASS")
    expected = {
        "image": "valkey/valkey:latest",
        "restart": "unless-stopped",
        "environment": ["ALLOW_EMPTY_PASSWORD=yes"],
        "ports": [f"{rendered.var('PORT')}:6379"],
        "volumes": [f"{rendered.spec.host}-data:/data"],
        "networks": ["portabase", "default"],
        "healthcheck": {"test": ["CMD-SHELL", "valkey-cli ping | grep PONG"], **HEALTH},
    }
    if auth:
        del expected["environment"]
        expected["command"] = ["valkey-server", "--requirepass", password]
        expected["healthcheck"] = {
            "test": ["CMD-SHELL", f"valkey-cli -a {password} ping | grep PONG"],
            **HEALTH,
        }
    assert rendered.service == expected


def compose_service_inline(render_engine):
    rendered = render_engine("valkey", auth=True, inline=True)
    assert rendered.service["ports"] == ["40000:6379"]
    assert rendered.service["command"] == [
        "valkey-server",
        "--requirepass",
        rendered.spec.password,
    ]


def agent_database_defaults_to_index_zero(ports):
    spec = VALKEY.generate(auth=False, ports=ports, answers={})
    assert VALKEY.agent_database(dataclasses.replace(spec, database=None)) == "0"
    assert VALKEY.agent_database(dataclasses.replace(spec, database="3")) == "3"
