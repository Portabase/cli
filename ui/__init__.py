from __future__ import annotations

import sys

from rich.console import Console

from core.errors import PortabaseError
from ui.components.banner import Banner
from ui.components.diff import Diff
from ui.components.hints import Hint
from ui.components.message import Message
from ui.components.progress import Progress
from ui.components.prompt import Prompt
from ui.components.section import Section
from ui.components.status import Status
from ui.components.summary import Summary
from ui.components.table import DataTable
from ui.form import Form
from ui.theme import QUESTIONARY_STYLE, QUESTIONARY_STYLE_PLAIN, RICH_THEME


class UI:
    def __init__(
        self,
        console: Console | None = None,
        *,
        non_interactive: bool = False,
        verbose: bool = False,
        no_color: bool = False,
    ) -> None:
        self.non_interactive = non_interactive
        self.verbose = verbose
        self.no_color = no_color
        self.console = console or self._make_console()

    def configure(
        self,
        *,
        non_interactive: bool | None = None,
        verbose: bool | None = None,
        no_color: bool | None = None,
    ) -> None:
        if non_interactive is not None:
            self.non_interactive = non_interactive
        if verbose is not None:
            self.verbose = verbose
        if no_color is not None and no_color != self.no_color:
            self.no_color = no_color
            self.console = self._make_console()

    def _make_console(self) -> Console:
        return Console(theme=RICH_THEME, no_color=self.no_color)

    def print(self, renderable, **kwargs) -> None:
        self.console.print(renderable, **kwargs)

    def out(self, text: str) -> None:
        sys.stdout.write(text)

    def banner(self) -> None:
        Banner(self.console)()

    def success(self, text: str) -> None:
        Message(self.console).success(text)

    def info(self, text: str) -> None:
        Message(self.console).info(text)

    def warning(self, text: str) -> None:
        Message(self.console).warning(text)

    def error(self, exc: PortabaseError, *, unexpected: bool = False) -> None:
        Message(self.console).error(exc, verbose=self.verbose, unexpected=unexpected)

    def hint(self, text: str | None = None) -> None:
        Hint(self.console)(text)

    def section(self, title: str) -> None:
        Section(self.console)(title)

    def status(self, text: str):
        return Status(self.console)(text)

    def progress(self) -> Progress:
        return Progress(self.console)

    def summary(self, rows: list[tuple[str, str]], *, title: str | None = None) -> None:
        Summary(self.console)(rows, title=title)

    def table(
        self, columns: list[str], rows: list[list[str]], *, title: str | None = None
    ) -> None:
        DataTable(self.console)(columns, rows, title=title)

    def diff(self, text: str) -> None:
        Diff(self.console)(text)

    def form(self) -> Form:
        style = QUESTIONARY_STYLE_PLAIN if self.no_color else QUESTIONARY_STYLE
        return Form(Prompt(self.console, style), self.non_interactive)

    def confirm(
        self, question: str, *, default: bool = False, value: bool | None = None
    ) -> bool:
        return self.form().confirm(question, value=value, default=default)
