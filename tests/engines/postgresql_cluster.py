import re
from typing import cast

import pytest
import yaml

from core.errors import ValidationError
from core.specs import DatabaseSpec
from engines import registry
from engines.postgresql import PostgresClusterEngine
from services.project import AgentProject
from tests.support import AGENT_ENV, EXISTING_ANSWERS, agent_service, field_specs
from ui.components.prompt import Prompt
from ui.form import Form

CLUSTER = registry.get("postgresql-cluster")
HEALTH = {"interval": "10s", "timeout": "5s", "retries": 5}
FORM = Form(cast(Prompt, None), non_interactive=True)
PHYSICAL = {"method": "physical", "full_every_days": 7}


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
    assert field_specs(CLUSTER.option_fields()) == [
        ("method", "choice", "archive"),
        ("full_every_days", "int", 7),
    ]
    assert CLUSTER.option_fields()[0].choices == ("archive", "physical")


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


def archive_writes_no_options():
    options = FORM.collect(CLUSTER.option_fields(), {"method": "archive"})
    spec = CLUSTER.from_existing(EXISTING_ANSWERS).with_options(options)
    assert "options" not in CLUSTER.agent_entry(spec)
    assert CLUSTER.mount_for(spec) is None


def physical_reaches_the_agent():
    options = FORM.collect(CLUSTER.option_fields(), {"method": "physical"})
    assert options == PHYSICAL
    spec = CLUSTER.from_existing(EXISTING_ANSWERS).with_options(options)
    assert CLUSTER.agent_entry(spec)["options"] == {"method": "physical"}
    longer = FORM.collect(
        CLUSTER.option_fields(), {"method": "physical", "full_every_days": "14"}
    )
    assert CLUSTER.agent_entry(spec.with_options(longer))["options"] == {
        "method": "physical",
        "full_every_days": 14,
    }


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ({"method": "physical", "full_every_days": "0"}, "at least 1"),
        ({"method": "physical", "full_every_days": "x"}, "whole number"),
        ({"method": "archive", "full_every_days": "3"}, "does not apply"),
        ({"method": "wal"}, "Invalid value"),
    ],
)
def physical_options_are_checked(answers, message):
    with pytest.raises(ValidationError, match=message):
        FORM.collect(CLUSTER.option_fields(), answers)


def physical_is_refused_on_a_new_database(ports):
    with pytest.raises(ValidationError, match="existing"):
        CLUSTER.generate(auth=True, ports=ports, answers={"options": PHYSICAL})


def physical_compose_mounts_the_restore_folder(tmp_path, renderer):
    project = AgentProject.create(tmp_path, dict(AGENT_ENV), host_gateway=False)
    spec = CLUSTER.from_existing(EXISTING_ANSWERS).with_options(PHYSICAL)
    project.add(spec, CLUSTER)
    project.add(CLUSTER.from_existing(EXISTING_ANSWERS).with_options(PHYSICAL), CLUSTER)
    result = renderer.render_agent(project, inline=False)
    result.validate()
    agent = yaml.safe_load(result.compose)["services"]["agent"]
    expected = agent_service("./restores:/restores")
    expected["environment"]["RESTORE_PATH"] = "/restores"
    assert agent == expected


def archive_compose_has_no_restore_folder(tmp_path, renderer):
    project = AgentProject.create(tmp_path, dict(AGENT_ENV), host_gateway=False)
    project.add(CLUSTER.from_existing(EXISTING_ANSWERS), CLUSTER)
    result = renderer.render_agent(project, inline=False)
    assert yaml.safe_load(result.compose)["services"]["agent"] == agent_service()
