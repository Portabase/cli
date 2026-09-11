from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from core.errors import UserAbort, ValidationError
from core.fields import Field
from ui.components.prompt import Prompt

_TRUE = {"1", "true", "yes", "y", "on"}
_FALSE = {"0", "false", "no", "n", "off"}


class Form:
    def __init__(self, prompt: Prompt, non_interactive: bool) -> None:
        self.prompt = prompt
        self.non_interactive = non_interactive
        self._askers: dict[str, Callable[[Field], Any]] = {
            "text": lambda f: self.prompt.text(f.prompt, default=f.default),
            "int": lambda f: self.prompt.integer(f.prompt, default=f.default),
            "secret": lambda f: self.prompt.secret(f.prompt),
            "bool": lambda f: self.prompt.confirm(f.prompt, default=bool(f.default)),
            "choice": lambda f: self.prompt.select(
                f.prompt, f.choices, default=f.default
            ),
            "path": lambda f: self.prompt.path(f.prompt, default=f.default),
        }

    def ask(self, field: Field, value: Any | None = None) -> Any:
        if value is not None:
            return self._coerce_and_validate(field, value)
        if self.non_interactive:
            if field.default is not None:
                return self._coerce_and_validate(field, field.default)
            raise ValidationError(
                f"Missing {field.flag}",
                hint=f"Required in non-interactive mode: {field.prompt}",
            )
        return self._ask_until_valid(field)

    def collect(
        self, fields: Sequence[Field], values: dict[str, Any]
    ) -> dict[str, Any]:
        return {f.name: self.ask(f, values.get(f.name)) for f in fields}

    def text(
        self, prompt: str, *, value=None, default=None, validator=None, name="value"
    ) -> str:
        field = Field(name, prompt, "text", default=default, validator=validator)
        return self.ask(field, value)

    def integer(
        self, prompt: str, *, value=None, default=None, validator=None, name="value"
    ) -> int:
        field = Field(name, prompt, "int", default=default, validator=validator)
        return self.ask(field, value)

    def secret(self, prompt: str, *, value=None, validator=None, name="value") -> str:
        return self.ask(Field(name, prompt, "secret", validator=validator), value)

    def confirm(
        self, prompt: str, *, value=None, default: bool = False, name="value"
    ) -> bool:
        return self.ask(Field(name, prompt, "bool", default=default), value)

    def choice(
        self,
        prompt: str,
        choices: Sequence[str],
        *,
        value=None,
        default=None,
        name="value",
    ) -> str:
        field = Field(name, prompt, "choice", default=default, choices=tuple(choices))
        return self.ask(field, value)

    def _ask_until_valid(self, field: Field) -> Any:
        if field.help:
            self.prompt.console.print(f"[info]ℹ {field.help}[/info]")
        while True:
            answer = self._askers[field.kind](field)
            if answer is None:
                raise UserAbort()
            try:
                return self._coerce_and_validate(field, answer)
            except ValidationError as e:
                self.prompt.console.print(f"[danger]✖ {e.message}[/danger]")

    def _coerce_and_validate(self, field: Field, value: Any) -> Any:
        value = self._coerce(field, value)
        if field.kind == "choice" and value not in field.choices:
            raise ValidationError(
                f"Invalid value for {field.flag}: {value!r}",
                hint="Choices: " + ", ".join(field.choices),
            )
        if field.validator is not None:
            value = field.validator(value)
        return value

    @staticmethod
    def _coerce(field: Field, value: Any) -> Any:
        if field.kind == "int" and not isinstance(value, int):
            try:
                return int(str(value).strip())
            except ValueError as e:
                raise ValidationError(
                    f"{field.flag} must be a whole number, got {value!r}"
                ) from e
        if field.kind == "bool" and not isinstance(value, bool):
            s = str(value).strip().lower()
            if s in _TRUE:
                return True
            if s in _FALSE:
                return False
            raise ValidationError(f"{field.flag} must be true or false, got {value!r}")
        if field.kind in ("text", "secret", "path", "choice"):
            return str(value)
        return value
