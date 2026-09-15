from __future__ import annotations

from commands.base import Command
from core.errors import NetworkError, UpdateError
from core.version import UNKNOWN, parse_version
from services.telemetry import Telemetry
from services.updater import Release, UpdateChecker, Updater, is_frozen
from ui import UI


class UpdateCommand(Command):
    name, help, panel = "update", "Update the CLI to the latest version.", "System"

    def __init__(
        self, ui: UI, telemetry: Telemetry, checker: UpdateChecker, updater: Updater
    ) -> None:
        super().__init__(ui, telemetry)
        self.checker = checker
        self.updater = updater

    def run(self) -> None:
        if not is_frozen():
            self.ui.warning(
                "The update command is only available for the binary version "
                "of Portabase CLI."
            )
            self.ui.info(
                "If you installed from source, use [bold]git pull[/bold] to update."
            )
            return

        current = self.checker.current
        release = self._latest()
        if release.tag == current:
            self.ui.success(f"Portabase CLI is already up to date ({current}).")
            return
        if current != UNKNOWN and parse_version(release.tag) < parse_version(current):
            self.ui.warning(
                f"Current version ({current}) is newer than the latest remote "
                f"version ({release.tag})."
            )
            self.confirm_or_abort("Continue with the downgrade?", default=False)

        target = self.updater.target_path()
        self.ui.info(f"Updating Portabase CLI from {current} to {release.tag}")
        self.ui.info(f"Target installation path: {target}")

        total = self.updater.expected_size(release) or 0
        with self.ui.progress().download(
            f"Downloading {release.tag}...", total
        ) as advance:
            tmp = self.updater.download(release, advance)
        self.updater.install(tmp, target)
        self.ui.success(f"Successfully updated to {release.tag}!")

    def _latest(self) -> Release:
        try:
            release = self.checker.fetch_latest()
        except NetworkError as error:
            raise UpdateError(
                "Could not fetch latest release data from GitHub.", cause=error
            ) from error
        if release is None:
            raise UpdateError("No release found for this channel.")
        return release
