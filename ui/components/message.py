from __future__ import annotations

import traceback

from core.errors import PortabaseError
from ui.components.base import Component


class Message(Component):
    def success(self, text: str) -> None:
        self.console.print(f"[success]✔ {text}[/success]")

    def info(self, text: str) -> None:
        self.console.print(f"[info]ℹ {text}[/info]")

    def warning(self, text: str) -> None:
        self.console.print(f"[warning]⚠ {text}[/warning]")

    def error(
        self, exc: PortabaseError, *, verbose: bool = False, unexpected: bool = False
    ) -> None:
        label = "Unexpected error" if unexpected else "Error"
        self.console.print(f"[danger]✖ {label}:[/danger] {exc.message}")
        if exc.hint:
            self.console.print(f"  [hint]↳ {exc.hint}[/hint]")
        if verbose or unexpected:
            self.console.print(f"  [hint]code: {exc.code}[/hint]")
        if verbose and exc.cause is not None:
            self.console.print(
                f"  [hint]cause: {type(exc.cause).__name__}: {exc.cause}[/hint]"
            )
        if verbose:
            self.console.print(
                "".join(traceback.format_exception(exc)), highlight=False, markup=False
            )
