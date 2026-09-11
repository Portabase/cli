from __future__ import annotations

from rich.panel import Panel

from ui.components.base import Component


class Section(Component):
    def __call__(self, title: str) -> None:
        self.console.print("")
        self.console.print(Panel(f"[bold]{title}[/bold]", style="cyan", expand=False))
