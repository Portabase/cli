from __future__ import annotations

from collections.abc import Sequence

import questionary
from questionary import Style
from rich.console import Console

from ui.components.base import Component


class Prompt(Component):
    def __init__(self, console: Console, style: Style) -> None:
        super().__init__(console)
        self.style = style

    def text(self, message: str, *, default: str | None = None) -> str | None:
        return questionary.text(message, default=default or "", style=self.style).ask()

    def integer(self, message: str, *, default: int | None = None) -> int | None:
        answer = questionary.text(
            message,
            default="" if default is None else str(default),
            validate=lambda value: (
                value.strip().lstrip("-").isdigit() or "Enter a whole number"
            ),
            style=self.style,
        ).ask()
        return None if answer is None else int(answer)

    def secret(self, message: str) -> str | None:
        return questionary.password(message, style=self.style).ask()

    def confirm(self, message: str, *, default: bool = False) -> bool | None:
        return questionary.confirm(message, default=default, style=self.style).ask()

    def select(
        self, message: str, choices: Sequence[str], *, default: str | None = None
    ) -> str | None:
        return questionary.select(
            message, choices=list(choices), default=default, style=self.style
        ).ask()

    def path(self, message: str, *, default: str | None = None) -> str | None:
        return questionary.path(message, default=default or "", style=self.style).ask()
