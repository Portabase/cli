import re

from core.specs import DatabaseSpec
from engines import registry
from engines.mssql import MssqlEngine
from tests.support import EXISTING_ANSWERS, field_specs

MSSQL = registry.get("mssql")


def attributes():
    assert type(MSSQL) is MssqlEngine
    assert (MSSQL.key, MSSQL.display, MSSQL.default_port) == (
        "mssql",
        "Microsoft SQL Server",
        1433,
    )
    assert MSSQL.template == "engines/mssql.yml.j2"
    assert (MSSQL.auth_variants, MSSQL.has_modes, MSSQL.warning) == (False, True, None)


def generate(ports):
    spec = MSSQL.generate(auth=True, ports=ports, answers={})
    assert re.fullmatch(r"db-mssql-[0-9a-f]{4}", spec.host or "")
    assert len(spec.password or "") == 16
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="mssql",
        name="MSSQL",
        managed=True,
        host=spec.host,
        port=1433,
        host_port=40000,
        database="master",
        username="sa",
        password=spec.password,
    )
    assert MSSQL.describe(spec) == f"{spec.host}:1433"


def env_vars(ports):
    spec = MSSQL.generate(auth=True, ports=ports, answers={})
    prefix = spec.env_prefix
    assert MSSQL.env_vars(spec) == {
        f"{prefix}_PORT": "40000",
        f"{prefix}_PASS": spec.password,
    }


def agent_entry(ports):
    spec = MSSQL.generate(auth=True, ports=ports, answers={})
    assert MSSQL.agent_entry(spec) == {
        "name": "MSSQL",
        "database": "master",
        "type": "mssql",
        "username": "sa",
        "password": spec.password,
        "port": 1433,
        "host": spec.host,
        "generated_id": spec.id,
    }


def fields():
    assert field_specs(MSSQL.fields_existing()) == [
        ("host", "text", "localhost"),
        ("port", "int", 1433),
        ("database", "text", None),
        ("username", "text", None),
        ("password", "secret", None),
    ]
    assert MSSQL.fields_new() == []
    assert MSSQL.option_fields() == []


def from_existing():
    spec = MSSQL.from_existing({**EXISTING_ANSWERS, "label": "Prod"})
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="mssql",
        name="Prod",
        host="db.example",
        port=1234,
        database="app",
        username="u",
        password="p",
    )
    assert MSSQL.from_existing(EXISTING_ANSWERS).name == "External DB"


def compose_service(render_engine):
    rendered = render_engine("mssql")
    assert rendered.service == {
        "image": "mcr.microsoft.com/azure-sql-edge:latest",
        "restart": "unless-stopped",
        "networks": ["portabase"],
        "ports": [f"{rendered.var('PORT')}:1433"],
        "environment": ["ACCEPT_EULA=Y", f"MSSQL_SA_PASSWORD={rendered.var('PASS')}"],
        "volumes": [f"{rendered.spec.host}-data:/var/opt/mssql"],
        "healthcheck": {
            "test": ["CMD-SHELL", "cat /proc/net/tcp6 | grep -q '059901' || exit 1"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 20,
        },
    }


def compose_service_inline(render_engine):
    rendered = render_engine("mssql", inline=True)
    assert rendered.service["ports"] == ["40000:1433"]
    assert rendered.service["environment"] == [
        "ACCEPT_EULA=Y",
        f"MSSQL_SA_PASSWORD={rendered.spec.password}",
    ]


def options_are_ignored(ports):
    spec = MSSQL.generate(auth=True, ports=ports, answers={"options": {"x": 1}})
    assert spec.options == {}
