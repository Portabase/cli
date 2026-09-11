from __future__ import annotations

import random

from ui.components.base import Component

HINTS = [
    "The Edge Key contains the connection details for dashboard and agent communication.",
    "Portabase uses Docker Compose to isolate your databases.",
    "List every configured database with 'portabase db list <name>'.",
    "Running 'portabase stop' will gracefully shut down your containers.",
    "The agent polls GitHub for configuration updates.",
    "Logs can be viewed in real time with 'portabase logs <name>'.",
    "Custom environment variables can be added to the generated .env file.",
    "Need to update? Use 'portabase update' to get the latest version.",
    "You can add several databases to a single agent during setup.",
    "Portabase Dashboard provides a web interface to manage your infrastructure.",
    "Docker not running? The CLI offers to start it for you.",
    "All configurations are stored locally in the component's folder.",
    "The 'portabase restart' command is useful after manual .env modifications.",
    "Portabase is open source. Visit our GitHub to contribute.",
    "Use the --start flag with 'agent' or 'dashboard' to skip the final prompt.",
    "Internal databases are automatically backed up when using volumes.",
    "The dashboard requires a PostgreSQL database to store its own data.",
    "Switch the update channel to 'beta' with 'portabase config set update_channel beta'.",
    "The Portabase network keeps communication between your containers private.",
    "Lost your Edge Key? You can find it in the dashboard.",
    "The 'portabase uninstall' command safely removes containers and their data.",
    "Use 'portabase --version' to check your current installation details.",
    "The 'databases.json' file keeps track of all managed database instances.",
]


class Hint(Component):
    def random(self) -> str:
        return f"[hint]{random.choice(HINTS)}[/hint]"

    def __call__(self, text: str | None = None) -> None:
        self.console.print(f"[hint]{text}[/hint]" if text else self.random())
