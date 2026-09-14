from __future__ import annotations

from contextlib import AbstractContextManager

from ui.components.base import Component
from ui.components.hints import Hint


class Status(Component):
    def __call__(self, text: str, *, spinner: str = "dots") -> AbstractContextManager:
        message = f"[bold magenta]{text}[/bold magenta]\n{Hint(self.console).random()}"
        return self.console.status(message, spinner=spinner)
