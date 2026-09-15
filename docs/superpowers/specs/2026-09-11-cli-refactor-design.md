# Refonte du CLI Portabase — Design

Date : 2026-09-11
Statut : validé en brainstorming, en attente de relecture avant plan d'implémentation.

## 1. Objectifs et périmètre

Refonte structurelle du CLI sans changement de dépendances majeures (Typer, Rich, questionary, requests, PyYAML conservés ; Jinja2 ajouté).

Objectifs :

- Supprimer la duplication entre `commands/agent.py` et `commands/db.py` (~500 lignes du wizard "ajouter une base" copiées).
- Remplacer la génération de `docker-compose.yml` par chirurgie texte (`.replace`, regex, ancres) par un rendu Jinja2 complet et déterministe.
- POO sur toute l'application : commandes, services, moteurs, composants UI en classes. Les utilitaires purs (`slugify`, `generate_password`, `validate_edge_key`) restent des fonctions.
- Chaque commande configurable intégralement par paramètres, sans mode interactif.
- Bibliothèque de composants `ui/` (approche shadcn : tokens, composants stateless, façade unique).
- Catcher d'erreurs unique avec hiérarchie d'exceptions et codes de sortie stables.
- Couche télémétrie prête pour OpenTelemetry, opt-in, sans dépendance immédiate.
- Plus d'auto-update : notification seulement, mise à jour manuelle.
- CI de PR (lint, Gitleaks, Plumber, validation des templates, build smoke), suppression du script `./release`.

Hors périmètre de cette spec :

- Tests automatisés (spec suivante ; la structure en tient compte : injection de dépendances, services sans I/O terminal, job `test` vide en CI).
- Sortie machine `--json`.
- Exporter OTel réel (le contrat est posé, l'implémentation viendra avec un endpoint).
- Fichier de spec déclaratif `build -f spec.yml`.
- Support Windows (inchangé : code présent, hors matrice de build).

## 2. Décisions structurantes

| Sujet | Décision |
|---|---|
| Layout | Plat, conservé (`main.py` racine, `--paths=.`). Nouveaux dossiers `services/`, `engines/`, `ui/`. |
| État d'une install | Aucun fichier d'état ajouté. Source de vérité = `.env` (variables runtime des conteneurs uniquement) + `databases.json` (contrat agent, inchangé) + lecture structurelle du compose existant pour le seul fait non dérivable (`host_gateway`). |
| Compose | Artefact dérivé, propriété du CLI, re-rendu intégralement à chaque commande mutante. Personnalisations utilisateur via `docker-compose.override.yml` (mécanisme Compose natif). |
| Templates | 100 % remote (S3), versionnés par version CLI exacte, manifest avec sha256, cache disque. Suppression du fallback `latest`. Source dans `templates/` à la racine du dépôt. |
| Création multi-DB | En non-interactif, `portabase agent` crée un agent sans base ; les bases s'ajoutent par `portabase db add` (un appel par base). En interactif, `agent` enchaîne sur une boucle « Add a database? » qui réutilise le même flux que `db add`. Pas de DSL `--db engine:opts`. |
| Options moteur | Flag générique répétable `-o/--option KEY=VALUE`, validé contre `DbEngine.option_fields()`. Pas de flag Typer par option. |
| Moteurs DB | Classes Python (`engines/`), registre à imports explicites. Pas de manifeste data-driven. |
| Input UI | questionary uniquement. `rich.prompt` et `typer.prompt` bannis (ruff). |
| Non-interactif | Flag `--non-interactive`, env `PORTABASE_NON_INTERACTIVE`, ou `stdin` non-TTY. Géré par `ui.Form`, pas par les commandes. |
| Erreurs | `PortabaseError` + sous-classes, codes de sortie distincts, un seul `try` dans `main.py`. `except:` nus interdits. |
| Télémétrie | Interface `Telemetry`, `NoopTelemetry` par défaut, opt-in via config globale, jamais de prompt. |
| Updater | Notification après la commande (cache 24 h, silencieux si hors ligne), `portabase update` manuel avec vérification de checksum. |
| Release | `bump.yml` (`workflow_dispatch`) remplace `./release`. Workflows de release sur tag inchangés. |
| Mot de passe | `generate_password` retire `$` et `` ` `` des symboles (cassent `--requirepass "${PASSWORD}"` via shell). Ne s'applique qu'aux nouvelles bases. |

## 3. Structure des fichiers

```
cli/
├── main.py                        # build_app(), catcher d'erreurs, codes de sortie
├── pyproject.toml                 # + jinja2 ; pyinstaller/ruff/pytest en groupe dev
│
├── commands/
│   ├── base.py                    # Command ABC, CommandGroup
│   ├── agent.py                   # AgentCommand
│   ├── dashboard.py               # DashboardCommand
│   ├── build.py                   # BuildCommand
│   ├── lifecycle.py               # Start/Stop/Restart/Logs/Uninstall (ex-common.py)
│   ├── db.py                      # DbCommands : add / remove / list
│   ├── config.py                  # ConfigCommands : get / set
│   ├── update.py                  # UpdateCommand
│   └── flows/
│       └── add_database.py        # AddDatabaseFlow : collecte + application, partagé par agent et db add
│
├── services/
│   ├── project.py                 # AgentProject, DashboardProject, DatabaseSpec, detect_kind()
│   ├── envfile.py                 # EnvFile
│   ├── compose_facts.py           # ComposeFacts (lecture structurelle, jamais d'écriture)
│   ├── renderer.py                # ComposeRenderer, RenderResult
│   ├── templates.py               # TemplateRepository, Manifest
│   ├── docker.py                  # DockerRunner
│   ├── ports.py                   # PortAllocator
│   ├── http.py                    # HttpClient
│   ├── updater.py                 # UpdateChecker, Updater
│   └── telemetry.py               # Telemetry ABC, NoopTelemetry, ConsoleTelemetry, TelemetryFactory
│
├── engines/
│   ├── __init__.py                # registry = EngineRegistry([...]) — imports explicites
│   ├── base.py                    # DbEngine ABC, Field
│   ├── registry.py                # EngineRegistry
│   ├── sql.py                     # StandardSqlEngine + Postgres/PostgresCluster/MySQL/MariaDB/MSSQL/Firebird
│   ├── redis.py                   # RedisEngine
│   ├── valkey.py                  # ValkeyEngine
│   ├── mongo.py                   # MongoEngine
│   ├── sqlite.py                  # SqliteEngine
│   └── docker_volume.py           # DockerVolumeEngine
│
├── ui/
│   ├── __init__.py                # façade UI
│   ├── theme.py                   # PALETTE → RICH_THEME + QUESTIONARY_STYLE
│   ├── form.py                    # Form (flag → prompt → défaut → erreur)
│   └── components/
│       ├── base.py                # Component(console)
│       ├── banner.py  message.py  section.py  summary.py  table.py
│       ├── status.py  hints.py    diff.py     prompt.py
│
├── core/
│   ├── errors.py                  # PortabaseError + sous-classes
│   ├── config.py                  # GlobalConfig (~/.portabase/config.json)
│   ├── version.py                 # current_version()
│   └── utils.py                   # slugify, generate_password, validate_edge_key — fonctions pures
│
├── templates/                     # source des templates remote (assets, pas un package Python)
│   ├── agent.yml.j2
│   ├── dashboard.yml.j2
│   ├── engines.map.json           # clé moteur → template (pour engines-check et manifest)
│   └── engines/
│       ├── postgresql.yml.j2  mysql.yml.j2  mariadb.yml.j2  mssql.yml.j2
│       ├── firebird.yml.j2    mongodb.yml.j2  redis.yml.j2  valkey.yml.j2
│
├── scripts/
│   └── render_check.py            # rend tous les templates avec fixtures, valide YAML + compose config
│
├── .github/workflows/
│   ├── ci.yml                     # PR : lint, render-check, engines-check, gitleaks, plumber, build-smoke, test
│   ├── bump.yml                   # workflow_dispatch : bump version + tag
│   ├── templates-hotfix.yml       # workflow_dispatch : re-upload templates vers une version existante
│   ├── release.yml, release-candidate.yml, python.yml, github.yml   # inchangés (hors durcissement)
│   └── templates-upload.yml       # + génération manifest.json, source templates/
│
├── .gitleaks.toml
└── supprimés : release, templates/compose.py, templates/__init__.py, commands/common.py,
                core/network.py, core/docker.py, .github/assets/templates/
```

Règle de dépendance, descendante uniquement :

- `commands` → `services`, `engines`, `ui`, `core`
- `services` → `engines`, `core` (jamais `ui` : un service lève, n'affiche rien)
- `engines` → `core`
- `ui` → `core`

## 4. Commandes

### 4.1 `Command`

```python
class Command(ABC):
    name: str
    help: str
    panel: str = "General"

    def __init__(self, ui: UI, telemetry: Telemetry): ...
    def register(self, app: typer.Typer) -> None:
        app.command(self.name, help=self.help, rich_help_panel=self.panel)(self.run)

    @abstractmethod
    def run(self, *args, **kwargs) -> None: ...
```

`base.py` wrappe `run` dans `telemetry.span(f"command.{name}")`. Les dépendances (`DockerRunner`, `TemplateRepository`, `EngineRegistry`, `PortAllocator`) sont injectées par constructeur dans `main.build_app()`.

Signatures Typer en `Annotated[...]`. Chaque option qui correspond à une question du wizard a une valeur par défaut `None` : présente → utilisée, absente → prompt (interactif) ou défaut/erreur (non-interactif). Une seule méthode `_collect()` par commande, aucun `if non_interactive` dans la logique métier.

### 4.2 Inventaire

| Commande | Options notables | Effet |
|---|---|---|
| `agent NAME` | `--key`, `--tz`, `--polling`, `--host-gateway/--no-host-gateway`, `--start`, `--force`, `--non-interactive` | crée le dossier, `.env`, `databases.json` vide, rend le compose. En interactif, enchaîne sur une boucle « Add a database? » (`AddDatabaseFlow`, rendu après chaque ajout). En non-interactif, ne crée aucune base. |
| `dashboard NAME` | `--port`, `--db-mode external\|internal\|custom`, `--db-host/--db-port/--db-name/--db-user/--db-password-stdin`, `--start`, `--force` | crée `.env`, rend le compose. |
| `db add NAME` | `--engine`, `--mode new\|existing`, `--auth/--no-auth`, `--name`, `--host`, `--port`, `--database`, `--user`, `--password`, `--password-stdin`, `--path`, `--volume`, `--container`, `--label`, `-o/--option KEY=VALUE` (répétable) | collecte via `AddDatabaseFlow` selon le moteur, mute `.env` + `databases.json`, re-rend. Flag ou option fourni mais non pertinent pour le moteur/mode → `ValidationError`. |
| `db remove NAME` | `--id` ou `--name`, `--purge-volume` | retire l'entrée, retire les variables `.env` du service, re-rend. Le volume Docker n'est supprimé que sur `--purge-volume`. |
| `db list NAME` | — | lecture seule. |
| `build PATH` | `--diff`, `--stdout`, `--inline-env`, `--output DIR` | re-rend depuis l'état. Sans option : écrit en place (= migration legacy). `--inline-env` substitue les valeurs au lieu de `${VAR}` avec avertissement secrets en clair. |
| `start/stop/restart/logs/uninstall PATH` | inchangées (`uninstall --force`) | n'utilisent pas le renderer, fonctionnent sur toute install. |
| `config get/set` | inchangées + clés `telemetry`, `telemetry_endpoint`, `channel` | config globale. |
| `update` | — | mise à jour manuelle avec vérification checksum. |

Options globales : `--verbose`, `--debug`, `--no-color`, `--non-interactive`. Détection `kind` d'un dossier : `databases.json` présent → agent ; `PROJECT_SECRET` dans `.env` → dashboard.

Le choix `back` dans les selects disparaît : interactif = Ctrl-C (`UserAbort`) ou entrée "cancel" en fin de liste.

### 4.3 `AddDatabaseFlow` (`commands/flows/add_database.py`)

Le wizard d'ajout de base est un objet réutilisable, pas une commande. C'est la duplication actuelle entre `agent.py` et `db.py` qui disparaît.

```python
class AddDatabaseFlow:
    def __init__(self, ui: UI, engines: EngineRegistry, ports: PortAllocator): ...

    def collect(self, values: dict) -> DatabaseSpec:
        """values = flags parsés (engine, mode, auth, host…, options).
        Champ manquant → prompt (interactif) / défaut / ValidationError (non-interactif)."""

    def apply(self, project: AgentProject, spec: DatabaseSpec) -> None:
        """Mute project.env (variables du service si managed) et project.databases, en mémoire."""
```

Séquence de `collect` : moteur (`--engine` ou select) → affiche `engine.warning` s'il existe → mode (`--mode` ou select ; sqlite et docker-volume n'ont pas de mode `existing`/`new` au sens service : sqlite distingue fichier créé vs chemin existant, docker-volume n'a qu'un mode) → variante auth si `engine.auth_variants` → `Form.collect(engine.fields_new() | fields_existing(), values)` → `Form.collect(engine.option_fields(), values["options"])` → `engine.generate(...)` ou construction depuis les réponses.

Utilisation :

- `DbAddCommand.run` : `AgentProject.load` → `templates.ensure()` → `flow.collect(flags)` → `flow.apply` → `renderer.render_agent` → `write`.
- `AgentCommand.run` (interactif seulement) : après le premier rendu, `while ui.confirm("Add a database?", default=True)` : `flow.collect({})` → `flow.apply` → rendu + écriture. Rendu après chaque ajout : un Ctrl-C au milieu laisse un état cohérent sur disque.

`flows/` vit dans `commands/` parce qu'il prompte via `ui` ; il ne fait aucune I/O fichier (c'est `RenderResult.write` qui écrit).

## 5. État, templates, rendu

### 5.1 Modèle de données (`services/project.py`)

Objets en mémoire construits depuis le disque, jamais persistés tels quels.

```python
@dataclass(frozen=True)
class DatabaseSpec:
    id: str; engine: str; name: str; managed: bool
    host: str | None; port: int | None; database: str | None
    username: str | None; password: str | None
    path: str | None          # sqlite
    volume: str | None; container: str | None   # docker-volume
    options: dict

    @classmethod
    def from_json(cls, raw: dict, env: EnvFile) -> "DatabaseSpec": ...
    def to_json(self) -> dict: ...          # format databases.json actuel, inchangé
    @property
    def env_prefix(self) -> str: ...        # "db-pg-a1f2" → "DB_PG_A1F2"


@dataclass
class AgentProject:
    path: Path; env: EnvFile; databases: list[DatabaseSpec]; host_gateway: bool

    @property
    def needs_docker_socket(self) -> bool   # une entrée docker-volume
    @property
    def managed(self) -> list[DatabaseSpec]
    @property
    def sqlite_mounts(self) -> list[tuple[str, str]]   # database commence par /config/ → ./x:/config/x


@dataclass
class DashboardProject:
    path: Path; env: EnvFile
    @property
    def db_mode(self) -> Literal["external", "custom", "internal"]
        # POSTGRES_HOST absent → internal ; == "db" → external ; sinon custom
```

Détection `managed` : `.env` contient `{PREFIX}_PORT` pour ce `host` (toutes les bases `new` l'écrivent, aucune `existing`). Si l'agent tolère les clés inconnues dans `databases.json`, une clé explicite `managed: true` sera ajoutée et la détection deviendra le fallback — à vérifier côté agent.

Cas limites :

- `host` managé sans `{PREFIX}_PORT` dans `.env` → `ui.warning`, la base est traitée comme externe.
- Deux entrées avec le même `host` → `ConfigError` avant tout rendu.
- `.env` ou `databases.json` absent → `ConfigError("Not a Portabase agent folder")`.

### 5.2 `EnvFile` (`services/envfile.py`)

Remplace `write_env_file`. Parse `KEY="v"`, `KEY='v'`, `KEY=v`, `export KEY=`, commentaires, lignes vides. Conserve l'ordre et les commentaires (liste de lignes typées). `merge()` met à jour en place et ajoute en fin ; `remove(prefix)` retire les `PREFIX_*`. Écriture toujours quotée `"…"`, `"` et `\` échappés. Sauvegarde atomique (tmp + `os.replace`).

`.env` ne contient que des variables consommées par les conteneurs. Aucune métadonnée CLI.

### 5.3 `ComposeFacts` (`services/compose_facts.py`)

`yaml.safe_load` du compose existant, lecture seule, jamais réécrit. Expose `host_gateway` (présence de `extra_hosts` sur `services.agent`, forme liste ou dict tolérée). Compose absent ou invalide → valeurs par défaut + `ui.warning`, jamais d'erreur.

### 5.4 `TemplateRepository` (`services/templates.py`)

- URL : `{TEMPLATE_BASE_URL}/{version}/manifest.json` puis fichiers listés.
- Résolution de version : `current_version()` ; sinon `PORTABASE_TEMPLATES_VERSION` ; sinon `PORTABASE_TEMPLATES_DIR` (court-circuite S3) ; sinon `TemplateError`. En dev non-frozen, `./templates` à côté de `main.py` est utilisé automatiquement s'il existe.
- Cache `~/.portabase/cache/templates/<version>/`. Séquence `ensure()` : GET manifest (10 s) → pour chaque fichier, sha256 identique en cache → skip, sinon GET + vérification sha256 et taille → écriture. Fichiers en cache absents du manifest supprimés. Manifest injoignable avec cache complet → warning et cache ; sans cache → `TemplateError` avec hint.
- Jinja2 : `Environment(undefined=StrictUndefined, keep_trailing_newline=True, autoescape=False)`. `{{ }}` ne collisionne pas avec `${}` Compose.

Manifest :

```json
{
  "schema": 1,
  "version": "26.09.0",
  "generated_at": "2026-09-11T14:02:17Z",
  "commit": "858d4926…",
  "files": {
    "agent.yml.j2":              { "sha256": "…", "size": 612 },
    "engines/postgresql.yml.j2": { "sha256": "…", "size": 498 }
  },
  "engines": {
    "postgresql": "engines/postgresql.yml.j2",
    "postgresql-cluster": "engines/postgresql.yml.j2"
  }
}
```

`schema` inconnu → `TemplateError`. `version` ≠ version demandée → `TemplateError`. `engines` sert à `engines-check` en CI et à `get_engine(key)`.

### 5.5 `ComposeRenderer` (`services/renderer.py`)

```python
class ComposeRenderer:
    def __init__(self, templates: TemplateRepository, engines: EngineRegistry): ...
    def render_agent(self, project: AgentProject, inline: bool = False) -> RenderResult: ...
    def render_dashboard(self, project: DashboardProject, inline: bool = False) -> RenderResult: ...
```

Contexte `agent.yml.j2` : `host_gateway`, `docker_socket`, `mounts` (sqlite), `services` (liste de `{name, volume, body}` où `body` est le rendu du template moteur). Le renderer passe aux templates moteurs des variables **déjà formées** (`port_var = "${DB_PG_A1F2_PORT}"` ou valeur littérale si `inline`) : la logique de nommage reste en Python, les templates restent lisibles.

`RenderResult` : `compose: str`, `databases: list[dict]`. `write(path)` valide d'abord (`yaml.safe_load` du compose → sinon `TemplateError`, un template remote cassé ne corrompt jamais une install), puis écrit `docker-compose.yml` et `databases.json` atomiquement. Le compose porte un en-tête `# Generated by Portabase CLI <version>. Do not edit — use docker-compose.override.yml.`

Ordre dans une commande mutante : collecte → `templates.ensure()` → mutation `.env`/`databases.json` en mémoire → rendu → validation → écriture. Le manifest est vérifié avant toute mutation.

### 5.6 Templates

`agent.yml.j2` :

```jinja
services:
  agent:
    restart: unless-stopped
    image: portabase/agent:latest
    volumes:
      - ./databases.json:/config/config.json
{%- for m in mounts %}
      - {{ m.host }}:{{ m.container }}
{%- endfor %}
{%- if docker_socket %}
      - /var/run/docker.sock:/var/run/docker.sock
{%- endif %}
{%- if host_gateway %}
    extra_hosts:
      - "localhost:host-gateway"
{%- endif %}
    environment:
      TZ: "${TZ}"
      EDGE_KEY: "${EDGE_KEY}"
      LOG_LEVEL: "${LOG_LEVEL}"
      POLLING: "${POLLING}"
    networks:
      - portabase
{% for s in services %}
{{ s.body }}
{%- endfor %}
{% if services %}
volumes:
{%- for s in services %}
  {{ s.volume }}:
{%- endfor %}
{% endif %}
networks:
  portabase:
    name: portabase_network
    external: true
```

Templates moteurs : un par moteur, variante auth par `{% if auth %}` (10 snippets actuels → 8 templates ; `postgresql-cluster` réutilise `postgresql.yml.j2`). `dashboard.yml.j2` : `{% if db_mode == "external" %}` autour du service `db`, de `depends_on` et du volume — remplace les trois `re.sub` de `dashboard.py`.

### 5.7 Installs legacy

Aucun marqueur de version nécessaire. `AgentProject.load()` fonctionne sur toute install (`.env` + `databases.json` existent déjà). Au premier `RenderResult.write()` sur un compose sans l'en-tête `# Generated by Portabase CLI`, le fichier est copié en `docker-compose.legacy.yml` et un avertissement est affiché. `portabase build PATH --diff` permet de voir le diff avant. Les commandes `start/stop/logs` ne déclenchent rien.

Différences attendues au premier rendu d'une install ancienne : `restart: unless-stopped` ajouté sur redis/valkey (absent des snippets actuels) ; à mentionner dans le changelog rc.

## 6. Moteurs DB (`engines/`)

```python
@dataclass(frozen=True)
class Field:
    name: str; prompt: str
    kind: Literal["text", "int", "secret", "bool", "choice"]
    default: Any = None; choices: tuple[str, ...] = (); help: str | None = None
    validator: Callable[[Any], Any] | None = None


class DbEngine(ABC):
    key: str; display: str; default_port: int
    template: str | None            # None = aucun service Compose (sqlite, docker-volume, existing)
    auth_variants: bool = False
    warning: str | None = None

    def fields_existing(self) -> list[Field]: ...   # défaut : host, port, database, username, password
    def fields_new(self) -> list[Field]: ...        # défaut : [] (tout généré)
    def option_fields(self) -> list[Field]: ...     # défaut : []
    def generate(self, service: str, auth: bool, ports: PortAllocator) -> DatabaseSpec: ...
    def env_vars(self, spec: DatabaseSpec) -> dict[str, str]: ...
    def template_ctx(self, spec: DatabaseSpec, inline: bool) -> dict: ...
    def agent_entry(self, spec: DatabaseSpec) -> dict: ...   # projection databases.json
    def agent_database(self, spec: DatabaseSpec) -> str: ... # défaut : spec.database ; hook pour "0", chemin…
```

Hiérarchie : `StandardSqlEngine` (postgresql, postgresql-cluster, mysql, mariadb, mssql, firebird), `RedisEngine`, `ValkeyEngine`, `MongoEngine`, `SqliteEngine`, `DockerVolumeEngine`. Redis et Valkey sont deux classes indépendantes dans deux fichiers, sans base commune (images, commandes et healthchecks divergent ; ce qu'elles partagent — `agent_database = "0"`, `auth_variants` — passe par les hooks de `DbEngine`). Les sous-classes ne surchargent que leurs particularités :

| Moteur | Particularité |
|---|---|
| postgresql | `option_fields` : `keep_ownership` (bool, défaut False), `clean_mode` (choice clean/none/drop_schemas/drop_database, défaut clean) |
| postgresql-cluster | `warning` superuser ; pas d'options |
| firebird | `agent_entry.name = "mirror.fdb"` ; var `_ROOT_PASS` |
| mssql | `agent_entry.username = "sa"` |
| redis | `agent_database = "0"` ; `auth_variants = True` ; no-auth → `_PORT` seul |
| valkey | idem redis, classe et template distincts |
| mongodb | `auth_variants = True` |
| sqlite | `fields_new` : nom de fichier ; `fields_existing` : chemin ; pas de template ; mount si chemin relatif |
| docker-volume | `fields` : volume, container (optionnel), label ; `warning` socket ; pas de template |

`EngineRegistry` : dict `key → instance`, imports explicites (compatible PyInstaller). `get(key)` inconnu → `ValidationError` avec la liste des clés.

### 6.1 Options moteur

Certains moteurs exposent des options que l'agent lit dans `databases.json` (`options` : aujourd'hui `keep_ownership` et `clean_mode` pour PostgreSQL). Le système doit accepter de nouvelles options sans toucher à la signature Typer.

- Déclaration : `DbEngine.option_fields() -> list[Field]`. Un `Field` comme les autres : nom, prompt, type, défaut, choix, validateur.
- Saisie non-interactive : flag générique répétable `-o KEY=VALUE` / `--option KEY=VALUE` sur `db add`. Parsé en `dict[str, str]`, converti selon `Field.kind` (`bool` : `true/false/1/0/yes/no`, `int`, `choice` validé contre `choices`). Clé inconnue pour ce moteur → `ValidationError` listant les options valides.
- Saisie interactive : `Form.collect(engine.option_fields(), values["options"])`, un prompt par option non fournie, avec le texte d'aide actuel (par exemple l'explication de `--no-owner` / `pg_restore --clean`) porté par `Field.help`.
- Stockage : `DatabaseSpec.options: dict` (valeurs typées).
- Projection : `agent_entry()` n'écrit dans `options` que les valeurs différentes du défaut. Comportement actuel conservé : `keep_ownership` absent si False, `clean_mode` absent si `clean`. Aucune clé `options` si vide.
- Affichage : `db list` montre les options non-défaut ; `Summary` les inclut lors de l'ajout.

Ajouter une option = une ligne dans `option_fields()` du moteur concerné.

## 7. `ui/`

### 7.1 Principes

- Tokens uniques (`ui/theme.py`) : `PALETTE` → `RICH_THEME` et `QUESTIONARY_STYLE`.
- Composants stateless, un par fichier, `Component(console)`.
- Façade `UI` : seule chose importée par `commands/`. Rich et questionary ne sont jamais importés hors de `ui/`.
- Le markup Rich est autorisé dans les arguments texte (`ui.success("Added [bold]x[/bold]")`).
- `NO_COLOR` / `--no-color` → `Console(no_color=True)`, style questionary vide.
- Jamais de prompt à l'intérieur d'un `ui.status()` (structurellement garanti : les services ne promptent pas).

### 7.2 Composants

| Composant | Remplace |
|---|---|
| `Banner` | `print_banner` |
| `Message` (`success/info/warning/error`) | ~60 `console.print("[success]✔ …")` |
| `Section` | `Panel("[bold]Database Setup[/bold]")` |
| `Summary` (masque auto des clés `password/secret/key`) | `Table(show_header=False)` de dashboard |
| `DataTable` | `Table` de `db list` |
| `Status` (context manager, hint injecté) | `console.status(msg + hint)` |
| `Hint` | `get_random_hint` |
| `Diff` | nouveau, pour `build --diff` |
| `Prompt` (`text/integer/secret/confirm/select/path`) | `rich.prompt.*`, `questionary.*` épars |

Règle anti-dérive : un composant n'existe que s'il a un appelant. L'inventaire ci-dessus est un plafond.

### 7.3 `Form`

```python
class Form:
    def ask(self, field: Field, value: Any | None) -> Any:
        # 1. valeur du flag → validée
        # 2. non-interactif : défaut, sinon ValidationError("Missing --<flag>")
        # 3. interactif : prompt selon field.kind (dispatch dict), None (Ctrl-C) → UserAbort
        #    validation en boucle jusqu'à valeur acceptée
    def collect(self, fields: list[Field], values: dict) -> dict: ...
    def text(...), integer(...), confirm(...), choice(...)   # raccourcis
```

`non_interactive` résolu une fois dans `main.py`. `ui.confirm()` en non-interactif renvoie le défaut ; les confirmations destructives ont `default=False` et un flag `--force`.

## 8. Erreurs, télémétrie, updater

### 8.1 Hiérarchie (`core/errors.py`)

| Classe | `code` | exit |
|---|---|---|
| `PortabaseError` | `E_GENERIC` | 1 |
| `UserAbort` | `E_ABORT` | 130 |
| `ValidationError` | `E_VALIDATION` | 2 |
| `ConfigError` | `E_CONFIG` | 3 |
| `DockerError` | `E_DOCKER` | 4 |
| `TemplateError` | `E_TEMPLATE` | 5 |
| `NetworkError` | `E_NETWORK` | 6 |
| `UpdateError` | `E_UPDATE` | 7 |

Constructeur : `(message, *, hint=None, cause=None)`. Les exceptions tierces (`requests`, `subprocess`, `yaml`, `jinja2`) sont wrappées à la frontière du service. `typer.Exit` n'est plus levé hors de `main.py`. Ruff : `E722`, `BLE001`, `S110`, `TID251`.

### 8.2 Catcher (`main.py`)

`app(standalone_mode=False)` dans un seul `try` : `UserAbort` → "Cancelled." exit 130 ; `PortabaseError` → `ui.error(e)` (message, hint, code ; `--verbose` ajoute cause et traceback), `telemetry.error(e)`, exit `e.exit_code` ; `click.UsageError` → mappé en `ValidationError` ; `KeyboardInterrupt` → exit 130 ; `Exception` → "Unexpected error", télémétrie `unexpected=True`, exit 1. `finally: telemetry.flush()`.

### 8.3 Télémétrie (`services/telemetry.py`)

```python
class Telemetry(ABC):
    def session(self, **attrs) -> ContextManager     # span racine par invocation
    def span(self, name: str, **attrs) -> ContextManager
    def event(self, name: str, **attrs) -> None
    def error(self, exc: Exception, unexpected: bool = False) -> None
    def flush(self) -> None
```

Implémentations : `NoopTelemetry` (défaut), `ConsoleTelemetry` (`--debug`, stderr), `OtelTelemetry` (futur, import lazy, construit seulement si `telemetry=true` et `telemetry_endpoint` défini). Spans : `Command.run`, `TemplateRepository.ensure`, `ComposeRenderer.render`, `DockerRunner.compose`. Attributs : commande, moteur, mode, durée, code de sortie, `error.code`, version CLI, OS. Jamais : nom d'agent, chemin, clé, credentials, contenu de fichier.

Opt-in : `portabase config set telemetry true` ou `PORTABASE_TELEMETRY=1`. Une ligne d'information à la première exécution, aucun prompt.

### 8.4 Updater (`services/updater.py`)

`UpdateChecker.notify(ui)` appelé après la commande, cache 24 h (`~/.portabase/cache/release.json`), silencieux si hors ligne, `--stdout` ou non-interactif. `Updater.apply()` vérifie le sha256 via `checksums.txt` de la release avant remplacement du binaire. Canal `beta` conservé.

## 9. CI, sécurité, release

### 9.1 `ci.yml` (`pull_request`, `push: main`)

| Job | Contenu |
|---|---|
| `lint` | `ruff check`, `ruff format --check` |
| `render-check` | `scripts/render_check.py` : rend `agent.yml.j2` (0 base, chaque moteur auth/no-auth, socket, host_gateway, mounts sqlite) et `dashboard.yml.j2` × 3 modes via le vrai `ComposeRenderer` (`PORTABASE_TEMPLATES_DIR=./templates`), puis `yaml.safe_load` et `docker compose config` avec `.env` fixture |
| `engines-check` | chaque `DbEngine.template` existe dans `templates/`, chaque template a un moteur, `engines.map.json` cohérent |
| `gitleaks` | action pinnée ; `.gitleaks.toml` allowlist `templates/**` et `HINTS` |
| `plumber` | action drop-in, `verify-attestation: true` |
| `build-smoke` | PyInstaller linux/amd64, `./dist/portabase --version`, `agent smoke --key <fixture> --non-interactive` avec templates locaux |
| `test` | `pytest` — vide, réservé à la spec tests |

### 9.2 Durcissement

- Toutes les actions pinnées par SHA avec commentaire de version ; Dependabot `github-actions` et `uv` hebdomadaires.
- `permissions: {}` au top de chaque workflow, permissions explicites par job. `packages: write` retiré (inutilisé).
- `templates-upload.yml` : plus de `~/.s3cfg` par heredoc ; credentials par variables d'environnement.
- `actions/attest-build-provenance` sur les binaires.

### 9.3 Release

`bump.yml` (`workflow_dispatch`, inputs `version`, `channel: stable|rc`) : validation regex, `stable` uniquement depuis `main`, `sed` `pyproject.toml` + `CITATION.cff`, commit `chore(release): X`, tag, push. Les workflows sur tag restent inchangés. `./release` supprimé. Pas de release-please (historique non conventional). Si `main` exige une PR, le workflow ouvre une PR au lieu de pousser — à régler selon la protection de branche.

`templates-hotfix.yml` (`workflow_dispatch`, input `version`) : re-sync `templates/` vers `templates/<version>/` et régénère le manifest. Réservé aux corrections compatibles avec le code de cette version.

`templates-upload.yml` : source `templates/`, génération de `manifest.json` (sha256, taille, version, commit, date, mapping moteurs depuis `engines.map.json`) avant `s3cmd sync`.

### 9.4 `pyproject.toml`

```toml
dependencies = ["typer", "rich", "questionary", "requests", "pyyaml", "jinja2"]
[dependency-groups]
dev = ["pyinstaller", "ruff", "pytest"]
```

## 10. Ordre des chantiers

Graphe de dépendances, pas un calendrier.

```
[A] Hygiène CI ─────────────────────────────────────────────┐  indépendant
    ci.yml, pin SHA, permissions, bump.yml, pyproject       │
                                                            │
[B] Fondations                                              │
    core/errors, ui/, services/{envfile,docker,http,ports}, │
    main.py catcher, Command ABC                            │
        │                                                   │
        ├──► [C] Lifecycle en POO (start/stop/…/config/update)
        │        (ancien code agent/db/dashboard via LegacyCommand)
        │
        └──► [D] Templates .j2 + TemplateRepository + engines/ + render-check
                  │
                  ▼
             [E] Rendu : project, compose_facts, renderer, build
                  │
                  ▼
             [F] agent / dashboard / db réécrits, ancien code supprimé
                  │
                  ▼
             [G] OTel réel, --json, spec tests
```

Contraintes :

- B avant tout code métier.
- D avant E (le renderer se construit contre des templates réels).
- E avant F.
- C et F ne touchent pas les mêmes fichiers ; C peut aller avant ou après D/E.
- A avant F de préférence : `render-check` et `build-smoke` sont le seul filet avant la spec tests.

Points de livraison :

| Après | État | Canal |
|---|---|---|
| A | fonctionnellement identique, CI verte | stable |
| B + C | lifecycle en POO, ui/ et erreurs neuves ; `agent`/`db`/`dashboard` = ancien code via `LegacyCommand` | stable |
| D | templates `.j2` uploadés sous la nouvelle version ; l'ancien code lit `agent.yml`, coexistence sur S3 | rc |
| E + F | bascule complète | rc obligatoire, puis stable |

Risques et parades :

| Étape | Risque | Parade |
|---|---|---|
| A | mauvais SHA casse un workflow | tag rc jetable |
| B | sur-conception de `ui/` | un composant = un appelant |
| D | template `.j2` diverge d'un snippet actuel | diff manuel des rendus contre l'ancien CLI, une fois |
| E | `ComposeFacts` lit mal un vieux compose | tolérance, warning, jamais de crash |
| F | install legacy cassée après `db add` | `.legacy.yml`, `build --diff`, changelog rc |
| F | mots de passe existants avec `$` | ne pas régénérer ; correction pour les nouvelles bases seulement |

## 11. Questions ouvertes

- L'agent tolère-t-il des clés inconnues dans `databases.json` ? Si oui : clé `managed: true` explicite.
- Protection de la branche `main` : `bump.yml` pousse directement ou ouvre une PR ?
- Garder la clé `engines` dans le manifest (double source de vérité avec le code) ou s'en tenir au registre Python ?
