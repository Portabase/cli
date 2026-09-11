from __future__ import annotations

from rich.table import Table

from ui.components.base import Component

_STYLES = ["cyan", "blue", "magenta", "green", "white", "dim"]


class DataTable(Component):
    def __call__(
        self, columns: list[str], rows: list[list[str]], *, title: str | None = None
    ) -> None:
        table = Table(title=title)
        for i, col in enumerate(columns):
            table.add_column(col, style=_STYLES[i % len(_STYLES)])
        for row in rows:
            table.add_row(*[str(c) for c in row])
        self.console.print(table)
