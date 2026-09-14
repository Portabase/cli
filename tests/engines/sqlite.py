import pytest

from core.specs import DatabaseSpec
from engines import registry
from engines.sqlite import SqliteEngine
from tests.support import agent_service, field_specs

SQLITE = registry.get("sqlite")


def attributes():
    assert type(SQLITE) is SqliteEngine
    assert (SQLITE.key, SQLITE.display, SQLITE.default_port) == (
        "sqlite",
        "SQLite",
        None,
    )
    assert SQLITE.template is None
    assert (SQLITE.auth_variants, SQLITE.has_modes, SQLITE.warning) == (
        False,
        True,
        None,
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (None, "local.sqlite"),
        ("", "local.sqlite"),
        ("app", "app.sqlite"),
        ("app.sqlite", "app.sqlite"),
    ],
)
def generate(ports, name, expected):
    spec = SQLITE.generate(auth=False, ports=ports, answers={"name": name})
    assert spec == DatabaseSpec(
        id=spec.id,
        engine="sqlite",
        name=expected,
        path=expected,
        database=f"/config/{expected}",
    )
    assert SQLITE.describe(spec) == "Local File"


def env_vars(ports):
    spec = SQLITE.generate(auth=False, ports=ports, answers={"name": "app"})
    assert SQLITE.env_vars(spec) == {}


def agent_entry(ports):
    spec = SQLITE.generate(auth=False, ports=ports, answers={"name": "app"})
    assert SQLITE.agent_entry(spec) == {
        "name": "app.sqlite",
        "database": "/config/app.sqlite",
        "type": "sqlite",
        "generated_id": spec.id,
    }


def fields():
    assert field_specs(SQLITE.fields_existing()) == [("path", "text", None)]
    assert field_specs(SQLITE.fields_new()) == [("name", "text", "local")]
    assert SQLITE.option_fields() == []


@pytest.mark.parametrize(
    ("path", "database"),
    [("data/app.db", "/config/data/app.db"), ("/srv/app.db", "/srv/app.db")],
    ids=["relative", "absolute"],
)
def from_existing(path, database):
    spec = SQLITE.from_existing({"path": path, "label": "Prod"})
    assert spec == DatabaseSpec(
        id=spec.id, engine="sqlite", name="Prod", path=path, database=database
    )
    assert SQLITE.from_existing({"path": path}).name == "External DB"


def compose_service(render_engine):
    rendered = render_engine("sqlite", answers={"name": "app"})
    assert rendered.doc["services"] == {
        "agent": agent_service("./app.sqlite:/config/app.sqlite")
    }
    assert "volumes" not in rendered.doc
    assert rendered.databases == [SQLITE.agent_entry(rendered.spec)]


def compose_service_inline(render_engine):
    rendered = render_engine("sqlite", inline=True, answers={"name": "app"})
    assert rendered.doc["services"] == {
        "agent": agent_service("./app.sqlite:/config/app.sqlite", inline=True)
    }


@pytest.mark.parametrize(
    ("database", "mount"),
    [
        ("/config/app.sqlite", ("./app.sqlite", "/config/app.sqlite")),
        ("/config/data/app.db", ("./data/app.db", "/config/data/app.db")),
        ("/srv/app.db", None),
        (None, None),
    ],
)
def mount_for(database, mount):
    spec = DatabaseSpec(id="1", engine="sqlite", name="n", database=database)
    assert SqliteEngine.mount_for(spec) == mount
