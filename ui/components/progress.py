from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from rich.progress import (
    BarColumn,
    DownloadColumn,
    SpinnerColumn,
    TextColumn,
    TransferSpeedColumn,
)
from rich.progress import Progress as RichProgress

from ui.components.base import Component
from ui.components.hints import Hint


class Progress(Component):
    @contextmanager
    def download(self, description: str, total: int) -> Iterator[Callable[[int], None]]:
        with RichProgress(
            SpinnerColumn(),
            TextColumn(
                "[progress.description]{task.description}\n"
                + Hint(self.console).random()
            ),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(description, total=total or None)
            yield lambda n: progress.update(task, advance=n)
