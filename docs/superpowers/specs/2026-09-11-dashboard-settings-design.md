# Dashboard settings and authentication — Design

Date : 2026-09-11
Dépend de : `2026-09-11-cli-refactor-design.md` (état déclaratif, `EnvFile`, `Field`, `Form`, `CommandGroup`).

## 1. Objectif

Configurer depuis le CLI ce que le dashboard lit dans son environnement : API et MCP, onboarding, authentification par mot de passe, providers OIDC et OAuth2. À la création et après coup, en interactif et par flags.

Au passage, une rupture de surface décidée pour être cohérente : un namespace par composant.

## 2. Surface CLI

### 2.1 Avant / après

| Avant | Après |
|---|---|
| `agent NAME` | `agent create NAME` |
| `db add\|remove\|list NAME` | `agent db add\|remove\|list NAME` |
| `dashboard NAME` | `dashboard create NAME` |
| — | `dashboard show NAME` |
| — | `dashboard set NAME KEY VALUE [KEY VALUE…]` |
| — | `dashboard auth add\|remove\|list NAME` |
| `start\|stop\|restart\|logs\|uninstall\|build PATH` | inchangés |
| `config`, `update`, `decrypt` | inchangés |

Un groupe Typer ne peut pas porter à la fois un argument positionnel et des sous-commandes (vérifié : `dashboard auth` créerait un dashboard nommé `auth`). D'où `create`.

### 2.2 Compatibilité

- `db` reste à la racine **une version**, alias de `agent db`, avec un avertissement à chaque appel : `'portabase db' is deprecated, use 'portabase agent db'`. Retiré à la version suivante.
- `portabase agent my-agent` et `portabase dashboard my-dash` produisent une `UsageError` « No such command ». Le catcher de `main.py` la reconnaît (token précédent = `agent` ou `dashboard`) et ajoute le hint `Did you mean: portabase agent create my-agent?`.
- README, `CONTRIBUTING.md`, doc portabase.io et script d'installation à mettre à jour dans la même release.

### 2.3 Implémentation

`CommandGroup` gagne `groups: list[CommandGroup]` pour imbriquer (`agent` contient `db`). `AgentCommand` devient `AgentCreateCommand` dans un `AgentCommands(CommandGroup)` ; idem `DashboardCreateCommand` dans `DashboardCommands`.

## 3. Registre de settings

Le cœur : une liste déclarative, un endroit à toucher pour ajouter un réglage.

```python
@dataclass(frozen=True)
class Setting:
    field: Field          # name, prompt, kind, default, choices, help, validator
    env: str              # variable écrite dans .env
    section: str          # "network" | "api" | "onboarding" | "auth"
    secret: bool = False  # jamais en flag visible sans avertissement, masqué à l'affichage
```

`services/dashboard_settings.py` :

| Section | `field.name` | `env` | kind | défaut dashboard |
|---|---|---|---|---|
| network | `url` | `PROJECT_URL` | text | `http://localhost:<port>` |
| network | `behind_proxy` | `TUSD_BEHIND_PROXY` | bool | false |
| network | `trusted_domains` | `TRUSTED_DOMAINS` | text | — |
| api | `api` | `API_ENABLED` | bool | false |
| api | `openapi` | `OPENAPI_ENABLED` | bool | false |
| api | `mcp` | `MCP_ENABLED` | bool | false |
| onboarding | `skip_onboarding` | `SKIP_ONBOARDING` | bool | false |
| onboarding | `admin_name` | `AUTH_DEFAULT_USER_NAME` | text | — |
| onboarding | `admin_email` | `AUTH_DEFAULT_USER` | text | — |
| onboarding | `admin_password` | `AUTH_DEFAULT_PASSWORD` | secret | — |
| auth | `password_auth` | `AUTH_EMAIL_PASSWORD_ENABLED` | bool | true |
| auth | `signup` | `AUTH_SIGNUP_ENABLED` | bool | — |
| auth | `passkey` | `AUTH_PASSKEY_ENABLED` | bool | — |
| auth | `account_linking` | `AUTH_ALLOW_LINKING` | bool | — |
| auth | `account_unlinking` | `AUTH_ALLOW_UNLINKING` | bool | — |
| auth | `sync_oidc_roles` | `AUTH_SYNC_OIDC_ROLES_ON_LOGIN` | bool | — |
| auth | `role_map` | `AUTH_ROLE_MAP` | text | — |
| auth | `allowed_group` | `ALLOWED_GROUP` | text | — |

Ce que le registre produit, sans code par réglage :

- les flags de `dashboard create` : `--api/--no-api` pour un bool, `--url` pour un texte, `--admin-password-stdin` pour un secret ;
- les prompts interactifs, groupés par section ;
- la validation de `dashboard set` : `KEY` doit être un `field.name` du registre, `VALUE` est coercé par `Form` (bool `true/false/yes/no/1/0`, choix, validateur) ;
- l'affichage de `dashboard show`, section par section, secrets masqués.

Écriture dans `.env` : booléens en `true`/`false`. À la création, seuls les réglages fournis ou différents du défaut sont écrits (le `.env` reste lisible). `set` écrit toujours la valeur demandée.

`admin_password` porte le validateur documenté : 8 caractères, majuscule, minuscule, chiffre, spécial.

## 4. Providers d'authentification

Répétables, donc en sous-commande, comme `agent db`.

### 4.1 Modèle

```python
@dataclass(frozen=True)
class AuthProvider:
    kind: Literal["oidc", "oauth"]
    id: str                  # providerId : "keycloak", "github"
    values: dict[str, str]   # champs → valeurs, sans le préfixe
```

Stockage dans `.env` par préfixe, ce qui est exactement le mécanisme des bases managées :

| kind | préfixe | champs |
|---|---|---|
| oidc | `AUTH_OIDC_<ID>_` | `ID`, `TITLE`, `DESC`, `ICON`, `ISSUER_URL`, `CLIENT`, `SECRET`, `SCOPES`, `PKCE`, `HOST` |
| oauth | `AUTH_SOCIAL_<PROVIDER>_` | `CLIENT`, `SECRET`, `TITLE` |

`<ID>` est l'identifiant en majuscules avec `-` → `_` ; `AUTH_OIDC_<ID>_ID` reçoit l'identifiant tel que saisi (c'est le `providerId` du callback). Les providers OAuth sont limités aux noms connus du dashboard : `google`, `github`, `discord`, `apple`, `linkedin`, `x`, `reddit`.

Lecture : `DashboardProject.providers` scanne les clés du `.env` par préfixe et reconstruit la liste. Aucun autre état.

### 4.2 Commandes

```
dashboard auth add NAME oidc ID --issuer URL --client CLIENT (--secret S | --secret-stdin)
                                [--title T] [--scopes "openid profile email"] [--pkce] [--host H]
dashboard auth add NAME oauth PROVIDER --client CLIENT (--secret S | --secret-stdin) [--title T]
dashboard auth list NAME
dashboard auth remove NAME ID [--yes]
```

- `add` sur un `ID` existant → `ValidationError`, hint « remove it first ».
- `remove` fait `env.remove_prefix(...)` puis re-rend.
- `list` affiche kind, id, titre, issuer/provider, et le callback à déclarer chez le fournisseur : `<PROJECT_URL>/api/auth/sso/callback/<id>`.
- `--secret` visible accepté avec avertissement, `--secret-stdin` recommandé — même règle que `agent db add`.

En interactif, `add` sans flags pose les champs du kind via `Form`.

## 5. Validations croisées

Dans `DashboardProject.validate()`, appelé avant toute écriture. Ce sont des refus, pas des avertissements : chacune laisse une instance inaccessible.

| Condition | Erreur |
|---|---|
| `skip_onboarding` sans `admin_email` **et** `admin_password` | « Skipping onboarding needs an initial account: set admin_email and admin_password. » |
| `password_auth = false` et aucun provider | « Disabling password login with no OIDC or OAuth provider would lock everyone out. » |
| au moins un provider et `url` sur `localhost` | « Providers need a public URL for their callback; set url (currently http://localhost:8887). » |
| `auth remove` du dernier provider alors que `password_auth = false` | même refus que la ligne 2 |

`admin_password` faible → refus par le validateur du champ.

## 6. Interactif — `dashboard create`

Le flux actuel reste : port, mode base, timezone, résumé, confirmation. Entre le résumé et la confirmation, une question :

```
Configure API, MCP and authentication now? [y/N]
```

Non par défaut. Si oui, trois sections courtes, chacune précédée de `ui.section(...)` :

1. **API** — `api`, `openapi`, `mcp`
2. **Onboarding** — `skip_onboarding` ; si oui, `admin_name`, `admin_email`, `admin_password` (masqué)
3. **Authentication** — `password_auth`, `signup`, `passkey`

Les providers ne sont pas dans le wizard : hint `Add a login provider with: portabase dashboard auth add NAME oidc …`, comme `agent create` renvoie vers `db add`.

Le résumé inclut les réglages non-défaut. `--yes` saute la confirmation, `--non-interactive` prend les défauts et ne pose pas la question des sections.

## 7. Application des changements

Toute commande mutante (`create`, `set`, `auth add`, `auth remove`) termine par `project.save_state()` puis `renderer.render_dashboard(project).write(path)`. Le template a `env_file: .env`, donc le compose ne change pas — mais `write` est appelé quand même pour garder un seul chemin.

Puis le message : `Apply with: portabase start NAME`.

**`restart` est corrigé dans cette spec** : `docker compose restart` ne relit pas `env_file` ni ne crée un service ajouté (bug déjà constaté sur `agent db add`). `RestartCommand` fait `up -d` puis `restart`, pour converger vers l'état déclaré. Le message des commandes mutantes peut alors dire `portabase restart NAME` sans mentir.

## 8. Ce qui ne change pas

- `dashboard.yml.j2` : aucune modification, `env_file` suffit.
- `EnvFile`, `Form`, `Field`, `Summary`, `render_dashboard` : réutilisés tels quels.
- Le mode `custom`/`external`/`internal` de la base : inchangé.

## 9. Hors périmètre

- SMTP (`SMTP_*`), `RETENTION_CRON`, `STALE_BACKUP_THRESHOLD_HOURS`, `BACKUP_FOLDER_NAME`, `TELEMETRY` du dashboard. Le registre les accepte en une ligne chacun le jour venu.
- Provider OAuth2 générique (endpoints libres) : le dashboard ne le documente pas.
- Un `agent set` : l'agent n'a que `TZ`, `POLLING`, `LOG_LEVEL` ; à ajouter si le besoin apparaît, avec le même registre.
- Tests automatisés : spec séparée. Vérification ici par `render_check` et les parcours non-interactifs.

## 10. Fichiers

| Fichier | Action |
|---|---|
| `commands/base.py` | `CommandGroup.groups` pour l'imbrication |
| `commands/agent.py` | `AgentCommands` (groupe) + `AgentCreateCommand` ; `db` devient `agent db` |
| `commands/db.py` | inchangé, enregistré sous `agent` ; alias racine déprécié |
| `commands/dashboard.py` | `DashboardCommands` : `create`, `show`, `set` |
| `commands/dashboard_auth.py` | `add`, `list`, `remove` |
| `commands/lifecycle.py` | `RestartCommand` → `up -d` puis `restart` |
| `services/dashboard_settings.py` | `Setting`, `SETTINGS`, `OAUTH_PROVIDERS`, `OIDC_FIELDS` |
| `services/project.py` | `DashboardProject` : `settings`, `providers`, `validate()`, `set()`, `add_provider()`, `remove_provider()` |
| `main.py` | enregistrement des groupes, hint « did you mean » |
| `README.md`, `.github/CONTRIBUTING.md` | nouvelle surface |

## 11. Questions ouvertes

- Le `providerId` OIDC : imposer le même que `<ID>` en minuscules, ou le laisser libre via `--id` ? Défaut retenu : identique, pas de flag.
- `dashboard set` accepte plusieurs paires en une commande ; faut-il aussi `dashboard unset KEY` pour revenir au défaut du dashboard (retirer la variable) ? Défaut retenu : oui, trivial avec `env.remove`.
