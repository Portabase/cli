import dataclasses
import re

import pytest

from core.specs import DatabaseSpec
from engines import registry
from engines.redis import RedisEngine
from tests.support import EXISTING_ANSWERS, field_specs

REDIS = registry.get("redis")
HEALTH = {"interval": "10s", "timeout": "5s", "retries": 5}
AUTH = pytest.mark.parametrize("auth", [True, False], ids=["auth", "noauth"])


def attributes():
    assert type(REDIS) is RedisEngine
    assert (REDIS.key, REDIS.display, REDIS.default_port) == ("redis", "Redis", 6379)
    assert REDIS.template == "engines/redis.yml.j2"
    assert (REDIS.auth_variants, REDIS.has_modes, REDIS.warning) == (True, True, None)


@AUTH
def generate(ports, auth):
    spec = REDIS.generate(auth=auth, ports=ports, answers={})
    suffix = "auth-" if auth else ""
    assert re.fullmatch(rf"db-redis-{suffix}[0-9a-f]{{4}}", spec.host or "")
    assert re.fullmatch(r"redis_[0-9a-f]{8}", spec.name)
    assert len(spec.password or "") == (16 if auth else 0)
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="redis",
        name=spec.name,
        managed=True,
        host=spec.host,
        port=6379,
        host_port=40000,
        database="0",
        username="",
        password=spec.password,
    )
    assert REDIS.describe(spec) == f"{spec.host}:6379"


@AUTH
def env_vars(ports, auth):
    spec = REDIS.generate(auth=auth, ports=ports, answers={})
    prefix = spec.env_prefix
    expected = {f"{prefix}_PORT": "40000"}
    if auth:
        expected[f"{prefix}_PASS"] = spec.password or ""
    assert REDIS.env_vars(spec) == expected


@AUTH
def agent_entry(ports, auth):
    spec = REDIS.generate(auth=auth, ports=ports, answers={})
    assert REDIS.agent_entry(spec) == {
        "name": spec.name,
        "database": "0",
        "type": "redis",
        "username": "",
        "password": spec.password or "",
        "port": 6379,
        "host": spec.host,
        "generated_id": spec.id,
    }


def fields():
    assert field_specs(REDIS.fields_existing()) == [
        ("host", "text", "localhost"),
        ("port", "int", 6379),
        ("database", "text", "0"),
        ("username", "text", ""),
        ("password", "text", ""),
    ]
    assert REDIS.fields_new() == []
    assert REDIS.option_fields() == []


def from_existing():
    spec = REDIS.from_existing({**EXISTING_ANSWERS, "label": "Prod"})
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="redis",
        name="Prod",
        host="db.example",
        port=1234,
        database="app",
        username="u",
        password="p",
    )
    assert REDIS.from_existing(EXISTING_ANSWERS).name == "External DB"


@AUTH
def compose_service(render_engine, auth):
    rendered = render_engine("redis", auth=auth)
    password = rendered.var("PASS")
    expected = {
        "image": "redis:latest",
        "restart": "unless-stopped",
        "ports": [f"{rendered.var('PORT')}:6379"],
        "volumes": [f"{rendered.spec.host}-data:/data"],
        "command": ["redis-server", "--appendonly", "yes"],
        "networks": ["portabase", "default"],
        "healthcheck": {"test": ["CMD-SHELL", "redis-cli ping | grep PONG"], **HEALTH},
    }
    if auth:
        expected["environment"] = [f"REDIS_PASSWORD={password}"]
        expected["command"] = [
            "redis-server",
            "--requirepass",
            password,
            "--appendonly",
            "yes",
        ]
        expected["healthcheck"] = {
            "test": ["CMD-SHELL", f"redis-cli -a {password} ping | grep PONG"],
            **HEALTH,
        }
    assert rendered.service == expected


def compose_service_inline(render_engine):
    rendered = render_engine("redis", auth=True, inline=True)
    password = rendered.spec.password
    assert rendered.service["ports"] == ["40000:6379"]
    assert rendered.service["environment"] == [f"REDIS_PASSWORD={password}"]
    assert rendered.service["command"] == [
        "redis-server",
        "--requirepass",
        password,
        "--appendonly",
        "yes",
    ]


def agent_database_defaults_to_index_zero(ports):
    spec = REDIS.generate(auth=False, ports=ports, answers={})
    assert REDIS.agent_database(dataclasses.replace(spec, database=None)) == "0"
    assert REDIS.agent_database(dataclasses.replace(spec, database="3")) == "3"
