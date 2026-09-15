from __future__ import annotations

from collections.abc import Iterable, Iterator

from core.errors import ValidationError
from engines.base import DbEngine
from engines.docker_volume import DockerVolumeEngine
from engines.firebird import FirebirdEngine
from engines.mariadb import MariaDbEngine
from engines.mongodb import MongoEngine
from engines.mssql import MssqlEngine
from engines.mysql import MySqlEngine
from engines.postgresql import PostgresClusterEngine, PostgresEngine
from engines.redis import RedisEngine
from engines.sqlite import SqliteEngine
from engines.valkey import ValkeyEngine


class EngineRegistry:
    def __init__(self, engines: Iterable[DbEngine]) -> None:
        self._by_key: dict[str, DbEngine] = {}
        for engine in engines:
            if engine.key in self._by_key:
                raise ValueError(f"Duplicate engine key: {engine.key}")
            self._by_key[engine.key] = engine

    def get(self, key: str) -> DbEngine:
        try:
            return self._by_key[key]
        except KeyError:
            raise ValidationError(
                f"Unknown engine '{key}'.",
                hint="Available: " + ", ".join(self.keys()),
            ) from None

    def keys(self) -> list[str]:
        return list(self._by_key)

    def choices(self) -> list[str]:
        return self.keys()

    def __iter__(self) -> Iterator[DbEngine]:
        return iter(self._by_key.values())

    def __contains__(self, key: str) -> bool:
        return key in self._by_key


ALL = (
    PostgresEngine(),
    PostgresClusterEngine(),
    MySqlEngine(),
    MariaDbEngine(),
    SqliteEngine(),
    FirebirdEngine(),
    MongoEngine(),
    RedisEngine(),
    ValkeyEngine(),
    MssqlEngine(),
    DockerVolumeEngine(),
)

registry = EngineRegistry(ALL)

__all__ = ["ALL", "EngineRegistry", "registry"]
