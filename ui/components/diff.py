from __future__ import annotations

from rich.syntax import Syntax

from ui.components.base import Component


class Diff(Component):
    def __call__(self, text: str) -> None:
        if not text.strip():
            self.console.print("[info]ℹ No changes.[/info]")
            return
        self.console.print(Syntax(text, "diff", theme="ansi_dark", word_wrap=False))
