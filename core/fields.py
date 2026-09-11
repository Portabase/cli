from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

FieldKind = Literal["text", "int", "secret", "bool", "choice", "path"]


@dataclass(frozen=True)
class Field:
    name: str
    prompt: str
    kind: FieldKind = "text"
    default: Any = None
    choices: tuple[str, ...] = ()
    help: str | None = None
    validator: Callable[[Any], Any] | None = None

    @property
    def flag(self) -> str:
        return "--" + self.name.replace("_", "-")
