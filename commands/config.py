from __future__ import annotations

from typing import Annotated

import typer

from commands.base import Command, CommandGroup
from core.config import GlobalConfig
from core.errors import ValidationError
from services.telemetry import Telemetry
from ui import UI

CHANNELS = ("stable", "beta")


class _ConfigCommand(Command):
    panel = "Configuration"

    def __init__(self, ui: UI, telemetry: Telemetry, config: GlobalConfig) -> None:
        super().__init__(ui, telemetry)
        self.config = config


class ConfigShow(_ConfigCommand):
    name, help = "show", "Show the current configuration."

    def run(self) -> None:
        data = self.config.all()
        self.ui.info(f"Configuration file: {self.config.path}")
        for key in GlobalConfig.KNOWN_KEYS:
            value = data.get(key, "[hint]unset[/hint]")
            self.ui.print(f"  [key]{key}[/key]: {value}")
        for key in sorted(set(data) - set(GlobalConfig.KNOWN_KEYS)):
            self.ui.print(
                f"  [key]{key}[/key]: {data[key]}  [hint](unknown key)[/hint]"
            )


class ConfigGet(_ConfigCommand):
    name, help = "get", "Print one configuration value."
    no_args_is_help = True

    def run(
        self, key: Annotated[str, typer.Argument(help="Configuration key")]
    ) -> None:
        value = self.config.get(key)
        if value is None:
            raise ValidationError(
                f"'{key}' is not set.",
                hint="Known keys: " + ", ".join(GlobalConfig.KNOWN_KEYS),
            )
        self.ui.print(str(value))


class ConfigSet(_ConfigCommand):
    name, help = "set", "Set a configuration value."
    no_args_is_help = True

    def run(
        self,
        key: Annotated[str, typer.Argument(help="Configuration key")],
        value: Annotated[str, typer.Argument(help="Value")],
    ) -> None:
        if key == "update_channel" and value not in CHANNELS:
            raise ValidationError(
                f"Invalid channel '{value}'.", hint="Choose 'stable' or 'beta'."
            )
        self.config.set(key, value)
        self.ui.success(f"{key} = {value}")


class ConfigChannel(_ConfigCommand):
    name, help = "channel", "Set the update channel (stable or beta)."
    no_args_is_help = True

    def run(self, name: Annotated[str, typer.Argument(help="stable or beta")]) -> None:
        ConfigSet(self.ui, self.telemetry, self.config).run(
            "update_channel", name.lower()
        )


class ConfigCommands(CommandGroup):
    name, help, panel = "config", "Manage global CLI configuration.", "Configuration"

    def __init__(self, ui: UI, telemetry: Telemetry, config: GlobalConfig) -> None:
        super().__init__(ui, telemetry)
        self.config = config

    @property
    def commands(self) -> list[Command]:
        deps = (self.ui, self.telemetry, self.config)
        return [
            ConfigShow(*deps),
            ConfigGet(*deps),
            ConfigSet(*deps),
            ConfigChannel(*deps),
        ]
