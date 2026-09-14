import re

from core.specs import DatabaseSpec
from engines import registry
from engines.postgresql import PostgresClusterEngine
from tests.support import EXISTING_ANSWERS, field_specs

CLUSTER = registry.get("postgresql-cluster")
HEALTH = {"interval": "10s", "timeout": "5s", "retries": 5}


def attributes():
    assert type(CLUSTER) is PostgresClusterEngine
    assert (CLUSTER.key, CLUSTER.display, CLUSTER.default_port) == (
        "postgresql-cluster",
        "PostgreSQL Cluster",
        5432,
    )
    assert CLUSTER.template == "engines/postgresql-cluster.yml.j2"
    assert (CLUSTER.auth_variants, CLUSTER.has_modes) == (False, True)
    assert "superuser" in (CLUSTER.warning or "")
    assert "pg_dumpall" in (CLUSTER.warning or "")


def generate(ports):
    spec = CLUSTER.generate(auth=True, ports=ports, answers={})
    assert re.fullmatch(r"db-pg-[0-9a-f]{4}", spec.host or "")
    assert re.fullmatch(r"pg_[0-9a-f]{8}", spec.database or "")
    assert len(spec.password or "") == 16
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="postgresql-cluster",
        name=spec.database or "",
        managed=True,
        host=spec.host,
        port=5432,
        host_port=40000,
        database=spec.database,
        username="admin",
        password=spec.password,
    )
    assert CLUSTER.describe(spec) == f"{spec.host}:5432"


def env_vars(ports):
    spec = CLUSTER.generate(auth=True, ports=ports, answers={})
    prefix = spec.env_prefix
    assert CLUSTER.env_vars(spec) == {
        f"{prefix}_PORT": "40000",
        f"{prefix}_DB": spec.database,
        f"{prefix}_USER": "admin",
        f"{prefix}_PASS": spec.password,
    }


def agent_entry(ports):
    spec = CLUSTER.generate(auth=True, ports=ports, answers={})
    assert CLUSTER.agent_entry(spec) == {
        "name": spec.name,
        "database": spec.database,
        "type": "postgresql-cluster",
        "username": "admin",
        "password": spec.password,
        "port": 5432,
        "host": spec.host,
        "generated_id": spec.id,
    }


def fields():
    assert field_specs(CLUSTER.fields_existing()) == [
        ("host", "text", "localhost"),
        ("port", "int", 5432),
        ("database", "text", None),
        ("username", "text", None),
        ("password", "secret", None),
    ]
    assert CLUSTER.fields_new() == []
    assert CLUSTER.option_fields() == []


def from_existing():
    spec = CLUSTER.from_existing({**EXISTING_ANSWERS, "label": "Prod"})
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="postgresql-cluster",
        name="Prod",
        host="db.example",
        port=1234,
        database="app",
        username="u",
        password="p",
    )
    assert CLUSTER.from_existing(EXISTING_ANSWERS).name == "External DB"


def compose_service(render_engine):
    rendered = render_engine("postgresql-cluster")
    assert rendered.service == {
        "image": "postgres:17-alpine",
        "restart": "unless-stopped",
        "networks": ["portabase"],
        "ports": [f"{rendered.var('PORT')}:5432"],
        "volumes": [f"{rendered.spec.host}-data:/var/lib/postgresql/data"],
        "environment": [
            f"POSTGRES_DB={rendered.var('DB')}",
            f"POSTGRES_USER={rendered.var('USER')}",
            f"POSTGRES_PASSWORD={rendered.var('PASS')}",
        ],
        "healthcheck": {
            "test": [
                "CMD-SHELL",
                f"pg_isready -U {rendered.var('USER')} -d {rendered.var('DB')}",
            ],
            **HEALTH,
        },
    }


def compose_service_inline(render_engine):
    rendered = render_engine("postgresql-cluster", inline=True)
    assert rendered.service["ports"] == ["40000:5432"]
    assert rendered.service["environment"] == [
        f"POSTGRES_DB={rendered.spec.database}",
        "POSTGRES_USER=admin",
        f"POSTGRES_PASSWORD={rendered.spec.password}",
    ]


def options_are_dropped(ports):
    spec = CLUSTER.generate(
        auth=True, ports=ports, answers={"options": {"keep_ownership": True}}
    )
    assert CLUSTER.non_default_options(spec) == {}
    assert "options" not in CLUSTER.agent_entry(spec)
