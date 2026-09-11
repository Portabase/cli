from __future__ import annotations

from rich.console import Console


class Component:
    def __init__(self, console: Console) -> None:
        self.console = console
