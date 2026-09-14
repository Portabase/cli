import re

from core.specs import DatabaseSpec
from engines import registry
from engines.firebird import FirebirdEngine
from tests.support import EXISTING_ANSWERS, field_specs

FIREBIRD = registry.get("firebird")
HEALTH = {"interval": "10s", "timeout": "5s", "retries": 5}


def attributes():
    assert type(FIREBIRD) is FirebirdEngine
    assert (FIREBIRD.key, FIREBIRD.display, FIREBIRD.default_port) == (
        "firebird",
        "Firebird",
        3050,
    )
    assert FIREBIRD.template == "engines/firebird.yml.j2"
    assert (FIREBIRD.auth_variants, FIREBIRD.has_modes, FIREBIRD.warning) == (
        False,
        True,
        None,
    )


def generate(ports):
    spec = FIREBIRD.generate(auth=True, ports=ports, answers={})
    assert re.fullmatch(r"db-firebird-[0-9a-f]{4}", spec.host or "")
    assert len(spec.password or "") == 16
    assert len(spec.root_password or "") == 16
    assert spec.password != spec.root_password
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="firebird",
        name="mirror.fdb",
        managed=True,
        host=spec.host,
        port=3050,
        host_port=40000,
        database="/var/lib/firebird/data/mirror.fdb",
        username="alice",
        password=spec.password,
        root_password=spec.root_password,
    )
    assert FIREBIRD.describe(spec) == f"{spec.host}:3050"


def env_vars(ports):
    spec = FIREBIRD.generate(auth=True, ports=ports, answers={})
    prefix = spec.env_prefix
    assert FIREBIRD.env_vars(spec) == {
        f"{prefix}_PORT": "40000",
        f"{prefix}_DB": "mirror.fdb",
        f"{prefix}_USER": "alice",
        f"{prefix}_PASS": spec.password,
        f"{prefix}_ROOT_PASS": spec.root_password,
    }


def agent_entry(ports):
    spec = FIREBIRD.generate(auth=True, ports=ports, answers={})
    assert FIREBIRD.agent_entry(spec) == {
        "name": "mirror.fdb",
        "database": "/var/lib/firebird/data/mirror.fdb",
        "type": "firebird",
        "username": "alice",
        "password": spec.password,
        "port": 3050,
        "host": spec.host,
        "generated_id": spec.id,
    }


def fields():
    assert field_specs(FIREBIRD.fields_existing()) == [
        ("host", "text", "localhost"),
        ("port", "int", 3050),
        ("database", "text", None),
        ("username", "text", None),
        ("password", "secret", None),
    ]
    assert FIREBIRD.fields_new() == []
    assert FIREBIRD.option_fields() == []


def from_existing():
    spec = FIREBIRD.from_existing({**EXISTING_ANSWERS, "label": "Prod"})
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="firebird",
        name="Prod",
        host="db.example",
        port=1234,
        database="app",
        username="u",
        password="p",
    )
    assert FIREBIRD.from_existing(EXISTING_ANSWERS).name == "External DB"


def compose_service(render_engine):
    rendered = render_engine("firebird")
    assert rendered.service == {
        "image": "firebirdsql/firebird",
        "restart": "unless-stopped",
        "networks": ["portabase"],
        "ports": [f"{rendered.var('PORT')}:3050"],
        "volumes": [f"{rendered.spec.host}-data:/var/lib/firebird/data"],
        "environment": [
            f"FIREBIRD_DATABASE={rendered.var('DB')}",
            f"FIREBIRD_USER={rendered.var('USER')}",
            f"FIREBIRD_PASSWORD={rendered.var('PASS')}",
            f"FIREBIRD_ROOT_PASSWORD={rendered.var('ROOT_PASS')}",
            "FIREBIRD_DATABASE_DEFAULT_CHARSET=UTF8",
        ],
        "healthcheck": {"test": ["CMD-SHELL", "nc -z localhost 3050"], **HEALTH},
    }


def compose_service_inline(render_engine):
    rendered = render_engine("firebird", inline=True)
    assert rendered.service["ports"] == ["40000:3050"]
    assert rendered.service["environment"] == [
        "FIREBIRD_DATABASE=mirror.fdb",
        "FIREBIRD_USER=alice",
        f"FIREBIRD_PASSWORD={rendered.spec.password}",
        f"FIREBIRD_ROOT_PASSWORD={rendered.spec.root_password}",
        "FIREBIRD_DATABASE_DEFAULT_CHARSET=UTF8",
    ]


def template_ctx_uses_the_file_name(ports):
    spec = FIREBIRD.generate(auth=True, ports=ports, answers={})
    prefix = spec.env_prefix
    ctx = FIREBIRD.template_ctx(spec)
    inline = FIREBIRD.template_ctx(spec, inline=True)
    assert (ctx["db_var"], ctx["root_password_var"]) == (
        f"${{{prefix}_DB}}",
        f"${{{prefix}_ROOT_PASS}}",
    )
    assert (inline["db_var"], inline["root_password_var"]) == (
        "mirror.fdb",
        spec.root_password,
    )
