import pytest

from core.errors import ValidationError
from engines import ALL, EngineRegistry, registry
from engines.postgresql import PostgresEngine

EXPECTED = [
    "postgresql",
    "postgresql-cluster",
    "mysql",
    "mariadb",
    "sqlite",
    "firebird",
    "mongodb",
    "redis",
    "valkey",
    "mssql",
    "docker-volume",
]


def keys_in_order():
    assert registry.keys() == EXPECTED
    assert registry.choices() == EXPECTED
    assert [engine.key for engine in registry] == EXPECTED
    assert "redis" in registry
    assert "nope" not in registry


def get_engine():
    assert isinstance(registry.get("postgresql"), PostgresEngine)
    with pytest.raises(ValidationError, match="Unknown engine 'nope'") as exc:
        registry.get("nope")
    assert "postgresql" in (exc.value.hint or "")


def duplicate_keys_are_refused():
    with pytest.raises(ValueError, match="Duplicate engine key: postgresql"):
        EngineRegistry([*ALL, PostgresEngine()])


def templates_match_engines(templates):
    shipped = {name for name in templates.names() if name.startswith("engines/")}
    used = {engine.template for engine in registry if engine.template is not None}
    assert used == shipped
    for name in used:
        templates.get(name)
