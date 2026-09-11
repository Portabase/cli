from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class Telemetry(ABC):
    @abstractmethod
    def session(self, **attrs: Any): ...

    @abstractmethod
    def span(self, name: str, **attrs: Any): ...

    @abstractmethod
    def event(self, name: str, **attrs: Any) -> None: ...

    @abstractmethod
    def error(self, exc: BaseException, *, unexpected: bool = False) -> None: ...

    def flush(self) -> None:
        return None


class NoopTelemetry(Telemetry):
    @contextmanager
    def session(self, **attrs: Any) -> Iterator[None]:
        yield

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[None]:
        yield

    def event(self, name: str, **attrs: Any) -> None:
        return None

    def error(self, exc: BaseException, *, unexpected: bool = False) -> None:
        return None
