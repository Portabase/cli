import re

import pytest

from core.errors import ValidationError
from core.specs import DatabaseSpec
from engines import registry
from engines.mongodb import MongoEngine
from tests.support import EXISTING_ANSWERS, field_specs

MONGO = registry.get("mongodb")
HEALTH = {"interval": "10s", "timeout": "5s", "retries": 5}
AUTH = pytest.mark.parametrize("auth", [True, False], ids=["auth", "noauth"])


def attributes():
    assert type(MONGO) is MongoEngine
    assert (MONGO.key, MONGO.display, MONGO.default_port) == (
        "mongodb",
        "MongoDB",
        27017,
    )
    assert MONGO.template == "engines/mongodb.yml.j2"
    assert (MONGO.auth_variants, MONGO.has_modes, MONGO.warning) == (True, True, None)


@AUTH
def generate(ports, auth):
    spec = MONGO.generate(auth=auth, ports=ports, answers={})
    suffix = "auth-" if auth else ""
    assert re.fullmatch(rf"db-mongo-{suffix}[0-9a-f]{{4}}", spec.host or "")
    assert re.fullmatch(r"mongo_[0-9a-f]{8}", spec.database or "")
    assert len(spec.password or "") == (16 if auth else 0)
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="mongodb",
        name=spec.database or "",
        managed=True,
        host=spec.host,
        port=27017,
        host_port=40000,
        database=spec.database,
        username="admin" if auth else "",
        password=spec.password,
    )
    assert MONGO.describe(spec) == f"{spec.host}:27017"


@AUTH
def env_vars(ports, auth):
    spec = MONGO.generate(auth=auth, ports=ports, answers={})
    prefix = spec.env_prefix
    expected = {f"{prefix}_PORT": "40000", f"{prefix}_DB": spec.database}
    if auth:
        expected |= {f"{prefix}_USER": "admin", f"{prefix}_PASS": spec.password}
    assert MONGO.env_vars(spec) == expected


@AUTH
def agent_entry(ports, auth):
    spec = MONGO.generate(auth=auth, ports=ports, answers={})
    assert MONGO.agent_entry(spec) == {
        "name": spec.name,
        "database": spec.database,
        "type": "mongodb",
        "username": "admin" if auth else "",
        "password": spec.password or "",
        "port": 27017,
        "host": spec.host,
        "generated_id": spec.id,
    }


def fields():
    assert field_specs(MONGO.fields_existing()) == [
        ("host", "text", "localhost"),
        ("port", "int", 27017),
        ("database", "text", None),
        ("username", "text", ""),
        ("password", "secret", ""),
    ]
    assert MONGO.fields_new() == []
    assert field_specs(MONGO.option_fields()) == [
        ("auth_source", "text", ""),
        ("replica_set", "text", ""),
        ("tls", "bool", False),
    ]


def from_existing():
    spec = MONGO.from_existing({**EXISTING_ANSWERS, "label": "Prod"})
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="mongodb",
        name="Prod",
        host="db.example",
        port=1234,
        database="app",
        username="u",
        password="p",
    )
    assert MONGO.from_existing(EXISTING_ANSWERS).name == "External DB"


@AUTH
def compose_service(render_engine, auth):
    rendered = render_engine("mongodb", auth=auth)
    expected = {
        "image": "mongo:latest",
        "restart": "unless-stopped",
        "networks": ["portabase"],
        "ports": [f"{rendered.var('PORT')}:27017"],
        "environment": [f"MONGO_INITDB_DATABASE={rendered.var('DB')}"],
        "volumes": [f"{rendered.spec.host}-data:/data/db"],
        "healthcheck": {
            "test": ["CMD-SHELL", "mongosh --eval 'db.runCommand({ping:1})' --quiet"],
            **HEALTH,
        },
    }
    if auth:
        expected["environment"] = [
            f"MONGO_INITDB_ROOT_USERNAME={rendered.var('USER')}",
            f"MONGO_INITDB_ROOT_PASSWORD={rendered.var('PASS')}",
            f"MONGO_INITDB_DATABASE={rendered.var('DB')}",
        ]
        expected["command"] = "mongod --auth"
    assert rendered.service == expected


def compose_service_inline(render_engine):
    rendered = render_engine("mongodb", auth=True, inline=True)
    assert rendered.service["ports"] == ["40000:27017"]
    assert rendered.service["environment"] == [
        "MONGO_INITDB_ROOT_USERNAME=admin",
        f"MONGO_INITDB_ROOT_PASSWORD={rendered.spec.password}",
        f"MONGO_INITDB_DATABASE={rendered.spec.database}",
    ]


def generate_keeps_options(ports):
    options = {"replica_set": "rs0", "tls": True}
    spec = MONGO.generate(auth=True, ports=ports, answers={"options": options})
    assert spec.options == options


def only_non_default_options_reach_the_agent(ports):
    options = {"auth_source": "", "replica_set": "rs0", "tls": False, "unknown": 1}
    spec = MONGO.generate(auth=True, ports=ports, answers={"options": options})
    assert MONGO.non_default_options(spec) == {"replica_set": "rs0"}
    assert MONGO.agent_entry(spec)["options"] == {"replica_set": "rs0"}
    tls_only = spec.with_options({"tls": True})
    assert MONGO.agent_entry(tls_only)["options"] == {"tls": True}
    custom_auth = spec.with_options({"auth_source": "users"})
    assert MONGO.agent_entry(custom_auth)["options"] == {"auth_source": "users"}
    defaults = spec.with_options({"auth_source": "", "replica_set": "", "tls": False})
    assert "options" not in MONGO.agent_entry(defaults)


def port_field_mentions_srv():
    port = next(field for field in MONGO.fields_existing() if field.name == "port")
    assert "mongodb+srv://" in (port.help or "")


@pytest.mark.parametrize("port", [0, 27017, 65535])
def port_validator_accepts(port):
    field = next(field for field in MONGO.fields_existing() if field.name == "port")
    assert field.validator is not None
    assert field.validator(port) == port


@pytest.mark.parametrize("port", [-1, 65536])
def port_validator_rejects(port):
    field = next(field for field in MONGO.fields_existing() if field.name == "port")
    assert field.validator is not None
    with pytest.raises(ValidationError):
        field.validator(port)


def srv_existing():
    spec = MONGO.from_existing(
        {**EXISTING_ANSWERS, "host": "cluster0.abcde.mongodb.net", "port": 0}
    )
    assert spec.port == 0
    assert MONGO.is_srv(spec)
    assert MONGO.describe(spec) == "mongodb+srv://cluster0.abcde.mongodb.net"
    assert MONGO.agent_entry(spec) == {
        "name": "External DB",
        "database": "app",
        "type": "mongodb",
        "username": "u",
        "password": "p",
        "host": "cluster0.abcde.mongodb.net",
        "generated_id": spec.id,
    }


def srv_missing_port():
    spec = DatabaseSpec(
        id="x", engine="mongodb", name="Atlas", host="c.mongodb.net", port=None
    )
    assert MONGO.is_srv(spec)
    assert "port" not in MONGO.agent_entry(spec)
    assert MONGO.describe(spec) == "mongodb+srv://c.mongodb.net"


def srv_without_auth():
    answers = {"host": "c.mongodb.net", "port": 0, "database": "app"}
    spec = MONGO.from_existing({**answers, "username": "", "password": ""})
    entry = MONGO.agent_entry(spec)
    assert "port" not in entry
    assert (entry["username"], entry["password"]) == ("", "")


def non_srv_existing():
    spec = MONGO.from_existing(EXISTING_ANSWERS)
    assert not MONGO.is_srv(spec)
    assert MONGO.describe(spec) == "db.example:1234"
