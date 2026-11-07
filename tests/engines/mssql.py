import re
from typing import cast

import pytest
import yaml

from core.errors import ValidationError
from core.specs import DatabaseSpec
from engines import registry
from engines.mssql import MssqlEngine
from services.project import AgentProject
from tests.support import AGENT_ENV, EXISTING_ANSWERS, agent_service, field_specs
from ui.components.prompt import Prompt
from ui.form import Form

MSSQL = registry.get("mssql")
FORM = Form(cast(Prompt, None), non_interactive=True)
BAK_OPTIONS = {
    "backup_format": "bak",
    "bak_server_path": r"D:\PortabaseBackups",
    "bak_agent_path": "/mnt/sql-backups",
}


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
    assert field_specs(MSSQL.option_fields()) == [
        ("backup_format", "choice", "dacpac"),
        ("bak_server_path", "text", ""),
        ("bak_agent_path", "text", ""),
        ("bak_verify", "bool", False),
    ]
    assert MSSQL.option_fields()[0].choices == ("dacpac", "bacpac", "bak")


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


def only_non_default_options_reach_the_agent(ports):
    spec = MSSQL.generate(auth=True, ports=ports, answers={})
    bacpac = spec.with_options({"backup_format": "bacpac", "unknown": 1})
    assert MSSQL.non_default_options(bacpac) == {"backup_format": "bacpac"}
    assert MSSQL.agent_entry(bacpac)["options"] == {"backup_format": "bacpac"}
    dacpac = spec.with_options({"backup_format": "dacpac"})
    assert "options" not in MSSQL.agent_entry(dacpac)


def bak_options_reach_the_agent():
    options = FORM.collect(MSSQL.option_fields(), {**BAK_OPTIONS, "bak_verify": "yes"})
    spec = MSSQL.from_existing(EXISTING_ANSWERS).with_options(options)
    assert MSSQL.agent_entry(spec)["options"] == {**BAK_OPTIONS, "bak_verify": True}


def bak_verify_off_is_not_written():
    options = FORM.collect(MSSQL.option_fields(), BAK_OPTIONS)
    spec = MSSQL.from_existing(EXISTING_ANSWERS).with_options(options)
    assert MSSQL.agent_entry(spec)["options"] == BAK_OPTIONS


def bak_mounts_the_folder_on_the_agent():
    spec = MSSQL.from_existing(EXISTING_ANSWERS)
    assert MSSQL.mount_for(spec) is None
    assert MSSQL.mount_for(spec.with_options({"backup_format": "bacpac"})) is None
    assert MSSQL.mount_for(spec.with_options(BAK_OPTIONS)) == (
        "/mnt/sql-backups",
        "/mnt/sql-backups",
    )


@pytest.mark.parametrize("backup_format", ["dacpac", "bacpac"])
def bak_options_only_apply_to_bak(backup_format):
    options = FORM.collect(MSSQL.option_fields(), {"backup_format": backup_format})
    assert options == {"backup_format": backup_format}
    with pytest.raises(ValidationError, match="--bak-server-path does not apply"):
        FORM.collect(
            MSSQL.option_fields(),
            {"backup_format": backup_format, "bak_server_path": "D:\\x"},
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"bak_server_path": "  "}, "bak_server_path"),
        ({"bak_agent_path": ""}, "bak_agent_path"),
        ({"bak_agent_path": "mnt/sql-backups"}, "absolute"),
        ({"bak_agent_path": "/"}, "absolute"),
        ({"bak_agent_path": "/mnt/a:b"}, "cannot contain"),
    ],
)
def bak_paths_are_required_and_checked(overrides, message):
    with pytest.raises(ValidationError, match=message):
        FORM.collect(MSSQL.option_fields(), {**BAK_OPTIONS, **overrides})


def bak_is_refused_on_a_new_database(ports):
    with pytest.raises(ValidationError, match="existing"):
        MSSQL.generate(auth=True, ports=ports, answers={"options": BAK_OPTIONS})


def bak_compose_mounts_the_folder(tmp_path, renderer):
    project = AgentProject.create(tmp_path, dict(AGENT_ENV), host_gateway=False)
    spec = MSSQL.from_existing(EXISTING_ANSWERS).with_options(BAK_OPTIONS)
    project.add(spec, MSSQL)
    result = renderer.render_agent(project, inline=False)
    result.validate()
    doc = yaml.safe_load(result.compose)
    assert doc["services"] == {
        "agent": agent_service("/mnt/sql-backups:/mnt/sql-backups")
    }
    assert result.databases == [MSSQL.agent_entry(spec)]
