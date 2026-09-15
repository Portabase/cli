# Plan 2 — Fondations et lifecycle (chantiers B + C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poser les fondations POO (erreurs, `ui/`, services d'infrastructure, `Command`, catcher, télémétrie no-op, updater sans auto-update) et réécrire les commandes de lifecycle/config/update dessus, tout en gardant `agent`, `dashboard` et `db` sur l'ancien code via un adaptateur — le CLI reste shippable en stable à la fin.

**Architecture:** `main.py` construit les dépendances (`UI`, `Telemetry`, `GlobalConfig`, `HttpClient`, `DockerRunner`) et les injecte dans des classes `Command` enregistrées sur Typer. Un seul `try` dans `main()` traduit `PortabaseError` en message + code de sortie. Les commandes legacy sont enregistrées telles quelles par `LegacyCommand` ; elles continuent d'importer `core.utils.console` jusqu'au Plan 4.

**Tech Stack:** Python 3.12, Typer 0.25 / Click 8.4, Rich 15, questionary 2.1, requests.

**Spec:** `docs/superpowers/specs/2026-09-11-cli-refactor-design.md` — sections 3, 4.1, 7, 8, 10 (B, C).

## Global Constraints

- Prérequis : Plan 1 exécuté (ruff configuré, CI en place).
- Règle de dépendance descendante : `commands → services, engines, ui, core` ; `services → engines, core` (jamais `ui`) ; `ui → core` ; `core → rien`. Vérifiée par ruff `TID251` (Task 12).
- `rich.prompt`, `typer.prompt`, `typer.confirm`, `print` interdits hors `ui/` (ruff `TID251`, activé Task 12 avec exceptions legacy).
- `typer.Exit` n'est levé nulle part hors des fichiers legacy ; le nouveau code lève `PortabaseError`.
- Pas de tests unitaires (consigne). Chaque tâche a des vérifications exécutables ; les commandes Docker sont vérifiées avec un dossier agent réel si Docker est disponible, sinon sur leurs chemins d'erreur.
- Ne pas toucher `commands/agent.py`, `commands/db.py`, `commands/dashboard.py`, `core/network.py`, `core/docker.py`, `templates/compose.py` (supprimés au Plan 4). `core/utils.py` : seulement retirer `current_version` (Task 2).
- Déviation spec assumée : `Field` vit dans `core/fields.py` (partagé par `ui.Form` et `engines`), pas dans `engines/base.py`.
- Nom de la clé de config existante conservé : `update_channel` (valeurs `stable` / `beta`).
- Commits Conventional Commits, un par tâche minimum.

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `core/errors.py` | créer | hiérarchie `PortabaseError` |
| `core/version.py` | créer | `current_version()`, `parse_version()`, `is_prerelease()` |
| `core/utils.py` | modifier | retirer `current_version` (re-export pour legacy) |
| `core/config.py` | modifier | ajouter classe `GlobalConfig` ; fonctions legacy conservées |
| `core/fields.py` | créer | `Field` |
| `ui/theme.py` | créer | `PALETTE`, `RICH_THEME`, `QUESTIONARY_STYLE` |
| `ui/components/base.py` | créer | `Component` |
| `ui/components/hints.py` | créer | `HINTS`, `Hint` |
| `ui/components/message.py` | créer | `Message` |
| `ui/components/banner.py` | créer | `Banner` |
| `ui/components/section.py` | créer | `Section` |
| `ui/components/status.py` | créer | `Status` |
| `ui/components/progress.py` | créer | `Progress` (téléchargement) |
| `ui/components/prompt.py` | créer | `Prompt` (questionary) |
| `ui/form.py` | créer | `Form` |
| `ui/__init__.py` | créer | façade `UI` |
| `services/http.py` | créer | `HttpClient` |
| `services/docker.py` | créer | `DockerRunner` |
| `services/telemetry.py` | créer | `Telemetry`, `NoopTelemetry`, `ConsoleTelemetry`, `TelemetryHub`, `TelemetryFactory` |
| `services/updater.py` | créer | `Release`, `UpdateChecker`, `Updater` |
| `commands/base.py` | créer | `Command`, `CommandGroup`, `LegacyCommand` |
| `commands/lifecycle.py` | créer | `Start/Stop/Restart/Logs/Uninstall` |
| `commands/config.py` | réécrire | `ConfigCommands` |
| `commands/update.py` | créer | `UpdateCommand` |
| `main.py` | réécrire | `Settings`, `build_app`, `main` |
| `commands/common.py`, `core/updater.py` | supprimer | — |
| `pyproject.toml` | modifier | `TID251`, per-file-ignores mis à jour |

---

### Task 1 : `core/errors.py`

**Files:**
- Create: `core/errors.py`

**Interfaces:**
- Produces: `PortabaseError(message, *, hint=None, cause=None)` avec attributs `message`, `hint`, `cause`, classe-attributs `code: str`, `exit_code: int` ; sous-classes `UserAbort`, `ValidationError`, `ConfigError`, `DockerError`, `TemplateError`, `NetworkError`, `UpdateError`.

- [ ] **Step 1: Écrire le module**

```python
"""Exception hierarchy. Every error the CLI reports to a user is one of these."""

from __future__ import annotations


class PortabaseError(Exception):
    code: str = "E_GENERIC"
    exit_code: int = 1

    def __init__(
        self,
        message: str,
        *,
        hint: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause

    def __str__(self) -> str:
        return self.message


class UserAbort(PortabaseError):
    code = "E_ABORT"
    exit_code = 130

    def __init__(self, message: str = "Cancelled.", **kwargs) -> None:
        super().__init__(message, **kwargs)


class ValidationError(PortabaseError):
    code = "E_VALIDATION"
    exit_code = 2


class ConfigError(PortabaseError):
    code = "E_CONFIG"
    exit_code = 3


class DockerError(PortabaseError):
    code = "E_DOCKER"
    exit_code = 4


class TemplateError(PortabaseError):
    code = "E_TEMPLATE"
    exit_code = 5


class NetworkError(PortabaseError):
    code = "E_NETWORK"
    exit_code = 6


class UpdateError(PortabaseError):
    code = "E_UPDATE"
    exit_code = 7
```

- [ ] **Step 2: Vérifier**

Run: `uv run python -c "from core.errors import *; e = DockerError('daemon down', hint='start it'); print(e.code, e.exit_code, e, e.hint); assert isinstance(e, PortabaseError)"`
Expected: `E_DOCKER 4 daemon down start it`.

- [ ] **Step 3: Commit**

```bash
git add core/errors.py
git commit -m "feat(core): add PortabaseError hierarchy with stable codes and exit codes"
```

---

### Task 2 : `core/version.py` et `core/fields.py`

**Files:**
- Create: `core/version.py`
- Create: `core/fields.py`
- Modify: `core/utils.py:197-214` (fonction `current_version`)

**Interfaces:**
- Produces: `current_version() -> str` ; `parse_version(v: str) -> tuple` ; `is_prerelease(v: str) -> bool` ; `Field` dataclass.

- [ ] **Step 1: Écrire `core/version.py`**

```python
"""CLI version helpers. Version is read from the bundled pyproject.toml."""

from __future__ import annotations

import re
import sys
import tomllib
from functools import lru_cache
from pathlib import Path

UNKNOWN = "unknown"
_PRE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:[-.]?(rc|alpha|beta|a|b)(\d*))?$", re.I)


@lru_cache(maxsize=1)
def current_version() -> str:
    try:
        base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent.parent
        with open(base / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError, AttributeError):
        return UNKNOWN


def is_prerelease(version: str) -> bool:
    m = _PRE.match(version.strip().lstrip("v"))
    return bool(m and m.group(4))


def parse_version(version: str) -> tuple[int, int, int, int, int]:
    """Sortable tuple. Pre-releases sort before the final release of the same number.

    (major, minor, patch, pre_rank, pre_number) — pre_rank: 0 alpha/a, 1 beta/b, 2 rc, 3 final.
    """
    m = _PRE.match(version.strip().lstrip("v"))
    if not m:
        return (0, 0, 0, 0, 0)
    major, minor, patch = (int(m.group(i)) for i in (1, 2, 3))
    tag = (m.group(4) or "").lower()
    rank = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2, "": 3}[tag]
    num = int(m.group(5)) if m.group(5) else 0
    return (major, minor, patch, rank, num)
```

- [ ] **Step 2: Écrire `core/fields.py`**

```python
"""Declarative input field. Used by ui.Form to prompt or validate a value."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

FieldKind = Literal["text", "int", "secret", "bool", "choice", "path"]


@dataclass(frozen=True)
class Field:
    name: str
    prompt: str
    kind: FieldKind = "text"
    default: Any = None
    choices: tuple[str, ...] = ()
    help: str | None = None
    validator: Callable[[Any], Any] | None = None

    @property
    def flag(self) -> str:
        return "--" + self.name.replace("_", "-")
```

- [ ] **Step 3: Retirer `current_version` de `core/utils.py`**

Supprimer la fonction `current_version` (lignes ~197–214) et ajouter en tête des imports :

```python
from core.version import current_version  # noqa: F401 — re-export for legacy modules
```

`core/network.py` et `core/updater.py` importent `current_version` depuis `core.utils` ; le re-export les garde fonctionnels jusqu'à leur suppression.

- [ ] **Step 4: Vérifier**

Run: `uv run python -c "from core.version import *; print(current_version(), is_prerelease('26.09.0rc1'), parse_version('26.09.0rc1') < parse_version('26.09.0'), parse_version('26.10.0') > parse_version('26.9.9'))" && uv run python main.py --version`
Expected: `26.07.6 True True True` puis `Portabase CLI version: 26.07.6`.

- [ ] **Step 5: Commit**

```bash
git add core/version.py core/fields.py core/utils.py
git commit -m "feat(core): add version helpers and Field descriptor"
```

---

### Task 3 : `GlobalConfig`

**Files:**
- Modify: `core/config.py`

**Interfaces:**
- Produces: `GlobalConfig(path: Path = GLOBAL_CONFIG_FILE)` avec `get(key, default=None)`, `set(key, value)`, `all() -> dict`, `cache_dir: Path` (`~/.portabase/cache`) ; propriétés typées `update_channel: str | None`, `telemetry: bool`, `telemetry_endpoint: str | None`.
- Les fonctions module-level existantes restent (legacy).

- [ ] **Step 1: Ajouter la classe en fin de `core/config.py`**

```python
class GlobalConfig:
    """~/.portabase/config.json. Unknown keys are preserved."""

    KNOWN_KEYS = ("update_channel", "telemetry", "telemetry_endpoint")

    def __init__(self, path: Path = GLOBAL_CONFIG_FILE) -> None:
        self.path = path
        self.cache_dir = path.parent / "cache"

    def all(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, key: str, default=None):
        return self.all().get(key, default)

    def set(self, key: str, value) -> None:
        data = self.all()
        data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, self.path)

    @property
    def update_channel(self) -> str | None:
        return self.get("update_channel")

    @property
    def telemetry(self) -> bool:
        return str(self.get("telemetry", "false")).lower() in ("1", "true", "yes")

    @property
    def telemetry_endpoint(self) -> str | None:
        return self.get("telemetry_endpoint")
```

Ajouter au-dessus des fonctions legacy le commentaire :

```python
# --- Legacy helpers below: used by commands/agent.py, db.py, dashboard.py, core/updater.py.
# --- Removed in plan 4. New code uses GlobalConfig.
```

- [ ] **Step 2: Vérifier**

Run: `uv run python -c "
from pathlib import Path; import tempfile
from core.config import GlobalConfig
c = GlobalConfig(Path(tempfile.mkdtemp())/'config.json')
print(c.all(), c.telemetry); c.set('update_channel','beta'); c.set('telemetry', True)
print(c.update_channel, c.telemetry, c.all())"`
Expected: `{} False` puis `beta True {'update_channel': 'beta', 'telemetry': True}`.

- [ ] **Step 3: Commit**

```bash
git add core/config.py
git commit -m "feat(core): add GlobalConfig class over ~/.portabase/config.json"
```

---

### Task 4 : `ui/theme.py` et composants d'affichage

**Files:**
- Create: `ui/__init__.py` (vide pour l'instant, rempli Task 6)
- Create: `ui/theme.py`
- Create: `ui/components/__init__.py` (vide)
- Create: `ui/components/base.py`
- Create: `ui/components/hints.py`
- Create: `ui/components/message.py`
- Create: `ui/components/banner.py`
- Create: `ui/components/section.py`
- Create: `ui/components/status.py`
- Create: `ui/components/progress.py`

**Interfaces:**
- Produces: `Component(console)` ; `Hint(console).random() -> str` ; `Message(console).success/info/warning(text)`, `.error(exc: PortabaseError, *, verbose: bool, unexpected: bool)` ; `Banner(console)()` ; `Section(console)(title)` ; `Status(console)(text) -> ContextManager` ; `Progress(console).download(description, total) -> ContextManager[Callable[[int], None]]`.

- [ ] **Step 1: `ui/theme.py`**

```python
"""Single source of visual tokens. Rich theme and questionary style derive from PALETTE."""

from __future__ import annotations

from questionary import Style
from rich.theme import Theme

PALETTE = {
    "brand": "#ff6600",
    "accent": "#5f00d7",
    "info": "cyan",
    "warning": "magenta",
    "danger": "red",
    "success": "green",
    "muted": "grey50",
}

RICH_THEME = Theme(
    {
        "info": f"dim {PALETTE['info']}",
        "warning": PALETTE["warning"],
        "danger": f"bold {PALETTE['danger']}",
        "success": f"bold {PALETTE['success']}",
        "title": f"bold white on {PALETTE['accent']}",
        "key": f"bold {PALETTE['brand']}",
        "value": "white",
        "hint": f"italic {PALETTE['muted']}",
        "brand": f"bold {PALETTE['brand']}",
    }
)

QUESTIONARY_STYLE = Style(
    [
        ("qmark", f"fg:{PALETTE['brand']} bold"),
        ("question", "bold"),
        ("pointer", f"fg:{PALETTE['brand']} bold"),
        ("highlighted", f"fg:black bg:{PALETTE['brand']} bold"),
        ("selected", f"fg:{PALETTE['brand']} bold"),
        ("answer", f"fg:{PALETTE['brand']}"),
    ]
)

QUESTIONARY_STYLE_PLAIN = Style([])
```

- [ ] **Step 2: `ui/components/base.py`**

```python
from __future__ import annotations

from rich.console import Console


class Component:
    """Stateless renderable bound to a console. Instantiate per call."""

    def __init__(self, console: Console) -> None:
        self.console = console
```

- [ ] **Step 3: `ui/components/hints.py`**

Reprendre la liste `HINTS` de `core/utils.py:42-66` telle quelle.

```python
from __future__ import annotations

import random

from ui.components.base import Component

HINTS = [
    "The Edge Key contains the connection details for dashboard and agent communication.",
    "Portabase uses Docker Compose to isolate your databases.",
    "You can list all configured databases using 'portabase db list <name>'.",
    "Running 'portabase stop' will gracefully shut down your containers.",
    "The agent polls the github for configuration updates.",
    "Logs can be viewed in real-time with 'portabase logs <name>'.",
    "Custom environment variables can be added to the generated .env file.",
    "Need to update? Use 'portabase update' to get the latest version.",
    "You can add multiple databases to a single agent during setup.",
    "Portabase Dashboard provides a web interface to manage your infrastructure.",
    "Is Docker not running? The CLI will offer to start it for you!",
    "All configurations are stored locally in the component's folder.",
    "The 'portabase restart' command is useful after manual .env modifications.",
    "Portabase is open-source! Check our GitHub to contribute.",
    "Using the --start flag with 'agent' or 'dashboard' skips the final prompt.",
    "Internal databases are automatically backed up when using volumes.",
    "The dashboard requires a PostgreSQL database to store its own data.",
    "You can change the update channel to 'beta' in the config for early features.",
    "Portabase network ensures secure communication between your containers.",
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
```

- [ ] **Step 4: `ui/components/message.py`**

```python
from __future__ import annotations

import traceback

from core.errors import PortabaseError
from ui.components.base import Component


class Message(Component):
    def success(self, text: str) -> None:
        self.console.print(f"[success]✔ {text}[/success]")

    def info(self, text: str) -> None:
        self.console.print(f"[info]ℹ {text}[/info]")

    def warning(self, text: str) -> None:
        self.console.print(f"[warning]⚠ {text}[/warning]")

    def error(self, exc: PortabaseError, *, verbose: bool = False, unexpected: bool = False) -> None:
        label = "Unexpected error" if unexpected else "Error"
        self.console.print(f"[danger]✖ {label}:[/danger] {exc.message}")
        if exc.hint:
            self.console.print(f"  [hint]↳ {exc.hint}[/hint]")
        if verbose or unexpected:
            self.console.print(f"  [hint]code: {exc.code}[/hint]")
        if verbose and exc.cause is not None:
            self.console.print(f"  [hint]cause: {type(exc.cause).__name__}: {exc.cause}[/hint]")
        if verbose:
            self.console.print("".join(traceback.format_exception(exc)), highlight=False, markup=False)
```

- [ ] **Step 5: `ui/components/banner.py`**

```python
from __future__ import annotations

from rich.align import Align

from ui.components.base import Component
from ui.components.hints import Hint

BANNER = """
[brand]█▀█ █▀█ █▀█ ▀█▀ ▄▀█ █▄▄ ▄▀█ █▀ █▀▀[/brand]
[brand]█▀▀ █▄█ █▀▄  █  █▀█ █▄█ █▀█ ▄█ ██▄[/brand]
[hint]Deploy your infrastructure anywhere.[/hint]
"""


class Banner(Component):
    def __call__(self) -> None:
        self.console.print(Align.center(BANNER))
        self.console.print(Align.center(Hint(self.console).random() + "\n"))
```

- [ ] **Step 6: `ui/components/section.py`**

```python
from __future__ import annotations

from rich.panel import Panel

from ui.components.base import Component


class Section(Component):
    def __call__(self, title: str) -> None:
        self.console.print("")
        self.console.print(Panel(f"[bold]{title}[/bold]", style="cyan", expand=False))
```

- [ ] **Step 7: `ui/components/status.py`**

```python
from __future__ import annotations

from contextlib import AbstractContextManager

from ui.components.base import Component
from ui.components.hints import Hint


class Status(Component):
    def __call__(self, text: str, *, spinner: str = "dots") -> AbstractContextManager:
        message = f"[bold magenta]{text}[/bold magenta]\n{Hint(self.console).random()}"
        return self.console.status(message, spinner=spinner)
```

- [ ] **Step 8: `ui/components/progress.py`**

```python
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress as RichProgress,
    SpinnerColumn,
    TextColumn,
    TransferSpeedColumn,
)

from ui.components.base import Component
from ui.components.hints import Hint


class Progress(Component):
    @contextmanager
    def download(self, description: str, total: int) -> Iterator[Callable[[int], None]]:
        """Yields an advance(n_bytes) callable."""
        with RichProgress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}\n" + Hint(self.console).random()),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(description, total=total or None)
            yield lambda n: progress.update(task, advance=n)
```

- [ ] **Step 9: Vérifier le rendu**

Run: `uv run python -c "
from rich.console import Console
from ui.theme import RICH_THEME
from ui.components.message import Message
from ui.components.banner import Banner
from ui.components.section import Section
from core.errors import DockerError
c = Console(theme=RICH_THEME)
Banner(c)(); Section(c)('Database Setup')
m = Message(c); m.success('ok'); m.info('note'); m.warning('careful')
m.error(DockerError('daemon down', hint='run: sudo systemctl start docker'))
m.error(DockerError('daemon down', hint='x', cause=RuntimeError('boom')), verbose=True)"`
Expected: bannière orange, panneau cyan, quatre messages avec icônes ✔ ℹ ⚠ ✖, hint indenté, puis le bloc verbose avec `code: E_DOCKER`, `cause: RuntimeError: boom` et une traceback.

- [ ] **Step 10: Commit**

```bash
git add ui/
git commit -m "feat(ui): add theme tokens and display components"
```

---

### Task 5 : `ui/components/prompt.py` et `ui/form.py`

**Files:**
- Create: `ui/components/prompt.py`
- Create: `ui/form.py`

**Interfaces:**
- Consumes: `Field` (Task 2), `UserAbort`/`ValidationError` (Task 1), `QUESTIONARY_STYLE` (Task 4).
- Produces: `Prompt(console, style)` avec `text/integer/secret/confirm/select/path` renvoyant `None` sur Ctrl-C ; `Form(prompt, non_interactive)` avec `ask(field, value)`, `collect(fields, values) -> dict`, raccourcis `text/integer/secret/confirm/choice`.

- [ ] **Step 1: `ui/components/prompt.py`**

```python
from __future__ import annotations

from collections.abc import Sequence

import questionary
from questionary import Style
from rich.console import Console

from ui.components.base import Component


class Prompt(Component):
    """Thin wrapper over questionary. Every method returns None when the user aborts (Ctrl-C)."""

    def __init__(self, console: Console, style: Style) -> None:
        super().__init__(console)
        self.style = style

    def text(self, message: str, *, default: str | None = None) -> str | None:
        return questionary.text(message, default=default or "", style=self.style).ask()

    def integer(self, message: str, *, default: int | None = None) -> int | None:
        answer = questionary.text(
            message,
            default="" if default is None else str(default),
            validate=lambda v: v.strip().lstrip("-").isdigit() or "Enter a whole number",
            style=self.style,
        ).ask()
        return None if answer is None else int(answer)

    def secret(self, message: str) -> str | None:
        return questionary.password(message, style=self.style).ask()

    def confirm(self, message: str, *, default: bool = False) -> bool | None:
        return questionary.confirm(message, default=default, style=self.style).ask()

    def select(self, message: str, choices: Sequence[str], *, default: str | None = None) -> str | None:
        return questionary.select(message, choices=list(choices), default=default, style=self.style).ask()

    def path(self, message: str, *, default: str | None = None) -> str | None:
        return questionary.path(message, default=default or "", style=self.style).ask()
```

- [ ] **Step 2: `ui/form.py`**

```python
"""Flag → prompt → default → error. The only place that knows about non-interactive mode."""

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
            "choice": lambda f: self.prompt.select(f.prompt, f.choices, default=f.default),
            "path": lambda f: self.prompt.path(f.prompt, default=f.default),
        }

    # ---- core -------------------------------------------------------------

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

    def collect(self, fields: Sequence[Field], values: dict[str, Any]) -> dict[str, Any]:
        return {f.name: self.ask(f, values.get(f.name)) for f in fields}

    # ---- shortcuts --------------------------------------------------------

    def text(self, prompt: str, *, value=None, default=None, validator=None, name="value") -> str:
        return self.ask(Field(name, prompt, "text", default=default, validator=validator), value)

    def integer(self, prompt: str, *, value=None, default=None, validator=None, name="value") -> int:
        return self.ask(Field(name, prompt, "int", default=default, validator=validator), value)

    def secret(self, prompt: str, *, value=None, validator=None, name="value") -> str:
        return self.ask(Field(name, prompt, "secret", validator=validator), value)

    def confirm(self, prompt: str, *, value=None, default: bool = False, name="value") -> bool:
        return self.ask(Field(name, prompt, "bool", default=default), value)

    def choice(self, prompt: str, choices: Sequence[str], *, value=None, default=None, name="value") -> str:
        return self.ask(Field(name, prompt, "choice", default=default, choices=tuple(choices)), value)

    # ---- internals --------------------------------------------------------

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
            value = field.validator(value)  # raises ValidationError
        return value

    @staticmethod
    def _coerce(field: Field, value: Any) -> Any:
        if field.kind == "int" and not isinstance(value, int):
            try:
                return int(str(value).strip())
            except ValueError as e:
                raise ValidationError(f"{field.flag} must be a whole number, got {value!r}") from e
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
```

- [ ] **Step 3: Vérifier le mode non-interactif (sans terminal)**

Run: `uv run python -c "
from rich.console import Console
from ui.theme import QUESTIONARY_STYLE
from ui.components.prompt import Prompt
from ui.form import Form
from core.fields import Field
from core.errors import ValidationError
f = Form(Prompt(Console(), QUESTIONARY_STYLE), non_interactive=True)
print(f.text('Timezone', value=None, default='UTC'), f.integer('Polling', value='7'), f.confirm('Gateway?', value='yes'))
print(f.collect([Field('engine','Engine','choice',choices=('a','b')), Field('port','Port','int',default=5432)], {'engine':'a'}))
try: f.text('Edge key')
except ValidationError as e: print('OK:', e.message, '|', e.hint)
try: f.choice('Mode', ['new','existing'], value='bogus')
except ValidationError as e: print('OK:', e.message, '|', e.hint)"`
Expected :
```
UTC 7 True
{'engine': 'a', 'port': 5432}
OK: Missing --value | Required in non-interactive mode: Edge key
OK: Invalid value for --value: 'bogus' | Choices: new, existing
```

- [ ] **Step 4: Vérifier le mode interactif (terminal requis)**

Run: `uv run python -c "
from rich.console import Console
from ui.theme import QUESTIONARY_STYLE
from ui.components.prompt import Prompt
from ui.form import Form
f = Form(Prompt(Console(), QUESTIONARY_STYLE), non_interactive=False)
print(f.choice('Mode', ['new','existing'], default='new'))
print(f.integer('Port', default=5432))"`
Répondre aux deux prompts. Puis relancer et faire Ctrl-C au premier prompt.
Expected: valeurs saisies affichées ; sur Ctrl-C, traceback se terminant par `core.errors.UserAbort: Cancelled.` (le catcher n'est pas encore branché — attendu).

- [ ] **Step 5: Commit**

```bash
git add ui/components/prompt.py ui/form.py
git commit -m "feat(ui): add questionary Prompt and Form with non-interactive resolution"
```

---

### Task 6 : Façade `UI`

**Files:**
- Modify: `ui/__init__.py`

**Interfaces:**
- Produces: `UI(console=None, *, non_interactive=False, verbose=False, no_color=False)` ; `configure(**kwargs)` ; `banner()`, `success/info/warning(text)`, `error(exc, unexpected=False)`, `hint(text=None)`, `section(title)`, `status(text)`, `progress()`, `confirm(q, default=False, value=None) -> bool`, `form() -> Form`, `print(renderable)`. Attribut `console`.

- [ ] **Step 1: Écrire la façade**

```python
"""Facade: the only thing `commands/` imports from ui. Rich and questionary stay inside ui/."""

from __future__ import annotations

from rich.console import Console

from core.errors import PortabaseError
from ui.components.banner import Banner
from ui.components.hints import Hint
from ui.components.message import Message
from ui.components.progress import Progress
from ui.components.prompt import Prompt
from ui.components.section import Section
from ui.components.status import Status
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

    def configure(self, *, non_interactive: bool | None = None, verbose: bool | None = None, no_color: bool | None = None) -> None:
        if non_interactive is not None:
            self.non_interactive = non_interactive
        if verbose is not None:
            self.verbose = verbose
        if no_color is not None and no_color != self.no_color:
            self.no_color = no_color
            self.console = self._make_console()

    def _make_console(self) -> Console:
        return Console(theme=RICH_THEME, no_color=self.no_color)

    # ---- output -----------------------------------------------------------

    def print(self, renderable) -> None:
        self.console.print(renderable)

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

    # ---- input ------------------------------------------------------------

    def form(self) -> Form:
        style = QUESTIONARY_STYLE_PLAIN if self.no_color else QUESTIONARY_STYLE
        return Form(Prompt(self.console, style), self.non_interactive)

    def confirm(self, question: str, *, default: bool = False, value: bool | None = None) -> bool:
        return self.form().confirm(question, value=value, default=default)
```

- [ ] **Step 2: Vérifier**

Run: `uv run python -c "
from ui import UI
ui = UI(non_interactive=True)
ui.banner(); ui.section('Test'); ui.success('a'); ui.warning('b'); ui.hint()
print('confirm default:', ui.confirm('Really?', default=False))
with ui.status('Working...'): import time; time.sleep(0.5)
ui.configure(no_color=True); ui.success('no color')"`
Expected: rendu, `confirm default: False` sans prompt, spinner 0,5 s, dernière ligne sans couleur.

- [ ] **Step 3: Commit**

```bash
git add ui/__init__.py
git commit -m "feat(ui): add UI facade"
```

---

### Task 7 : `services/http.py` et `services/docker.py`

**Files:**
- Create: `services/__init__.py` (vide)
- Create: `services/http.py`
- Create: `services/docker.py`

**Interfaces:**
- Produces:
  - `HttpClient(timeout=10.0)` : `get_json(url) -> Any`, `get_text(url) -> str`, `download(url, dest: Path, on_progress: Callable[[int], None] | None = None, *, timeout=30.0) -> int` (octets), `head_content_length(url) -> int | None`. Lèvent `NetworkError`.
  - `DockerRunner(docker_bin: str | None = None)` : `available() -> bool`, `daemon_running() -> bool`, `start_daemon() -> bool`, `ensure_network(name)`, `compose(cwd, args, *, check=True, capture=False) -> subprocess.CompletedProcess`, `project_name(cwd) -> str`. Lèvent `DockerError`.

- [ ] **Step 1: `services/http.py`**

```python
"""requests wrapper. Every failure becomes NetworkError; nothing else leaks out."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests

from core.errors import NetworkError

_HINT = "Check your internet connection or proxy settings."


class HttpClient:
    def __init__(self, timeout: float = 10.0, user_agent: str = "portabase-cli") -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent

    def get_json(self, url: str) -> Any:
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            raise NetworkError(f"GET {url} failed: {e}", hint=_HINT, cause=e) from e
        except ValueError as e:
            raise NetworkError(f"GET {url}: response is not JSON", cause=e) from e

    def get_text(self, url: str) -> str:
        try:
            r = self.session.get(url, timeout=self.timeout)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            raise NetworkError(f"GET {url} failed: {e}", hint=_HINT, cause=e) from e

    def status(self, url: str) -> int:
        """HTTP status without raising on 4xx/5xx. Network failure still raises."""
        try:
            return self.session.get(url, timeout=self.timeout, stream=True).status_code
        except requests.RequestException as e:
            raise NetworkError(f"GET {url} failed: {e}", hint=_HINT, cause=e) from e

    def download(
        self,
        url: str,
        dest: Path,
        on_progress: Callable[[int], None] | None = None,
        *,
        timeout: float = 30.0,
    ) -> int:
        written = 0
        try:
            with self.session.get(url, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        written += len(chunk)
                        if on_progress:
                            on_progress(len(chunk))
        except requests.RequestException as e:
            dest.unlink(missing_ok=True)
            raise NetworkError(f"Download of {url} failed: {e}", hint=_HINT, cause=e) from e
        return written

    def content_length(self, url: str) -> int | None:
        try:
            r = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            value = r.headers.get("content-length")
            return int(value) if value else None
        except (requests.RequestException, ValueError):
            return None
```

- [ ] **Step 2: `services/docker.py`**

Reprend `core/docker.py` + `check_system`/`start_docker` de `core/utils.py`, sans aucune sortie terminal.

```python
"""Docker CLI runner. No terminal output; callers decide what to show."""

from __future__ import annotations

import platform
import shutil
import subprocess
import time
from pathlib import Path

from core.errors import DockerError
from core.utils import slugify_project_name

_START_COMMANDS = {
    "Linux": ["sudo", "systemctl", "start", "docker"],
    "Darwin": ["open", "--background", "-a", "Docker"],
    "Windows": ["cmd", "/c", "start", "docker"],
}


class DockerRunner:
    def __init__(self, docker_bin: str | None = None) -> None:
        self._bin = docker_bin

    @property
    def binary(self) -> str:
        if self._bin is None:
            found = shutil.which("docker")
            if found is None:
                raise DockerError(
                    "Docker not found (binary missing).",
                    hint="Install Docker: https://docs.docker.com/get-docker/",
                )
            self._bin = found
        return self._bin

    def available(self) -> bool:
        return shutil.which("docker") is not None

    def daemon_running(self) -> bool:
        try:
            subprocess.run(
                [self.binary, "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
            )
            return True
        except (subprocess.CalledProcessError, OSError):
            return False

    def start_daemon(self, *, wait_seconds: int = 20) -> bool:
        cmd = _START_COMMANDS.get(platform.system())
        if cmd is None:
            return False
        try:
            subprocess.run(cmd, check=True)
        except (subprocess.CalledProcessError, OSError) as e:
            raise DockerError(f"Failed to start Docker: {e}", cause=e) from e
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            if self.daemon_running():
                return True
            time.sleep(2)
        return False

    def ensure_network(self, name: str) -> None:
        inspect = subprocess.run(
            [self.binary, "network", "inspect", name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if inspect.returncode == 0:
            return
        try:
            subprocess.run([self.binary, "network", "create", name], stdout=subprocess.DEVNULL, check=True)
        except subprocess.CalledProcessError as e:
            raise DockerError(f"Could not create Docker network '{name}'.", cause=e) from e

    @staticmethod
    def project_name(cwd: Path) -> str:
        return slugify_project_name(cwd.resolve().name)

    def compose(
        self,
        cwd: Path,
        args: list[str],
        *,
        check: bool = True,
        capture: bool = False,
    ) -> subprocess.CompletedProcess:
        cmd = [self.binary, "compose", "-p", self.project_name(cwd), *args]
        try:
            return subprocess.run(
                cmd,
                cwd=cwd,
                check=check,
                capture_output=capture,
                text=capture,
            )
        except subprocess.CalledProcessError as e:
            raise DockerError(
                f"docker compose {' '.join(args)} failed (exit {e.returncode}).",
                hint=f"Run it manually in {cwd} to see the full output.",
                cause=e,
            ) from e
```

- [ ] **Step 3: Vérifier**

Run: `uv run python -c "
from services.http import HttpClient
from services.docker import DockerRunner
from core.errors import NetworkError, DockerError
h = HttpClient(timeout=5)
print(type(h.get_json('https://api.github.com/repos/Portabase/cli')).__name__)
try: h.get_json('https://127.0.0.1:1/nope')
except NetworkError as e: print('NetworkError OK:', e.code)
d = DockerRunner(); print('docker available:', d.available(), '| daemon:', d.available() and d.daemon_running())
try: DockerRunner(docker_bin='/nonexistent').compose(__import__('pathlib').Path('.'), ['version'])
except (DockerError, OSError) as e: print('error path OK:', type(e).__name__)"`
Expected: `dict`, `NetworkError OK: E_NETWORK`, état Docker local, `error path OK: FileNotFoundError` ou `DockerError` (les deux acceptables ici ; `OSError` est traité au niveau commande, Task 9).

- [ ] **Step 4: Commit**

```bash
git add services/
git commit -m "feat(services): add HttpClient and DockerRunner"
```

---

### Task 8 : `services/telemetry.py`

**Files:**
- Create: `services/telemetry.py`

**Interfaces:**
- Produces: `Telemetry` ABC (`session(**attrs)`, `span(name, **attrs)`, `event(name, **attrs)`, `error(exc, unexpected=False)`, `flush()`) ; `NoopTelemetry` ; `ConsoleTelemetry(stream=sys.stderr)` ; `TelemetryHub(inner)` avec `.set(inner)` ; `TelemetryFactory.build(config: GlobalConfig, *, debug: bool) -> TelemetryHub`.

- [ ] **Step 1: Écrire le module**

```python
"""Telemetry contract. Noop by default; OTel exporter can be plugged later without touching callers.

Never record: agent names, paths, keys, credentials, file contents.
"""

from __future__ import annotations

import sys
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TextIO

from core.config import GlobalConfig


class Telemetry(ABC):
    @abstractmethod
    def session(self, **attrs: Any):
        """Context manager: root span for one CLI invocation."""

    @abstractmethod
    def span(self, name: str, **attrs: Any):
        """Context manager: child span."""

    @abstractmethod
    def event(self, name: str, **attrs: Any) -> None: ...

    @abstractmethod
    def error(self, exc: BaseException, *, unexpected: bool = False) -> None: ...

    def flush(self) -> None:
        return None


class NoopTelemetry(Telemetry):
    @contextmanager
    def session(self, **attrs: Any) -> Iterator[None]:
        yield

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[None]:
        yield

    def event(self, name: str, **attrs: Any) -> None:
        return None

    def error(self, exc: BaseException, *, unexpected: bool = False) -> None:
        return None


class ConsoleTelemetry(Telemetry):
    """--debug: prints spans and events to stderr. Development aid, not an exporter."""

    def __init__(self, stream: TextIO = sys.stderr) -> None:
        self.stream = stream
        self._depth = 0

    def _log(self, line: str) -> None:
        self.stream.write("  " * self._depth + f"[telemetry] {line}\n")
        self.stream.flush()

    @contextmanager
    def session(self, **attrs: Any) -> Iterator[None]:
        with self.span("session", **attrs):
            yield

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[None]:
        self._log(f"▶ {name} {attrs}")
        self._depth += 1
        start = time.perf_counter()
        try:
            yield
        finally:
            self._depth -= 1
            self._log(f"◀ {name} {time.perf_counter() - start:.3f}s")

    def event(self, name: str, **attrs: Any) -> None:
        self._log(f"• {name} {attrs}")

    def error(self, exc: BaseException, *, unexpected: bool = False) -> None:
        code = getattr(exc, "code", type(exc).__name__)
        self._log(f"✖ error code={code} unexpected={unexpected}")


class TelemetryHub(Telemetry):
    """Delegates to a swappable implementation. Commands hold the hub; main swaps the inner."""

    def __init__(self, inner: Telemetry | None = None) -> None:
        self.inner: Telemetry = inner or NoopTelemetry()

    def set(self, inner: Telemetry) -> None:
        self.inner = inner

    def session(self, **attrs: Any):
        return self.inner.session(**attrs)

    def span(self, name: str, **attrs: Any):
        return self.inner.span(name, **attrs)

    def event(self, name: str, **attrs: Any) -> None:
        self.inner.event(name, **attrs)

    def error(self, exc: BaseException, *, unexpected: bool = False) -> None:
        self.inner.error(exc, unexpected=unexpected)

    def flush(self) -> None:
        self.inner.flush()


class TelemetryFactory:
    @staticmethod
    def build(config: GlobalConfig, *, debug: bool = False) -> TelemetryHub:
        if debug:
            return TelemetryHub(ConsoleTelemetry())
        # Opt-in and endpoint present → OTel exporter (future plan). Until then: noop.
        return TelemetryHub(NoopTelemetry())
```

- [ ] **Step 2: Vérifier**

Run: `uv run python -c "
from services.telemetry import *
from core.config import GlobalConfig
hub = TelemetryFactory.build(GlobalConfig(), debug=True)
with hub.session(cli_version='x'):
    with hub.span('command.start', command='start'):
        hub.event('compose', args='up')
    hub.error(RuntimeError('boom'), unexpected=True)
hub.set(NoopTelemetry())
with hub.span('silent'): pass
print('ok')"`
Expected: lignes `[telemetry]` imbriquées sur stderr pour session/command/event/error, rien pour `silent`, puis `ok`.

- [ ] **Step 3: Commit**

```bash
git add services/telemetry.py
git commit -m "feat(services): add Telemetry contract with noop, console and hub implementations"
```

---

### Task 9 : `commands/base.py` — `Command`, `CommandGroup`, `LegacyCommand`

**Files:**
- Create: `commands/base.py`

**Interfaces:**
- Consumes: `UI`, `Telemetry`, `DockerRunner`, erreurs.
- Produces:
  - `Command(ui, telemetry)` : attributs de classe `name`, `help`, `panel`, `no_args_is_help=False` ; `register(app)` ; `run(...)` abstraite ; helpers `require_docker(docker)`, `require_project_dir(path) -> Path`.
  - `CommandGroup(ui, telemetry)` : `name`, `help`, `commands: list[Command]`, `typer() -> typer.Typer`, `register(app)`.
  - `LegacyCommand(ui, telemetry, fn, *, name, help, panel, no_args_is_help=True)`.

- [ ] **Step 1: Écrire le module**

```python
"""Command base classes. Typer registers bound `run` methods; dependencies come via constructors."""

from __future__ import annotations

import functools
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path

import typer

from core.errors import ConfigError, DockerError, UserAbort
from services.docker import DockerRunner
from services.telemetry import Telemetry
from ui import UI


class Command(ABC):
    name: str
    help: str
    panel: str = "General"
    no_args_is_help: bool = False

    def __init__(self, ui: UI, telemetry: Telemetry) -> None:
        self.ui = ui
        self.telemetry = telemetry

    # ---- registration -----------------------------------------------------

    def register(self, app: typer.Typer) -> None:
        app.command(
            self.name,
            help=self.help,
            rich_help_panel=self.panel,
            no_args_is_help=self.no_args_is_help,
        )(self._traced(self.run))

    def _traced(self, fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with self.telemetry.span(f"command.{self.name}"):
                return fn(*args, **kwargs)

        return wrapper

    @abstractmethod
    def run(self, *args, **kwargs) -> None: ...

    # ---- shared helpers ---------------------------------------------------

    def require_docker(self, docker: DockerRunner) -> None:
        """Binary present and daemon up, offering to start it when interactive."""
        if not docker.available():
            raise DockerError(
                "Docker not found (binary missing).",
                hint="Install Docker: https://docs.docker.com/get-docker/",
            )
        if docker.daemon_running():
            return
        self.ui.warning("Docker is installed but the daemon is not running.")
        if self.ui.confirm("Do you want to try starting Docker?", default=False):
            with self.ui.status("Waiting for Docker to start..."):
                started = docker.start_daemon()
            if started:
                self.ui.success("Docker started successfully.")
                return
        raise DockerError("Docker is required to continue.", hint="Start the Docker daemon and retry.")

    @staticmethod
    def require_project_dir(path: Path) -> Path:
        path = path.resolve()
        if not (path / "docker-compose.yml").exists():
            raise ConfigError(
                f"No Portabase configuration found in: {path}",
                hint="Expected a docker-compose.yml created by 'portabase agent' or 'portabase dashboard'.",
            )
        return path

    def confirm_or_abort(self, question: str, *, default: bool = False, value: bool | None = None) -> None:
        if not self.ui.confirm(question, default=default, value=value):
            raise UserAbort()


class CommandGroup:
    name: str
    help: str
    panel: str = "General"

    def __init__(self, ui: UI, telemetry: Telemetry) -> None:
        self.ui = ui
        self.telemetry = telemetry

    @property
    @abstractmethod
    def commands(self) -> list[Command]: ...

    def typer(self) -> typer.Typer:
        sub = typer.Typer(help=self.help, no_args_is_help=True)
        for cmd in self.commands:
            cmd.register(sub)
        return sub

    def register(self, app: typer.Typer) -> None:
        app.add_typer(self.typer(), name=self.name, rich_help_panel=self.panel)


class LegacyCommand(Command):
    """Adapter for the pre-refactor function-style commands. Removed in plan 4."""

    def __init__(
        self,
        ui: UI,
        telemetry: Telemetry,
        fn: Callable,
        *,
        name: str,
        help: str,
        panel: str,
        no_args_is_help: bool = True,
    ) -> None:
        super().__init__(ui, telemetry)
        self.name, self.help, self.panel, self.no_args_is_help = name, help, panel, no_args_is_help
        self._fn = fn

    def register(self, app: typer.Typer) -> None:
        app.command(
            self.name,
            help=self.help,
            rich_help_panel=self.panel,
            no_args_is_help=self.no_args_is_help,
        )(self._traced(self._fn))

    def run(self, *args, **kwargs) -> None:
        return self._fn(*args, **kwargs)
```

Note : `_traced` utilise `functools.wraps`, donc Typer voit la signature de la fonction d'origine (`__wrapped__`) — c'est ce qui permet d'envelopper sans casser l'introspection des paramètres.

- [ ] **Step 2: Vérifier l'introspection Typer à travers `_traced`**

Run: `uv run python -c "
from typing import Annotated
import typer
from commands.base import Command
from ui import UI
from services.telemetry import NoopTelemetry
class Hello(Command):
    name, help, panel = 'hello', 'Say hello', 'Test'
    def run(self, name: Annotated[str, typer.Argument()], loud: Annotated[bool, typer.Option('--loud')] = False):
        print('hello', name.upper() if loud else name)
app = typer.Typer(add_completion=False)
@app.callback()
def root(): pass
Hello(UI(), NoopTelemetry()).register(app)
app(['hello', 'bob', '--loud'], standalone_mode=False)"`
Expected: `hello BOB`.

- [ ] **Step 3: Commit**

```bash
git add commands/base.py
git commit -m "feat(commands): add Command, CommandGroup and LegacyCommand base classes"
```

---

### Task 10 : `services/updater.py`

**Files:**
- Create: `services/updater.py`

**Interfaces:**
- Consumes: `HttpClient`, `GlobalConfig`, `core.version`.
- Produces: `Release(tag, assets: dict[str, str], prerelease: bool)` ; `UpdateChecker(http, config, current: str)` : `include_prerelease -> bool`, `latest(force=False) -> Release | None` (cache 24 h, `None` si réseau KO), `available() -> str | None` (tag plus récent ou `None`) ; `Updater(http, current: str)` : `asset_name() -> str`, `target_path() -> Path`, `download(release, on_progress) -> Path` (vérifie sha256 via `checksums.txt`), `install(tmp: Path, target: Path) -> None`.

- [ ] **Step 1: Écrire le module**

```python
"""Update check (notify only) and manual update with checksum verification."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.config import GlobalConfig
from core.errors import NetworkError, UpdateError
from core.version import UNKNOWN, is_prerelease, parse_version
from services.http import HttpClient

GITHUB_REPO = "Portabase/cli"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
CACHE_TTL = 24 * 3600


@dataclass(frozen=True)
class Release:
    tag: str
    assets: dict[str, str]  # name -> browser_download_url
    prerelease: bool

    @classmethod
    def from_api(cls, data: dict) -> Release:
        return cls(
            tag=str(data.get("tag_name", "")).lstrip("v"),
            assets={a["name"]: a["browser_download_url"] for a in data.get("assets", [])},
            prerelease=bool(data.get("prerelease", False)),
        )


def platform_asset_name() -> str:
    system = platform.system().lower()
    system = "macos" if system == "darwin" else system
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    name = f"portabase_{system}_{arch}"
    return name + ".exe" if system == "windows" else name


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


class UpdateChecker:
    def __init__(self, http: HttpClient, config: GlobalConfig, current: str) -> None:
        self.http = http
        self.config = config
        self.current = current
        self.cache_file = config.cache_dir / "release.json"

    @property
    def include_prerelease(self) -> bool:
        channel = self.config.update_channel
        if channel:
            return channel == "beta"
        return is_prerelease(self.current)

    def fetch_latest(self) -> Release | None:
        """Network call. Returns None when nothing is published."""
        if self.include_prerelease:
            releases = self.http.get_json(RELEASES_URL)
            return Release.from_api(releases[0]) if releases else None
        return Release.from_api(self.http.get_json(f"{RELEASES_URL}/latest"))

    def latest(self, *, force: bool = False) -> Release | None:
        """Cached 24h. Returns None on any network failure — never raises."""
        if not force:
            cached = self._read_cache()
            if cached is not None:
                return cached
        try:
            release = self.fetch_latest()
        except NetworkError:
            return None
        if release is not None:
            self._write_cache(release)
        return release

    def available(self, *, force: bool = False) -> str | None:
        if self.current == UNKNOWN:
            return None
        release = self.latest(force=force)
        if release is None:
            return None
        if parse_version(release.tag) > parse_version(self.current):
            return release.tag
        return None

    def _read_cache(self) -> Release | None:
        try:
            with open(self.cache_file, encoding="utf-8") as f:
                data = json.load(f)
            if time.time() - float(data.get("checked_at", 0)) > CACHE_TTL:
                return None
            if data.get("channel_pre") != self.include_prerelease:
                return None
            return Release(tag=data["tag"], assets=data.get("assets", {}), prerelease=bool(data.get("prerelease")))
        except (OSError, ValueError, KeyError):
            return None

    def _write_cache(self, release: Release) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "checked_at": time.time(),
                        "channel_pre": self.include_prerelease,
                        "tag": release.tag,
                        "assets": release.assets,
                        "prerelease": release.prerelease,
                    },
                    f,
                )
        except OSError:
            pass


class Updater:
    CHECKSUMS_ASSET = "checksums.txt"

    def __init__(self, http: HttpClient, current: str) -> None:
        self.http = http
        self.current = current

    def target_path(self) -> Path:
        if is_frozen():
            return Path(sys.executable).resolve()
        if platform.system().lower() == "windows":
            return Path(os.environ.get("APPDATA", "")) / "Portabase" / "portabase.exe"
        default = Path("/usr/local/bin/portabase")
        return default if default.exists() else Path.home() / ".local" / "bin" / "portabase"

    def download(self, release: Release, on_progress: Callable[[int], None] | None = None) -> Path:
        name = platform_asset_name()
        url = release.assets.get(name)
        if url is None:
            raise UpdateError(
                f"No binary for this platform ({name}) in release {release.tag}.",
                hint="Available: " + ", ".join(sorted(release.assets)) if release.assets else None,
            )
        fd, tmp = tempfile.mkstemp(prefix="portabase_update_")
        os.close(fd)
        tmp_path = Path(tmp)
        try:
            self.http.download(url, tmp_path, on_progress, timeout=60)
            self._verify(release, name, tmp_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        return tmp_path

    def expected_size(self, release: Release) -> int | None:
        url = release.assets.get(platform_asset_name())
        return self.http.content_length(url) if url else None

    def _verify(self, release: Release, name: str, path: Path) -> None:
        url = release.assets.get(self.CHECKSUMS_ASSET)
        if url is None:
            raise UpdateError(f"Release {release.tag} has no {self.CHECKSUMS_ASSET}; refusing to install.")
        expected = None
        for line in self.http.get_text(url).splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                expected = parts[0].lower()
        if expected is None:
            raise UpdateError(f"{name} not listed in {self.CHECKSUMS_ASSET}; refusing to install.")
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise UpdateError("Checksum mismatch for downloaded binary; refusing to install.")

    def install(self, tmp: Path, target: Path) -> None:
        system = platform.system().lower()
        if system != "windows":
            tmp.chmod(0o755)
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = target.with_name(target.name + ".old")
        writable = os.access(target.parent, os.W_OK) and (not target.exists() or os.access(target, os.W_OK))
        try:
            if writable or system == "windows":
                if target.exists():
                    backup.unlink(missing_ok=True)
                    target.rename(backup)
                shutil.move(str(tmp), str(target))
            else:
                if target.exists():
                    subprocess.run(["sudo", "mv", str(target), str(backup)], check=True)
                subprocess.run(["sudo", "mv", str(tmp), str(target)], check=True)
                subprocess.run(["sudo", "chmod", "+x", str(target)], check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            raise UpdateError(f"Could not install to {target}: {e}", cause=e) from e
```

- [ ] **Step 2: Vérifier le checker (réseau requis)**

Run: `uv run python -c "
from pathlib import Path; import tempfile
from services.http import HttpClient
from services.updater import UpdateChecker, platform_asset_name
from core.config import GlobalConfig
cfg = GlobalConfig(Path(tempfile.mkdtemp())/'config.json')
c = UpdateChecker(HttpClient(), cfg, '0.0.1')
r = c.latest(force=True); print('latest:', r.tag, 'pre:', r.prerelease, 'assets:', len(r.assets))
print('cached:', c.latest().tag == r.tag, '| available from 0.0.1:', c.available())
print('asset for this machine:', platform_asset_name(), platform_asset_name() in r.assets)"`
Expected: tag de la dernière release stable (ex. `26.07.6`), `cached: True`, `available from 0.0.1: <tag>`, asset présent `True` sur linux/macos.

- [ ] **Step 3: Commit**

```bash
git add services/updater.py
git commit -m "feat(services): add UpdateChecker (notify, cached) and Updater with checksum verification"
```

---

### Task 11 : `commands/lifecycle.py`, `commands/config.py`, `commands/update.py`

**Files:**
- Create: `commands/lifecycle.py`
- Modify: `commands/config.py` (réécriture complète)
- Create: `commands/update.py`
- Delete: `commands/common.py` (Task 12, après bascule de `main.py`)

**Interfaces:**
- Consumes: `Command`, `CommandGroup`, `DockerRunner`, `UpdateChecker`, `Updater`, `GlobalConfig`.
- Produces: classes `StartCommand`, `StopCommand`, `RestartCommand`, `LogsCommand`, `UninstallCommand` (constructeur `(ui, telemetry, docker)`) ; `ConfigCommands(ui, telemetry, config)` groupe `config` avec `show`, `get`, `set`, `channel` ; `UpdateCommand(ui, telemetry, checker, updater)`.

- [ ] **Step 1: `commands/lifecycle.py`**

```python
"""start / stop / restart / logs / uninstall. No rendering: work on any folder with a compose file."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import typer

from commands.base import Command
from services.docker import DockerRunner
from services.telemetry import Telemetry
from ui import UI

PathArg = Annotated[Path, typer.Argument(help="Path to the component folder")]


class _ComposeCommand(Command):
    panel = "Lifecycle"
    no_args_is_help = True
    verb: str
    compose_args: list[str]
    done: str

    def __init__(self, ui: UI, telemetry: Telemetry, docker: DockerRunner) -> None:
        super().__init__(ui, telemetry)
        self.docker = docker

    def run(self, path: PathArg) -> None:
        path = self.require_project_dir(path)
        self.require_docker(self.docker)
        with self.ui.status(f"{self.verb} {path.name}..."):
            self.docker.compose(path, self.compose_args)
        self.ui.success(self.done)


class StartCommand(_ComposeCommand):
    name, help = "start", "Start a Portabase component."
    verb, compose_args, done = "Starting", ["up", "-d"], "Started"


class StopCommand(_ComposeCommand):
    name, help = "stop", "Stop a Portabase component."
    verb, compose_args, done = "Stopping", ["stop"], "Stopped"


class RestartCommand(_ComposeCommand):
    name, help = "restart", "Restart a Portabase component."
    verb, compose_args, done = "Restarting", ["restart"], "Restarted"


class LogsCommand(Command):
    name, help, panel = "logs", "View logs of a Portabase component.", "Lifecycle"
    no_args_is_help = True

    def __init__(self, ui: UI, telemetry: Telemetry, docker: DockerRunner) -> None:
        super().__init__(ui, telemetry)
        self.docker = docker

    def run(
        self,
        path: PathArg,
        follow: Annotated[bool, typer.Option("--follow/--no-follow", "-f", help="Follow log output")] = True,
    ) -> None:
        path = self.require_project_dir(path)
        self.require_docker(self.docker)
        args = ["logs", "-f"] if follow else ["logs"]
        try:
            self.docker.compose(path, args, check=False)
        except KeyboardInterrupt:
            pass


class UninstallCommand(Command):
    name, help, panel = "uninstall", "Uninstall and delete a Portabase component.", "Lifecycle"
    no_args_is_help = True

    def __init__(self, ui: UI, telemetry: Telemetry, docker: DockerRunner) -> None:
        super().__init__(ui, telemetry)
        self.docker = docker

    def run(
        self,
        path: PathArg,
        force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
    ) -> None:
        path = self.require_project_dir(path)
        self.require_docker(self.docker)
        if not force:
            self.ui.warning(f"This will delete containers, volumes and all data in {path}.")
            self.confirm_or_abort("Are you sure?", default=False)
        with self.ui.status("Uninstalling..."):
            self.docker.compose(path, ["down", "-v"])
            try:
                shutil.rmtree(path)
            except OSError as e:
                self.ui.warning(f"Could not remove directory: {e}")
        self.ui.success("Uninstalled")
```

- [ ] **Step 2: `commands/config.py` (réécriture)**

```python
"""Global configuration (~/.portabase/config.json)."""

from __future__ import annotations

from typing import Annotated

import typer

from commands.base import Command, CommandGroup
from core.config import GlobalConfig
from core.errors import ValidationError
from services.telemetry import Telemetry
from ui import UI

CHANNELS = ("stable", "beta")
BOOL_KEYS = ("telemetry",)


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
            self.ui.print(f"  [key]{key}[/key]: {data[key]}  [hint](unknown key)[/hint]")


class ConfigGet(_ConfigCommand):
    name, help = "get", "Print one configuration value."
    no_args_is_help = True

    def run(self, key: Annotated[str, typer.Argument(help="Configuration key")]) -> None:
        value = self.config.get(key)
        if value is None:
            raise ValidationError(f"'{key}' is not set.", hint="Known keys: " + ", ".join(GlobalConfig.KNOWN_KEYS))
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
            raise ValidationError(f"Invalid channel '{value}'.", hint="Choose 'stable' or 'beta'.")
        stored: object = value
        if key in BOOL_KEYS:
            lowered = value.lower()
            if lowered not in ("true", "false", "1", "0", "yes", "no"):
                raise ValidationError(f"'{key}' expects true or false.")
            stored = lowered in ("true", "1", "yes")
        self.config.set(key, stored)
        self.ui.success(f"{key} = {stored}")


class ConfigChannel(_ConfigCommand):
    """Kept for compatibility with the previous `config channel <name>` command."""

    name, help = "channel", "Set the update channel (stable or beta)."
    no_args_is_help = True

    def run(self, name: Annotated[str, typer.Argument(help="stable or beta")]) -> None:
        ConfigSet(self.ui, self.telemetry, self.config).run("update_channel", name.lower())


class ConfigCommands(CommandGroup):
    name, help, panel = "config", "Manage global CLI configuration.", "Configuration"

    def __init__(self, ui: UI, telemetry: Telemetry, config: GlobalConfig) -> None:
        super().__init__(ui, telemetry)
        self.config = config

    @property
    def commands(self) -> list[Command]:
        deps = (self.ui, self.telemetry, self.config)
        return [ConfigShow(*deps), ConfigGet(*deps), ConfigSet(*deps), ConfigChannel(*deps)]
```

- [ ] **Step 3: `commands/update.py`**

```python
"""Manual update. Auto-update is gone; main.py only prints a notice after commands."""

from __future__ import annotations

from commands.base import Command
from core.errors import UpdateError
from core.version import UNKNOWN, parse_version
from services.telemetry import Telemetry
from services.updater import Release, UpdateChecker, Updater, is_frozen
from ui import UI


class UpdateCommand(Command):
    name, help, panel = "update", "Update the CLI to the latest version.", "System"

    def __init__(self, ui: UI, telemetry: Telemetry, checker: UpdateChecker, updater: Updater) -> None:
        super().__init__(ui, telemetry)
        self.checker = checker
        self.updater = updater

    def run(self) -> None:
        if not is_frozen():
            self.ui.warning("The update command is only available for the binary version of Portabase CLI.")
            self.ui.info("If you installed from source, use [bold]git pull[/bold] to update.")
            return

        current = self.checker.current
        release = self._latest()
        if release.tag == current:
            self.ui.success(f"Portabase CLI is already up to date ({current}).")
            return
        if current != UNKNOWN and parse_version(release.tag) < parse_version(current):
            self.ui.warning(f"Current version ({current}) is newer than the latest remote version ({release.tag}).")
            self.confirm_or_abort("Continue with the downgrade?", default=False)

        target = self.updater.target_path()
        self.ui.info(f"Updating Portabase CLI from {current} to {release.tag}")
        self.ui.info(f"Target installation path: {target}")

        total = self.updater.expected_size(release) or 0
        with self.ui.progress().download(f"Downloading {release.tag}...", total) as advance:
            tmp = self.updater.download(release, advance)
        self.updater.install(tmp, target)
        self.ui.success(f"Successfully updated to {release.tag}!")

    def _latest(self) -> Release:
        try:
            release = self.checker.fetch_latest()
        except Exception as e:  # NetworkError
            raise UpdateError("Could not fetch latest release data from GitHub.", cause=e) from e
        if release is None:
            raise UpdateError("No release found for this channel.")
        return release
```

- [ ] **Step 4: Vérifier le lint des nouveaux fichiers**

Run: `uv run ruff check commands/lifecycle.py commands/config.py commands/update.py commands/base.py services ui core`
Expected: `All checks passed!`. (`except Exception` dans `_latest` : remplacer par `except NetworkError` en important `NetworkError` depuis `core.errors` si ruff `BLE001` se plaint — c'est de toute façon plus précis.)

- [ ] **Step 5: Commit**

```bash
git add commands/lifecycle.py commands/config.py commands/update.py
git commit -m "feat(commands): rewrite lifecycle, config and update commands as classes"
```

---

### Task 12 : `main.py` — câblage, catcher, bascule

**Files:**
- Modify: `main.py` (réécriture complète)
- Delete: `commands/common.py`, `core/updater.py`
- Modify: `pyproject.toml` (`TID251`, per-file-ignores)

**Interfaces:**
- Consumes: tout ce qui précède + fonctions legacy `commands.agent.agent`, `commands.dashboard.dashboard`, `commands.db.app`.
- Produces: `Settings`, `build_app(ui, telemetry, config, settings) -> tuple[typer.Typer, UpdateChecker]`, `main() -> None`.

- [ ] **Step 1: Réécrire `main.py`**

```python
"""Entry point. Builds dependencies, registers commands, owns the single error boundary."""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass
from typing import Annotated

import click
import typer

from commands import agent as legacy_agent
from commands import dashboard as legacy_dashboard
from commands import db as legacy_db
from commands.base import LegacyCommand
from commands.config import ConfigCommands
from commands.lifecycle import LogsCommand, RestartCommand, StartCommand, StopCommand, UninstallCommand
from commands.update import UpdateCommand
from core.config import GlobalConfig
from core.errors import PortabaseError, UserAbort, ValidationError
from core.version import current_version
from services.docker import DockerRunner
from services.http import HttpClient
from services.telemetry import ConsoleTelemetry, TelemetryFactory, TelemetryHub
from services.updater import UpdateChecker, Updater, is_frozen
from ui import UI


@dataclass
class Settings:
    non_interactive: bool = False
    verbose: bool = False
    debug: bool = False
    no_color: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            non_interactive=os.environ.get("PORTABASE_NON_INTERACTIVE", "").lower() in ("1", "true", "yes")
            or not sys.stdin.isatty(),
            no_color=bool(os.environ.get("NO_COLOR")),
        )


def build_app(
    ui: UI, telemetry: TelemetryHub, config: GlobalConfig, settings: Settings
) -> tuple[typer.Typer, UpdateChecker]:
    app = typer.Typer(no_args_is_help=True, add_completion=False, rich_markup_mode="rich")
    http = HttpClient()
    docker = DockerRunner()
    version = current_version()
    checker = UpdateChecker(http, config, version)
    updater = Updater(http, version)

    def version_callback(value: bool) -> None:
        if value:
            ui.print(f"Portabase CLI version: {version}")
            latest = checker.available(force=True)
            if latest:
                ui.warning(f"A new version is available: [bold]{latest}[/bold]")
            raise typer.Exit()

    @app.callback()
    def root(
        _version: Annotated[
            bool | None,
            typer.Option("--version", help="Show the version and exit.", callback=version_callback, is_eager=True),
        ] = None,
        verbose: Annotated[bool, typer.Option("--verbose", help="Show error causes and tracebacks.")] = False,
        debug: Annotated[bool, typer.Option("--debug", help="Verbose plus telemetry trace on stderr.")] = False,
        no_color: Annotated[bool, typer.Option("--no-color", help="Disable colours.")] = False,
        non_interactive: Annotated[
            bool,
            typer.Option("--non-interactive", envvar="PORTABASE_NON_INTERACTIVE", help="Never prompt; fail on missing input."),
        ] = False,
    ) -> None:
        """Portabase CLI to manage agents, dashboards and databases."""
        settings.verbose = verbose or debug
        settings.debug = debug
        settings.no_color = settings.no_color or no_color
        settings.non_interactive = settings.non_interactive or non_interactive
        ui.configure(verbose=settings.verbose, no_color=settings.no_color, non_interactive=settings.non_interactive)
        if debug:
            telemetry.set(ConsoleTelemetry())

    commands = [
        LegacyCommand(ui, telemetry, legacy_agent.agent, name="agent", help="Create a new Portabase Agent instance.", panel="Creation"),
        LegacyCommand(ui, telemetry, legacy_dashboard.dashboard, name="dashboard", help="Create a new Portabase Dashboard instance.", panel="Creation"),
        StartCommand(ui, telemetry, docker),
        StopCommand(ui, telemetry, docker),
        RestartCommand(ui, telemetry, docker),
        LogsCommand(ui, telemetry, docker),
        UninstallCommand(ui, telemetry, docker),
        UpdateCommand(ui, telemetry, checker, updater),
    ]
    for cmd in commands:
        cmd.register(app)

    app.add_typer(legacy_db.app, name="db", rich_help_panel="Configuration")  # legacy, replaced in plan 4
    ConfigCommands(ui, telemetry, config).register(app)

    return app, checker


def _notify_update(ui: UI, checker: UpdateChecker, settings: Settings, invoked: str | None) -> None:
    if not is_frozen() or settings.non_interactive or invoked in ("update", None):
        return
    latest = checker.available()
    if latest:
        ui.print("")
        ui.warning(f"A new version of Portabase CLI is available: [bold]{latest}[/bold] (current: {checker.current})")
        ui.info("Run [bold]portabase update[/bold] to update.")


def main() -> None:
    settings = Settings.from_env()
    config = GlobalConfig()
    ui = UI(non_interactive=settings.non_interactive, no_color=settings.no_color)
    telemetry = TelemetryFactory.build(config, debug=False)
    app, checker = build_app(ui, telemetry, config, settings)
    invoked = next((a for a in sys.argv[1:] if not a.startswith("-")), None)
    exit_code = 0

    try:
        with telemetry.session(cli_version=current_version(), os=platform.system()):
            app(standalone_mode=False)
    except UserAbort as e:
        ui.warning(e.message)
        telemetry.event("abort")
        exit_code = e.exit_code
    except PortabaseError as e:
        ui.error(e)
        telemetry.error(e)
        exit_code = e.exit_code
    except click.exceptions.NoArgsIsHelpError:
        exit_code = 0  # help already printed by Typer
    except click.exceptions.Exit as e:  # typer.Exit from legacy code or --help
        exit_code = e.exit_code
    except click.exceptions.Abort:  # typer.Abort from legacy code
        ui.warning("Cancelled.")
        exit_code = 130
    except click.UsageError as e:
        err = ValidationError(e.format_message(), hint="Run 'portabase --help' for usage.")
        ui.error(err)
        telemetry.error(err)
        exit_code = err.exit_code
    except KeyboardInterrupt:
        ui.console.print("")
        ui.warning("Cancelled.")
        exit_code = 130
    except Exception as e:  # noqa: BLE001 — last resort: a bug, not an expected error
        wrapped = PortabaseError("Unexpected error: " + str(e), cause=e)
        ui.error(wrapped, unexpected=True)
        telemetry.error(e, unexpected=True)
        exit_code = 1
    finally:
        telemetry.flush()

    if exit_code == 0:
        _notify_update(ui, checker, settings, invoked)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Supprimer les modules remplacés**

Run: `git rm commands/common.py core/updater.py`

Puis vérifier qu'aucun import ne subsiste :
Run: `grep -rn "commands.common\|core.updater\|check_for_updates\|update_cli" --include=*.py . | grep -v ".venv"`
Expected: aucune sortie.

- [ ] **Step 3: Mettre à jour `pyproject.toml`**

Remplacer le bloc `[tool.ruff.lint.per-file-ignores]` par :

```toml
# Code legacy supprimé au plan 4. Ne pas étendre cette liste.
[tool.ruff.lint.per-file-ignores]
"commands/agent.py" = ["BLE001", "E722", "S110", "SIM102", "TID251"]
"commands/db.py" = ["BLE001", "E722", "S110", "TID251"]
"commands/dashboard.py" = ["BLE001", "TID251"]
"core/config.py" = ["BLE001", "E722", "S110"]
"core/utils.py" = ["BLE001", "E722", "S110", "PLR1730", "TID251"]
"core/network.py" = ["BLE001", "TID251"]
"main.py" = ["TID251"]

[tool.ruff.lint.flake8-tidy-imports.banned-api]
"rich.prompt".msg = "Use ui.form() / ui.confirm() instead."
"rich.console".msg = "Only ui/ may build a Console. Use the UI facade."
"typer.prompt".msg = "Use ui.form() instead."
"typer.confirm".msg = "Use ui.confirm() instead."
```

Et ajouter `"TID251"` dans `select` s'il n'y est pas déjà (il y est depuis Plan 1). `main.py` importe `click` et `typer.Exit`, pas de prompt : `TID251` sur `main.py` est là uniquement pour `ui.console.print` ? Non — `rich.console` n'y est pas importé. Retirer `"main.py" = ["TID251"]` si `ruff check` passe sans.

Ajouter `known-first-party = ["commands", "core", "services", "ui", "templates"]` dans `[tool.ruff.lint.isort]`.

- [ ] **Step 4: Lint complet**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: passe. Sinon `uv run ruff format .` puis corriger les erreurs signalées **dans les nouveaux fichiers uniquement**.

- [ ] **Step 5: Vérifier l'aide et les erreurs de saisie**

Run: `uv run python main.py; echo "exit=$?"`
Expected: aide affichée, `exit=0`.

Run: `uv run python main.py --help | head -30`
Expected: panneaux `Creation` (agent, dashboard), `Lifecycle` (start, stop, restart, logs, uninstall), `Configuration` (db, config), `System` (update) ; options `--version`, `--verbose`, `--debug`, `--no-color`, `--non-interactive`.

Run: `uv run python main.py start; echo "exit=$?"`
Expected: aide de `start` (no_args_is_help), `exit=0`.

Run: `uv run python main.py bogus; echo "exit=$?"`
Expected: `✖ Error: No such command 'bogus'.` + hint, `exit=2`.

Run: `uv run python main.py start /tmp/does-not-exist; echo "exit=$?"`
Expected: `✖ Error: No Portabase configuration found in: /tmp/does-not-exist` + hint, `exit=3`.

Run: `uv run python main.py --verbose start /tmp/does-not-exist 2>&1 | grep -c "code: E_CONFIG"`
Expected: `1`.

- [ ] **Step 6: Vérifier config**

Run: `uv run python main.py config show && uv run python main.py config set update_channel beta && uv run python main.py config get update_channel && uv run python main.py config channel stable && uv run python main.py config set update_channel nope; echo "exit=$?"`
Expected: affichage, `✔ update_channel = beta`, `beta`, `✔ update_channel = stable`, puis `✖ Error: Invalid channel 'nope'.` `exit=2`.

- [ ] **Step 7: Vérifier update et --version (non-frozen)**

Run: `uv run python main.py update; echo "exit=$?"; uv run python main.py --version; echo "exit=$?"`
Expected: avertissement "only available for the binary version", `exit=0` ; version puis éventuellement "A new version is available", `exit=0`.

- [ ] **Step 8: Vérifier le mode non-interactif et Ctrl-C**

Run: `uv run python main.py --non-interactive uninstall /tmp/does-not-exist; echo "exit=$?"`
Expected: `E_CONFIG`, `exit=3` (l'erreur dossier précède la confirmation).

Créer un faux projet : `mkdir -p /tmp/pb-fake && touch /tmp/pb-fake/docker-compose.yml`.
Run: `uv run python main.py --non-interactive uninstall /tmp/pb-fake; echo "exit=$?"`
Expected (Docker présent) : confirm par défaut `False` → `⚠ Cancelled.` `exit=130`, dossier intact. (Docker absent : `E_DOCKER`, `exit=4`.)

Run: `uv run python main.py uninstall /tmp/pb-fake` puis Ctrl-C au prompt.
Expected: `⚠ Cancelled.`, `exit=130`, pas de traceback.

- [ ] **Step 9: Vérifier les commandes legacy à travers le catcher**

Run: `uv run python main.py agent; echo "exit=$?"` puis `uv run python main.py db list /tmp/does-not-exist; echo "exit=$?"`
Expected: aide de `agent` `exit=0` ; message legacy `No Portabase configuration found` (ancien style) et `exit=1` (via `typer.Exit(1)` → `click.exceptions.Exit`).

- [ ] **Step 10: Vérifier le lifecycle réel (si Docker disponible)**

```bash
cd /tmp && rm -rf pb-smoke && uv --directory /home/soluce/Documents/PROJETS/Portabase/cli run python /home/soluce/Documents/PROJETS/Portabase/cli/main.py dashboard pb-smoke --port 8899
```
Répondre `internal` au choix DB, `N` à "Start dashboard now?". Puis :

```bash
M=/home/soluce/Documents/PROJETS/Portabase/cli/main.py
uv --directory /home/soluce/Documents/PROJETS/Portabase/cli run python $M start /tmp/pb-smoke
uv --directory /home/soluce/Documents/PROJETS/Portabase/cli run python $M logs /tmp/pb-smoke --no-follow | tail -3
uv --directory /home/soluce/Documents/PROJETS/Portabase/cli run python $M restart /tmp/pb-smoke
uv --directory /home/soluce/Documents/PROJETS/Portabase/cli run python $M stop /tmp/pb-smoke
uv --directory /home/soluce/Documents/PROJETS/Portabase/cli run python $M uninstall /tmp/pb-smoke --force
ls /tmp/pb-smoke 2>&1
```
Expected: `✔ Started`, quelques lignes de logs, `✔ Restarted`, `✔ Stopped`, `✔ Uninstalled`, `No such file or directory`.

- [ ] **Step 11: Commit**

```bash
git add main.py pyproject.toml
git commit -m "refactor: wire commands through DI container and single error boundary

Lifecycle, config and update run on the new Command classes; agent,
dashboard and db stay on legacy code behind LegacyCommand until plan 4.
Auto-update is replaced by a post-command notice."
```

---

### Task 13 : Build smoke, PR

**Files:** aucun nouveau.

- [ ] **Step 1: Binaire local**

Run: `rm -rf build dist *.spec && uv run pyinstaller --onefile --name portabase_smoke --paths=. --collect-all rich --collect-all requests --collect-data certifi --add-data "pyproject.toml:." main.py && ./dist/portabase_smoke --version && ./dist/portabase_smoke config show && ./dist/portabase_smoke start /tmp/nope; echo "exit=$?"; rm -rf build dist *.spec`
Expected: version, config, `E_CONFIG` `exit=3`. Aucun `ModuleNotFoundError` (questionary, services, ui embarqués via `--paths=.`).

- [ ] **Step 2: PR**

```bash
git checkout -b refactor/foundations
git push -u origin refactor/foundations
```
Ouvrir la PR « refactor: foundations (errors, ui, services, Command) + lifecycle rewrite ». Checks Plan 1 verts attendus.

- [ ] **Step 3: Release candidate (optionnel mais recommandé)**

Après merge : Actions → Bump version → `26.08.0rc1`, channel `rc`. Installer le binaire rc sur une machine avec une install existante et dérouler `start/stop/logs/restart` + `--version` (la notification de mise à jour après commande s'affiche seulement en binaire).

---

## Self-review

**Spec coverage :**
- §3 structure : `core/errors`, `core/version`, `core/config` (GlobalConfig), `ui/*`, `services/{http,docker,telemetry,updater}`, `commands/{base,lifecycle,config,update}`, `main.py` ✔. `services/{envfile,ports,templates,renderer,project,compose_facts}`, `engines/`, `commands/{agent,dashboard,build,db,flows}` → Plans 3–4. `core/fields.py` : déviation documentée.
- §4.1 `Command`, `register`, `_traced`, injection ✔ (T9). `Annotated` ✔.
- §7 ui : tokens ✔, composants Banner/Message/Section/Status/Hint/Prompt ✔ + Progress (appelant : update). `Summary`, `DataTable`, `Diff` → Plan 4 (appelants). `Form` ✔ avec flag→prompt→défaut→erreur, `UserAbort` sur `None` ✔. `NO_COLOR` ✔. Pas de prompt sous status : respecté dans lifecycle (confirm avant status).
- §8.1 hiérarchie et codes ✔. §8.2 catcher, `standalone_mode=False`, mapping click ✔ (T12). §8.3 télémétrie contrat + noop + console + hub ✔ ; opt-in config lu par `TelemetryFactory` (endpoint ignoré tant qu'aucun exporter — documenté). §8.4 updater : notif après commande, cache 24 h, silencieux offline, checksum ✔.
- §10 B+C : shippable, legacy via `LegacyCommand` ✔.

**Placeholders :** aucun.

**Cohérence des types :** `UI.confirm(question, *, default, value)` utilisé par `Command.confirm_or_abort` et `require_docker` ✔ ; `Telemetry.span` context manager utilisé par `_traced` ✔ ; `UpdateChecker.available(force=)` utilisé par `version_callback` et `_notify_update` ✔ ; `Updater.expected_size/download/install` utilisés par `UpdateCommand` ✔ ; `HttpClient.content_length` utilisé par `Updater.expected_size` ✔ (`head_content_length` cité dans l'interface T7 = `content_length` ; nom retenu : `content_length`).

**Écarts connus :**
- `UpdateCommand._latest` : utiliser `except NetworkError` (T11 step 4).
