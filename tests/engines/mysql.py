import re

from core.specs import DatabaseSpec
from engines import registry
from engines.mariadb import MariaDbEngine
from engines.mysql import MySqlEngine
from tests.support import EXISTING_ANSWERS, field_specs

MYSQL = registry.get("mysql")
HEALTH = {"interval": "10s", "timeout": "5s", "retries": 5}


def attributes():
    assert type(MYSQL) is MySqlEngine
    assert isinstance(MYSQL, MariaDbEngine)
    assert (MYSQL.key, MYSQL.display, MYSQL.default_port) == ("mysql", "MySQL", 3306)
    assert MYSQL.template == "engines/mysql.yml.j2"
    assert (MYSQL.auth_variants, MYSQL.has_modes, MYSQL.warning) == (False, True, None)


def generate(ports):
    spec = MYSQL.generate(auth=True, ports=ports, answers={})
    assert re.fullmatch(r"db-mariadb-[0-9a-f]{4}", spec.host or "")
    assert re.fullmatch(r"mysql_[0-9a-f]{8}", spec.database or "")
    assert len(spec.password or "") == 16
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="mysql",
        name=spec.database or "",
        managed=True,
        host=spec.host,
        port=3306,
        host_port=40000,
        database=spec.database,
        username="admin",
        password=spec.password,
    )
    assert MYSQL.describe(spec) == f"{spec.host}:3306"


def env_vars(ports):
    spec = MYSQL.generate(auth=True, ports=ports, answers={})
    prefix = spec.env_prefix
    assert MYSQL.env_vars(spec) == {
        f"{prefix}_PORT": "40000",
        f"{prefix}_DB": spec.database,
        f"{prefix}_USER": "admin",
        f"{prefix}_PASS": spec.password,
    }


def agent_entry(ports):
    spec = MYSQL.generate(auth=True, ports=ports, answers={})
    assert MYSQL.agent_entry(spec) == {
        "name": spec.name,
        "database": spec.database,
        "type": "mysql",
        "username": "admin",
        "password": spec.password,
        "port": 3306,
        "host": spec.host,
        "generated_id": spec.id,
    }


def fields():
    assert field_specs(MYSQL.fields_existing()) == [
        ("host", "text", "localhost"),
        ("port", "int", 3306),
        ("database", "text", None),
        ("username", "text", None),
        ("password", "secret", None),
    ]
    assert MYSQL.fields_new() == []
    assert MYSQL.option_fields() == []


def from_existing():
    spec = MYSQL.from_existing({**EXISTING_ANSWERS, "label": "Prod"})
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="mysql",
        name="Prod",
        host="db.example",
        port=1234,
        database="app",
        username="u",
        password="p",
    )
    assert MYSQL.from_existing(EXISTING_ANSWERS).name == "External DB"


def compose_service(render_engine):
    rendered = render_engine("mysql")
    assert rendered.service == {
        # MySQL databases have always run on the MariaDB image (wire compatible).
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
    rendered = render_engine("mysql", inline=True)
    assert rendered.service["ports"] == ["40000:3306"]
    assert rendered.service["environment"] == [
        f"MYSQL_DATABASE={rendered.spec.database}",
        "MYSQL_USER=admin",
        f"MYSQL_PASSWORD={rendered.spec.password}",
        "MYSQL_RANDOM_ROOT_PASSWORD=yes",
    ]
