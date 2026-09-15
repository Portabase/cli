from __future__ import annotations

import re

from rich.panel import Panel
from rich.table import Table

from ui.components.base import Component

_SENSITIVE = re.compile(r"(password|secret|key|token)", re.I)
_URL_CREDS = re.compile(r"://([^:/@]+):([^@/]+)@")


def mask(label: str, value: str) -> str:
    if _SENSITIVE.search(label):
        return "••••••••"
    return _URL_CREDS.sub(r"://\1:****@", value)


class Summary(Component):
    def __call__(
        self, rows: list[tuple[str, str]], *, title: str | None = None
    ) -> None:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Property", style="bold cyan")
        table.add_column("Value", style="white")
        for label, value in rows:
            table.add_row(label, mask(label, str(value)))
        self.console.print("")
        self.console.print(
            Panel(
                table,
                title=f"[bold white]{title}[/bold white]" if title else None,
                border_style="bold blue",
                expand=False,
            )
        )
