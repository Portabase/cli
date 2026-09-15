from __future__ import annotations

from rich.align import Align

from ui.components.base import Component
from ui.components.hints import Hint

BANNER = """
[brand]█▀█ █▀█ █▀█ ▀█▀ ▄▀█ █▄▄ ▄▀█ █▀ █▀▀[/brand]
[brand]█▀▀ █▄█ █▀▄  █  █▀█ █▄█ █▀█ ▄█ ██▄[/brand]
[hint]Deploy your infrastructure anywhere.[/hint]
"""


class Banner(Component):
    def __call__(self) -> None:
        self.console.print(Align.center(BANNER))
        self.console.print(Align.center(Hint(self.console).random() + "\n"))
