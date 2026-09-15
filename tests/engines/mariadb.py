import re

from core.specs import DatabaseSpec
from engines import registry
from engines.mariadb import MariaDbEngine
from tests.support import EXISTING_ANSWERS, field_specs

MARIADB = registry.get("mariadb")
HEALTH = {"interval": "10s", "timeout": "5s", "retries": 5}


def attributes():
    assert type(MARIADB) is MariaDbEngine
    assert (MARIADB.key, MARIADB.display, MARIADB.default_port) == (
        "mariadb",
        "MariaDB",
        3306,
    )
    assert MARIADB.template == "engines/mariadb.yml.j2"
    assert (MARIADB.auth_variants, MARIADB.has_modes, MARIADB.warning) == (
        False,
        True,
        None,
    )


def generate(ports):
    spec = MARIADB.generate(auth=True, ports=ports, answers={})
    assert re.fullmatch(r"db-mariadb-[0-9a-f]{4}", spec.host or "")
    assert re.fullmatch(r"mysql_[0-9a-f]{8}", spec.database or "")
    assert len(spec.password or "") == 16
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="mariadb",
        name=spec.database or "",
        managed=True,
        host=spec.host,
        port=3306,
        host_port=40000,
        database=spec.database,
        username="admin",
        password=spec.password,
    )
    assert MARIADB.describe(spec) == f"{spec.host}:3306"


def env_vars(ports):
    spec = MARIADB.generate(auth=True, ports=ports, answers={})
    prefix = spec.env_prefix
    assert MARIADB.env_vars(spec) == {
        f"{prefix}_PORT": "40000",
        f"{prefix}_DB": spec.database,
        f"{prefix}_USER": "admin",
        f"{prefix}_PASS": spec.password,
    }


def agent_entry(ports):
    spec = MARIADB.generate(auth=True, ports=ports, answers={})
    assert MARIADB.agent_entry(spec) == {
        "name": spec.name,
        "database": spec.database,
        "type": "mariadb",
        "username": "admin",
        "password": spec.password,
        "port": 3306,
        "host": spec.host,
        "generated_id": spec.id,
    }


def fields():
    assert field_specs(MARIADB.fields_existing()) == [
        ("host", "text", "localhost"),
        ("port", "int", 3306),
        ("database", "text", None),
        ("username", "text", None),
        ("password", "secret", None),
    ]
    assert MARIADB.fields_new() == []
    assert MARIADB.option_fields() == []


def from_existing():
    spec = MARIADB.from_existing({**EXISTING_ANSWERS, "label": "Prod"})
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="mariadb",
        name="Prod",
        host="db.example",
        port=1234,
        database="app",
        username="u",
        password="p",
    )
    assert MARIADB.from_existing(EXISTING_ANSWERS).name == "External DB"


def compose_service(render_engine):
    rendered = render_engine("mariadb")
    assert rendered.service == {
        "image": "mariadb:latest",
        "restart": "unless-stopped",
        "networks": ["portabase"],
        "ports": [f"{rendered.var('PORT')}:3306"],
        "environment": [
            f"MYSQL_DATABASE={rendered.var('DB')}",
            f"MYSQL_USER={rendered.var('USER')}",
            f"MYSQL_PASSWORD={rendered.var('PASS')}",
            "MYSQL_RANDOM_ROOT_PASSWORD=yes",
        ],
        "volumes": [f"{rendered.spec.host}-data:/var/lib/mysql"],
        "healthcheck": {
            "test": [
                "CMD-SHELL",
                f"mariadb-admin ping -h localhost -u {rendered.var('USER')} -p{rendered.var('PASS')}",
            ],
            **HEALTH,
        },
    }


def compose_service_inline(render_engine):
    rendered = render_engine("mariadb", inline=True)
    assert rendered.service["ports"] == ["40000:3306"]
    assert rendered.service["environment"] == [
        f"MYSQL_DATABASE={rendered.spec.database}",
        "MYSQL_USER=admin",
        f"MYSQL_PASSWORD={rendered.spec.password}",
        "MYSQL_RANDOM_ROOT_PASSWORD=yes",
    ]
