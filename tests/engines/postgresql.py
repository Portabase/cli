import re

from core.specs import DatabaseSpec
from engines import registry
from engines.postgresql import PostgresEngine
from tests.support import EXISTING_ANSWERS, field_specs

PG = registry.get("postgresql")
HEALTH = {"interval": "10s", "timeout": "5s", "retries": 5}


def attributes():
    assert type(PG) is PostgresEngine
    assert (PG.key, PG.display, PG.default_port) == ("postgresql", "PostgreSQL", 5432)
    assert PG.template == "engines/postgresql.yml.j2"
    assert (PG.auth_variants, PG.has_modes, PG.warning) == (False, True, None)


def generate(ports):
    spec = PG.generate(auth=True, ports=ports, answers={})
    assert re.fullmatch(r"db-pg-[0-9a-f]{4}", spec.host or "")
    assert re.fullmatch(r"pg_[0-9a-f]{8}", spec.database or "")
    assert len(spec.password or "") == 16
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="postgresql",
        name=spec.database or "",
        managed=True,
        host=spec.host,
        port=5432,
        host_port=40000,
        database=spec.database,
        username="admin",
        password=spec.password,
    )
    assert PG.describe(spec) == f"{spec.host}:5432"


def env_vars(ports):
    spec = PG.generate(auth=True, ports=ports, answers={})
    prefix = spec.env_prefix
    assert PG.env_vars(spec) == {
        f"{prefix}_PORT": "40000",
        f"{prefix}_DB": spec.database,
        f"{prefix}_USER": "admin",
        f"{prefix}_PASS": spec.password,
    }


def agent_entry(ports):
    spec = PG.generate(auth=True, ports=ports, answers={})
    assert PG.agent_entry(spec) == {
        "name": spec.name,
        "database": spec.database,
        "type": "postgresql",
        "username": "admin",
        "password": spec.password,
        "port": 5432,
        "host": spec.host,
        "generated_id": spec.id,
    }


def fields():
    assert field_specs(PG.fields_existing()) == [
        ("host", "text", "localhost"),
        ("port", "int", 5432),
        ("database", "text", None),
        ("username", "text", None),
        ("password", "secret", None),
    ]
    assert PG.fields_new() == []
    assert field_specs(PG.option_fields()) == [
        ("keep_ownership", "bool", False),
        ("clean_mode", "choice", "clean"),
    ]
    assert PG.option_fields()[1].choices == (
        "clean",
        "none",
        "drop_schemas",
        "drop_database",
    )


def from_existing():
    spec = PG.from_existing({**EXISTING_ANSWERS, "label": "Prod"})
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="postgresql",
        name="Prod",
        host="db.example",
        port=1234,
        database="app",
        username="u",
        password="p",
    )
    assert PG.from_existing(EXISTING_ANSWERS).name == "External DB"


def compose_service(render_engine):
    rendered = render_engine("postgresql")
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
    rendered = render_engine("postgresql", inline=True)
    assert rendered.service["ports"] == ["40000:5432"]
    assert rendered.service["environment"] == [
        f"POSTGRES_DB={rendered.spec.database}",
        "POSTGRES_USER=admin",
        f"POSTGRES_PASSWORD={rendered.spec.password}",
    ]


def only_non_default_options_reach_the_agent(ports):
    options = {"keep_ownership": True, "clean_mode": "clean", "unknown": 1}
    spec = PG.generate(auth=True, ports=ports, answers={"options": options})
    assert spec.options == options
    assert PG.non_default_options(spec) == {"keep_ownership": True}
    assert PG.agent_entry(spec)["options"] == {"keep_ownership": True}
    assert "options" not in PG.agent_entry(spec.with_options({"clean_mode": "clean"}))
