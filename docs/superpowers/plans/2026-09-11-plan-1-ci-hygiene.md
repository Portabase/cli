# Plan 1 — CI, hygiène et release (chantier A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CI de PR bloquante (lint, secrets, sécurité pipeline, build smoke), workflows durcis et pinnés, `./release` remplacé par `bump.yml` — sans changer une ligne de comportement du CLI.

**Architecture:** Un workflow `ci.yml` sur PR/push main avec des jobs indépendants. Les workflows de release existants restent structurellement identiques, seulement pinnés par SHA et restreints en permissions. La configuration ruff vit dans `pyproject.toml` avec des exclusions explicites pour le code legacy qui sera supprimé aux plans 2–4.

**Tech Stack:** GitHub Actions, uv 0.9, ruff 0.16, pytest, PyInstaller 6.17, gitleaks-action v2, getplumber/plumber, Dependabot.

**Spec:** `docs/superpowers/specs/2026-09-11-cli-refactor-design.md` — sections 9 (CI, sécurité, release) et 10 (étape A).

## Global Constraints

- Python `>=3.12` (pyproject actuel). Ne pas changer.
- Aucune modification de comportement du CLI dans ce plan. Seuls `pyproject.toml`, `.gitignore`, `.github/**`, `.gitleaks.toml` et le formatage (`ruff format`) bougent.
- Toutes les `uses:` pinnées par SHA complet + commentaire `# vX.Y.Z`.
- `permissions: {}` au top de chaque workflow ; permissions explicites par job.
- Le job `test` existe mais ne collecte aucun test (réservé à la spec tests).
- Aucun test unitaire dans ce plan (consigne utilisateur). Chaque tâche a des étapes de vérification exécutables.
- Commits en Conventional Commits (`chore`, `ci`, `build`, `style`).
- `gh` n'est pas authentifié sur ce poste : les appels `gh api` sur dépôts publics fonctionnent, `gh` sur `Portabase/cli` (protection de branche, secrets) ne fonctionne pas. Vérifier ces points dans l'interface GitHub.

SHAs résolus le 2026-09-11 (à réutiliser tels quels) :

| Action | Tag | SHA |
|---|---|---|
| actions/checkout | v4 | `11d5960a326750d5838078e36cf38b85af677262` |
| actions/upload-artifact | v4 | `ea165f8d65b6e75b540449e92b4886f43607fa02` |
| actions/download-artifact | v4 | `d3f86a106a0bac45b974a628896c90dbdf5c8093` |
| actions/attest-build-provenance | v2 | `e8998f949152b193b063cb0ec769d69d929409be` |
| astral-sh/setup-uv | v3 | `caf0cab7a618c569241d31dcd442f54681755d39` |
| astral-sh/ruff-action | v3 | `4919ec5cf1f49eff0871dbcea0da843445b837e6` |
| softprops/action-gh-release | v2 | `3bb12739c298aeb8a4eeaf626c5b8d85266b0e65` |
| mikepenz/release-changelog-builder-action | v5 | `c9dc8369bccbc41e0ac887f8fd674f5925d315f7` |
| gitleaks/gitleaks-action | v2 | `ff98106e4c7b2bc287b24eaf42907196329070c7` |
| getplumber/plumber | (doc officielle) | `3feac69e925e9771f8a495f4177af754d568c1ad` |

Pour re-résoudre un SHA : `gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq .object.sha` (si `.object.type == "tag"`, résoudre encore via `repos/<owner>/<repo>/git/tags/<sha> --jq .object.sha`).

---

## File Structure

| Fichier | Action | Responsabilité |
|---|---|---|
| `pyproject.toml` | modifier | deps runtime/dev, config ruff, config pytest |
| `.gitignore` | modifier | retirer `uv.lock` (tracké, requis par `--frozen`) |
| `commands/*.py`, `core/*.py`, `main.py` | reformater seulement | `ruff format` mécanique, aucun changement sémantique |
| `.gitleaks.toml` | créer | allowlist des faux positifs |
| `.github/workflows/ci.yml` | créer | lint, test, gitleaks, plumber, build-smoke |
| `.github/workflows/python.yml` | modifier | pin SHA, permissions, `--frozen`, attestation |
| `.github/workflows/github.yml` | modifier | pin SHA, permissions par job |
| `.github/workflows/templates-upload.yml` | modifier | pin SHA, permissions, s3cmd sans `~/.s3cfg` |
| `.github/workflows/release.yml`, `release-candidate.yml` | modifier | `permissions: {}` top-level, retirer `packages: write` |
| `.github/dependabot.yml` | créer | github-actions + uv hebdo |
| `.github/workflows/bump.yml` | créer | remplace `./release` |
| `release` | supprimer | — |
| `.github/CONTRIBUTING.md` | modifier | procédure de release |

---

### Task 1 : `pyproject.toml` — dépendances, ruff, pytest

**Files:**
- Modify: `pyproject.toml`
- Modify: `.gitignore`

**Interfaces:**
- Produces: commandes `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest` utilisables localement et en CI ; groupe `dev` avec `pyinstaller`, `ruff`, `pytest`.

- [ ] **Step 1: Réécrire `pyproject.toml`**

Remplacer le contenu intégral par :

```toml
[project]
name = "portabase-cli"
version = "26.07.6"
description = "The official command line interface (CLI) for managing and deploying Portabase instances with ease."
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.20.0",
    "rich>=14.2.0",
    "questionary>=2.1.0",
    "requests>=2.32.5",
    "pyyaml>=6.0.3",
]

[dependency-groups]
dev = [
    "pyinstaller>=6.17.0",
    "ruff>=0.16.0",
    "pytest>=8.3",
]

[tool.ruff]
target-version = "py312"
line-length = 88
extend-exclude = [".venv", "build", "dist"]

[tool.ruff.lint]
select = [
    "E", "F", "W",     # pycodestyle / pyflakes
    "I",               # isort
    "UP",              # pyupgrade
    "B",               # bugbear
    "BLE",             # blind except
    "S110",            # try-except-pass
    "E722",            # bare except
    "TID251",          # banned imports (activé au plan 2 : rich.prompt, typer.prompt)
    "SIM",
    "TRY201",
    "PLW1510",         # subprocess.run sans check=
]
ignore = [
    "B008",            # typer.Argument(...) / typer.Option(...) en défaut : idiome Typer
    "E501",            # line length géré par ruff format
]

# Code legacy supprimé aux plans 2-4. Ne pas étendre cette liste : tout nouveau
# fichier doit passer sans exception.
[tool.ruff.lint.per-file-ignores]
"commands/agent.py" = ["BLE001", "E722", "S110", "SIM102"]
"commands/db.py" = ["BLE001", "E722", "S110"]
"commands/dashboard.py" = ["BLE001"]
"commands/common.py" = ["BLE001", "PLW1510"]
"core/config.py" = ["BLE001", "E722", "S110"]
"core/utils.py" = ["BLE001", "E722", "S110", "PLR1730"]
"core/updater.py" = ["BLE001", "TRY201"]
"core/network.py" = ["BLE001"]

[tool.ruff.lint.isort]
known-first-party = ["commands", "core", "templates"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Retirer `uv.lock` de `.gitignore`**

`.gitignore` devient :

```
dist/
build/
.venv/
__pycache__/
*.spec
```

- [ ] **Step 3: Régénérer le lock et synchroniser**

Run: `uv lock && uv sync --all-groups`
Expected: `uv.lock` mis à jour (pyinstaller passe en groupe dev, ruff et pytest ajoutés), `.venv` contient `ruff` et `pytest`.

- [ ] **Step 4: Vérifier que le CLI démarre toujours**

Run: `uv run python main.py --version`
Expected: `Portabase CLI version: 26.07.6` (plus éventuel message de mise à jour).

- [ ] **Step 5: Vérifier le lint**

Run: `uv run ruff check .`
Expected: `All checks passed!`. Si des erreurs subsistent, ajuster **uniquement** `per-file-ignores` pour les fichiers legacy listés ; ne pas modifier le code Python.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .gitignore
git commit -m "build: move pyinstaller to dev group, add ruff and pytest config

Legacy files get per-file-ignores for bare/blind excepts; those files are
rewritten in later plans and the ignores are removed with them."
```

---

### Task 2 : Formatage mécanique

**Files:**
- Modify: tous les fichiers signalés par `ruff format --check` (5 fichiers au 2026-09-11)

**Interfaces:**
- Produces: `uv run ruff format --check .` passe.

- [ ] **Step 1: Lister les fichiers à reformater**

Run: `uv run ruff format --check .`
Expected: `5 files would be reformatted, 17 files already formatted` (nombres indicatifs).

- [ ] **Step 2: Appliquer**

Run: `uv run ruff format .`

- [ ] **Step 3: Vérifier que rien de sémantique n'a changé**

Run: `git diff --stat && uv run python main.py --help`
Expected: diff uniquement sur espaces/quotes/retours à la ligne ; `--help` affiche les commandes `agent`, `dashboard`, `start`, `stop`, `restart`, `logs`, `uninstall`, `db`, `config`, `update`.

- [ ] **Step 4: Vérifier lint + format ensemble**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: les deux passent.

- [ ] **Step 5: Commit**

```bash
git add -A commands core main.py
git commit -m "style: apply ruff format"
```

---

### Task 3 : `.gitleaks.toml`

**Files:**
- Create: `.gitleaks.toml`

**Interfaces:**
- Produces: config lue par `gitleaks/gitleaks-action` (Task 4) et par `gitleaks detect` en local.

- [ ] **Step 1: Créer le fichier**

```toml
# Gitleaks configuration for Portabase CLI.
# Extends the default ruleset; only adds allowlists for known false positives.

title = "portabase-cli"

[extend]
useDefault = true

[allowlist]
description = "Known false positives"
paths = [
  # Compose templates contain PASSWORD=${...} placeholders, never real secrets.
  '''templates/.*''',
  '''\.github/assets/templates/.*''',
  # Lock file: hashes only.
  '''uv\.lock''',
]
regexes = [
  # Compose interpolation placeholders.
  '''\$\{[A-Z0-9_]+\}''',
  # Test/fixture edge keys are base64 JSON with these field names, not credentials.
  '''"masterKeyB64"''',
]
```

- [ ] **Step 2: Scanner l'historique en local**

Run: `uvx --from gitleaks gitleaks detect --source . --config .gitleaks.toml --redact --no-banner || docker run --rm -v "$PWD:/repo" -w /repo ghcr.io/gitleaks/gitleaks:v8 detect --source . --config .gitleaks.toml --redact --no-banner`

(Le binaire gitleaks n'est pas distribué via PyPI ; la première commande échouera, la seconde via Docker fonctionne. Si aucun des deux n'est disponible, passer : la CI fera le scan à la Task 4.)

Expected: `no leaks found`. Si des fuites réelles sont trouvées dans l'historique : **s'arrêter et le signaler** — ne pas allowlister, ne pas réécrire l'historique sans décision explicite.

- [ ] **Step 3: Commit**

```bash
git add .gitleaks.toml
git commit -m "ci: add gitleaks config with template placeholder allowlist"
```

---

### Task 4 : `ci.yml` — lint, test, gitleaks, plumber, build-smoke

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: config ruff/pytest de Task 1, `.gitleaks.toml` de Task 3.
- Produces: check requis `CI / lint`, `CI / test`, `CI / gitleaks`, `CI / plumber`, `CI / build-smoke` sur chaque PR. Le job `build-smoke` sera enrichi au Plan 4 (invocation `agent --non-interactive`).

- [ ] **Step 1: Créer le workflow**

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

permissions: {}

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    name: lint
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - uses: astral-sh/setup-uv@caf0cab7a618c569241d31dcd442f54681755d39 # v3
      - name: Install
        run: uv sync --frozen --all-groups
      - name: Ruff check
        run: uv run ruff check . --output-format=github
      - name: Ruff format
        run: uv run ruff format --check .

  test:
    name: test
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - uses: astral-sh/setup-uv@caf0cab7a618c569241d31dcd442f54681755d39 # v3
      - name: Install
        run: uv sync --frozen --all-groups
      - name: Pytest
        # Exit code 5 = no tests collected. Accepted until the test suite exists.
        run: |
          set +e
          uv run pytest
          code=$?
          set -e
          if [ "$code" -ne 0 ] && [ "$code" -ne 5 ]; then exit "$code"; fi

  gitleaks:
    name: gitleaks
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7 # v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITLEAKS_CONFIG: .gitleaks.toml

  plumber:
    name: plumber
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - uses: getplumber/plumber@3feac69e925e9771f8a495f4177af754d568c1ad
        with:
          score-push: false
          upload-sarif: true
          # First run: observe only. Tighten to min-score once the baseline is known.
          soft-fail: true

  build-smoke:
    name: build-smoke
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
      - uses: astral-sh/setup-uv@caf0cab7a618c569241d31dcd442f54681755d39 # v3
      - name: Install
        run: uv sync --frozen --all-groups
      - name: Build binary
        run: |
          rm -rf build dist *.spec
          uv run pyinstaller \
            --onefile \
            --name portabase_smoke \
            --paths=. \
            --collect-all rich \
            --collect-all requests \
            --collect-data certifi \
            --add-data "pyproject.toml:." \
            main.py
      - name: Smoke
        run: |
          ./dist/portabase_smoke --version
          ./dist/portabase_smoke --help
```

- [ ] **Step 2: Valider la syntaxe YAML localement**

Run: `uv run python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Vérifier localement ce que fera le job lint**

Run: `uv sync --frozen --all-groups && uv run ruff check . --output-format=github && uv run ruff format --check .`
Expected: aucune sortie d'erreur.

- [ ] **Step 4: Vérifier localement ce que fera le job test**

Run: `uv run pytest; echo "exit=$?"`
Expected: `exit=5` (aucun test collecté).

- [ ] **Step 5: Vérifier localement ce que fera build-smoke**

Run: `rm -rf build dist *.spec && uv run pyinstaller --onefile --name portabase_smoke --paths=. --collect-all rich --collect-all requests --collect-data certifi --add-data "pyproject.toml:." main.py && ./dist/portabase_smoke --version`
Expected: `Portabase CLI version: 26.07.6`. Puis `rm -rf build dist *.spec`.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add PR workflow (lint, test, gitleaks, plumber, build smoke)"
```

---

### Task 5 : Durcir `python.yml` (build binaires)

**Files:**
- Modify: `.github/workflows/python.yml`

**Interfaces:**
- Consumes: appelé par `release.yml` / `release-candidate.yml` via `workflow_call`.
- Produces: artefacts `portabase_<os>_<arch>` inchangés + attestation de provenance.

- [ ] **Step 1: Réécrire le workflow**

```yaml
name: Build Python Binaries

on:
  workflow_call:

permissions: {}

jobs:
  build:
    name: Build for ${{ matrix.os }} (${{ matrix.arch }})
    runs-on: ${{ matrix.runner }}
    permissions:
      contents: read
      id-token: write
      attestations: write
    strategy:
      matrix:
        include:
          - os: linux
            arch: amd64
            runner: ubuntu-latest
          - os: linux
            arch: arm64
            runner: ubuntu-24.04-arm
          - os: macos
            arch: arm64
            runner: macos-latest
          - os: macos
            arch: amd64
            runner: macos-15-intel

    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4

      - uses: astral-sh/setup-uv@caf0cab7a618c569241d31dcd442f54681755d39 # v3

      - name: Install
        run: uv sync --frozen --all-groups

      - name: Build binary
        run: |
          rm -rf build dist *.spec
          uv run pyinstaller \
            --onefile \
            --name portabase_${{ matrix.os }}_${{ matrix.arch }} \
            --paths=. \
            --collect-all rich \
            --collect-all requests \
            --collect-data certifi \
            --add-data "pyproject.toml:." \
            main.py

      - name: Smoke
        run: ./dist/portabase_${{ matrix.os }}_${{ matrix.arch }} --version

      - name: Attest provenance
        uses: actions/attest-build-provenance@e8998f949152b193b063cb0ec769d69d929409be # v2
        with:
          subject-path: dist/portabase_${{ matrix.os }}_${{ matrix.arch }}

      - name: Upload artifacts
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4
        with:
          name: portabase_${{ matrix.os }}_${{ matrix.arch }}
          path: dist/portabase_${{ matrix.os }}_${{ matrix.arch }}
```

Changements par rapport à l'actuel : `uv python install` remplacé par `uv sync --frozen` (respecte `.python-version` et le lock) ; étape `Smoke` ; attestation ; permissions explicites.

- [ ] **Step 2: Valider YAML**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/python.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/python.yml
git commit -m "ci: pin actions, scope permissions, attest binaries in build workflow"
```

---

### Task 6 : Durcir `github.yml` (release GitHub + Discord)

**Files:**
- Modify: `.github/workflows/github.yml`

**Interfaces:**
- Consumes: artefacts de Task 5.
- Produces: release GitHub identique à aujourd'hui.

- [ ] **Step 1: Modifier uniquement l'en-tête et les `uses:`**

Remplacer le bloc `jobs:` d'en-tête et les trois `uses:` ; le reste (changelog config, script Discord) reste identique.

En-tête (après le bloc `on:` existant, avant `jobs:`) — ajouter :

```yaml
permissions: {}
```

Job :

```yaml
jobs:
  create-release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Check out the repo
        uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
        with:
          fetch-depth: 0

      - name: Download artifacts
        if: inputs.artifact_name != ''
        uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093 # v4
        with:
          pattern: ${{ inputs.artifact_name }}
          path: dist
          merge-multiple: true
```

Et plus bas :

```yaml
      - name: Build Changelog
        id: build_changelog
        uses: mikepenz/release-changelog-builder-action@c9dc8369bccbc41e0ac887f8fd674f5925d315f7 # v5
```

```yaml
      - name: Create GitHub Release
        uses: softprops/action-gh-release@3bb12739c298aeb8a4eeaf626c5b8d85266b0e65 # v2
```

- [ ] **Step 2: Vérifier qu'aucun `@vN` non pinné ne reste**

Run: `grep -nE 'uses: .*@v[0-9]' .github/workflows/github.yml`
Expected: aucune sortie.

- [ ] **Step 3: Valider YAML**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/github.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/github.yml
git commit -m "ci: pin actions and scope permissions in release workflow"
```

---

### Task 7 : Durcir `templates-upload.yml` (S3 sans fichier de credentials)

**Files:**
- Modify: `.github/workflows/templates-upload.yml`

**Interfaces:**
- Produces: même arborescence S3 qu'aujourd'hui (`cli/public/templates/<version>/` et `latest/`). La source reste `.github/assets/templates/` jusqu'au Plan 3 qui la déplace vers `templates/` et ajoute le manifest.

- [ ] **Step 1: Réécrire le workflow**

```yaml
name: Upload Templates to S3

on:
  workflow_call:
    inputs:
      version:
        required: true
        type: string
      is_prerelease:
        required: true
        type: boolean
    secrets:
      S3_ENDPOINT:
        required: true
      S3_ACCESS_KEY:
        required: true
      S3_SECRET_KEY:
        required: true
      S3_BUCKET:
        required: true

permissions: {}

jobs:
  upload:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    env:
      # s3cmd reads these flags; no config file is written to disk.
      S3CMD_ARGS: >-
        --access_key=${{ secrets.S3_ACCESS_KEY }}
        --secret_key=${{ secrets.S3_SECRET_KEY }}
        --host=${{ secrets.S3_ENDPOINT }}
        --host-bucket=%(bucket)s.${{ secrets.S3_ENDPOINT }}
        --ssl
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4

      - name: Install s3cmd
        run: sudo apt-get update && sudo apt-get install -y s3cmd

      - name: Upload versioned templates
        run: |
          CLEAN_VERSION="${{ inputs.version }}"
          CLEAN_VERSION="${CLEAN_VERSION#v}"
          s3cmd $S3CMD_ARGS sync .github/assets/templates/ \
            "s3://${{ secrets.S3_BUCKET }}/cli/public/templates/${CLEAN_VERSION}/" --acl-public

      - name: Upload latest templates (stable only)
        if: ${{ !inputs.is_prerelease }}
        run: |
          s3cmd $S3CMD_ARGS sync .github/assets/templates/ \
            "s3://${{ secrets.S3_BUCKET }}/cli/public/templates/latest/" --acl-public
```

Note : les secrets passés en arguments de ligne de commande sont masqués dans les logs par GitHub (`***`). C'est le compromis retenu ; l'alternative (`~/.s3cfg`) laisse les secrets en clair sur le disque du runner.

- [ ] **Step 2: Valider YAML**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/templates-upload.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/templates-upload.yml
git commit -m "ci: pass S3 credentials to s3cmd as flags instead of writing ~/.s3cfg"
```

---

### Task 8 : Permissions top-level sur `release.yml` et `release-candidate.yml`

**Files:**
- Modify: `.github/workflows/release.yml:10-13`
- Modify: `.github/workflows/release-candidate.yml:12-15`

**Interfaces:**
- Produces: workflows appelants avec permissions minimales ; les jobs `uses:` héritent des permissions déclarées dans les workflows appelés (Tasks 5–7).

- [ ] **Step 1: Dans les deux fichiers, remplacer**

```yaml
permissions:
  contents: write
  packages: write
```

par

```yaml
permissions:
  contents: write
  id-token: write
  attestations: write
  security-events: write
```

Un workflow appelant doit déclarer au moins les permissions que les workflows appelés demandent (`contents: write` pour la release, `id-token`/`attestations` pour l'attestation). `packages: write` n'était utilisé par aucun job.

- [ ] **Step 2: Vérifier**

Run: `grep -n "packages" .github/workflows/*.yml`
Expected: aucune sortie.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml .github/workflows/release-candidate.yml
git commit -m "ci: drop unused packages permission, declare attestation permissions"
```

---

### Task 9 : Dependabot

**Files:**
- Create: `.github/dependabot.yml`

**Interfaces:**
- Produces: PRs hebdomadaires pour les SHAs d'actions et les dépendances uv.

- [ ] **Step 1: Créer le fichier**

```yaml
version: 2
updates:
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
    groups:
      actions:
        patterns: ["*"]
    commit-message:
      prefix: "ci"

  - package-ecosystem: uv
    directory: /
    schedule:
      interval: weekly
    groups:
      python:
        patterns: ["*"]
    commit-message:
      prefix: "build"
```

- [ ] **Step 2: Valider YAML**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/dependabot.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add .github/dependabot.yml
git commit -m "ci: enable dependabot for actions and uv"
```

---

### Task 10 : `bump.yml` remplace `./release`

**Files:**
- Create: `.github/workflows/bump.yml`
- Delete: `release`
- Modify: `.github/CONTRIBUTING.md`

**Interfaces:**
- Produces: déclenchement manuel qui commit `chore(release): X`, tague `X` et pousse. Le push du tag déclenche `release.yml` ou `release-candidate.yml` selon le motif, exactement comme le script.

- [ ] **Step 1: Créer le workflow**

```yaml
name: Bump version

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version (e.g. 26.09.0 or 26.09.0rc1). No leading v."
        required: true
        type: string
      channel:
        description: "stable: only from main. rc: any branch."
        required: true
        type: choice
        options: [stable, rc]
        default: rc

permissions: {}

jobs:
  bump:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
        with:
          fetch-depth: 0
          # Use a PAT if branch protection blocks GITHUB_TOKEN pushes to main.
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Validate version against channel
        env:
          VERSION: ${{ inputs.version }}
          CHANNEL: ${{ inputs.channel }}
          REF: ${{ github.ref_name }}
        run: |
          set -euo pipefail
          if [[ "$VERSION" == v* ]]; then
            echo "::error::Version must not start with 'v'"; exit 1
          fi
          if [[ "$CHANNEL" == "stable" ]]; then
            if [[ "$REF" != "main" ]]; then
              echo "::error::stable releases are only allowed from main (got $REF)"; exit 1
            fi
            if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
              echo "::error::stable version must match X.Y.Z"; exit 1
            fi
          else
            if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-.]?(rc|alpha|beta|a|b)[0-9]*(\.[0-9]+)?)$ ]]; then
              echo "::error::rc version must match X.Y.Z(rc|a|b|alpha|beta)N"; exit 1
            fi
          fi
          if git rev-parse "$VERSION" >/dev/null 2>&1; then
            echo "::error::Tag $VERSION already exists"; exit 1
          fi

      - name: Update version files
        env:
          VERSION: ${{ inputs.version }}
        run: |
          set -euo pipefail
          DATE=$(date -u +%F)
          sed -i "s/^version = \".*\"/version = \"$VERSION\"/" pyproject.toml
          if [ -f CITATION.cff ]; then
            sed -i "s/^version: .*/version: $VERSION/" CITATION.cff
            sed -i "s/^date-released: .*/date-released: \"$DATE\"/" CITATION.cff
          fi
          git diff --stat

      - name: Commit, tag, push
        env:
          VERSION: ${{ inputs.version }}
        run: |
          set -euo pipefail
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add pyproject.toml CITATION.cff
          if git diff --cached --quiet; then
            echo "No version change to commit"
          else
            git commit -m "chore(release): $VERSION"
          fi
          git tag -a "$VERSION" -m "Release $VERSION"
          git push origin HEAD
          git push origin "$VERSION"
```

Différences avec le script : pas de `package.json` / `Cargo.toml` (absents du dépôt) ; `git add .` remplacé par un `add` ciblé ; identité bot.

Point à vérifier dans l'interface GitHub (Settings → Branches) : si `main` exige une PR, `git push origin HEAD` sera refusé pour `GITHUB_TOKEN`. Deux solutions : (a) autoriser `github-actions[bot]` à contourner la règle ; (b) créer un PAT fine-grained (Contents: write) stocké en secret `RELEASE_TOKEN` et remplacer `token: ${{ secrets.GITHUB_TOKEN }}` par `token: ${{ secrets.RELEASE_TOKEN }}`. Note : un push effectué avec `GITHUB_TOKEN` ne déclenche **pas** d'autres workflows par design GitHub — **le push du tag ne déclenchera donc pas `release.yml`**. Avec un PAT (`RELEASE_TOKEN`), il le déclenche. → **Utiliser un PAT est obligatoire** pour que le tag lance la release. Créer le secret avant le premier usage.

- [ ] **Step 2: Remplacer le token par le PAT**

Dans le workflow ci-dessus, `token: ${{ secrets.GITHUB_TOKEN }}` → `token: ${{ secrets.RELEASE_TOKEN }}` et supprimer le commentaire au-dessus. Le secret `RELEASE_TOKEN` (fine-grained PAT, dépôt `Portabase/cli`, permissions Contents: Read and write, Metadata: Read) doit être créé par un mainteneur dans Settings → Secrets → Actions.

- [ ] **Step 3: Supprimer le script**

Run: `git rm release`

- [ ] **Step 4: Documenter dans CONTRIBUTING.md**

Ajouter une section à la fin de `.github/CONTRIBUTING.md` :

```markdown
## Releasing

Releases are cut from GitHub Actions, never from a local machine.

1. Open **Actions → Bump version → Run workflow**.
2. Pick the branch (`main` for stable, any branch for a release candidate).
3. Enter the version without a leading `v` (`26.09.0` for stable, `26.09.0rc1` for a candidate) and the matching channel.
4. The workflow commits `chore(release): <version>`, creates the tag and pushes. The tag triggers the build, the GitHub release, the Discord notification and the template upload.

Stable versions must match `X.Y.Z` and can only be cut from `main`.
```

- [ ] **Step 5: Valider YAML**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/bump.yml')); print('ok')"`
Expected: `ok`.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/bump.yml .github/CONTRIBUTING.md
git commit -m "ci: replace ./release script with bump workflow"
```

---

### Task 11 : Vérification de bout en bout sur GitHub

**Files:** aucun.

**Interfaces:**
- Consumes: tout ce qui précède.

- [ ] **Step 1: Pousser une branche et ouvrir une PR**

```bash
git checkout -b ci/hygiene
git push -u origin ci/hygiene
gh pr create --fill --title "ci: PR workflow, pinned actions, bump workflow" --body "Implements plan 1 (chantier A) of docs/superpowers/specs/2026-09-11-cli-refactor-design.md. No CLI behaviour change."
```

(`gh` non authentifié ici : créer la PR depuis l'interface si la commande échoue.)

- [ ] **Step 2: Vérifier les checks**

Expected dans l'onglet Checks : `lint`, `test`, `gitleaks`, `plumber`, `build-smoke` tous verts. `plumber` publie un rapport SARIF dans Security → Code scanning ; noter le score obtenu.

- [ ] **Step 3: Si `plumber` remonte des findings sur les workflows**

Les traiter dans la même PR si triviaux (permission manquante, action non pinnée oubliée). Sinon ouvrir une issue avec la liste et laisser `soft-fail: true`.

- [ ] **Step 4: Créer le secret `RELEASE_TOKEN`**

Settings → Secrets and variables → Actions → New repository secret. PAT fine-grained, dépôt `Portabase/cli`, Contents: Read and write, Metadata: Read.

- [ ] **Step 5: Merger, puis tester `bump.yml` avec un rc jetable**

Actions → Bump version → branche `main`, version `26.07.7rc1`, channel `rc`. Expected : commit `chore(release): 26.07.7rc1` sur `main`, tag créé, `release-candidate.yml` déclenché, binaires attestés publiés en pre-release, templates uploadés sous `templates/26.07.7rc1/`.

- [ ] **Step 6: Rendre les checks requis**

Settings → Branches → `main` → Require status checks : `lint`, `test`, `gitleaks`, `build-smoke`. Laisser `plumber` non requis tant que `soft-fail: true`.

---

## Self-review

**Spec coverage (§9, §10 A) :**
- 9.1 `ci.yml` : lint ✔ (T4), test vide ✔ (T4), gitleaks ✔ (T3, T4), plumber ✔ (T4), build-smoke `--version` ✔ (T4 ; l'invocation `agent --non-interactive` arrive au Plan 4), `render-check` et `engines-check` → Plan 3 (dépendent des templates `.j2` et du registre).
- 9.2 pin SHA ✔ (T4–T8), Dependabot ✔ (T9), `permissions: {}` ✔, `packages: write` retiré ✔ (T8), `~/.s3cfg` supprimé ✔ (T7), attestation ✔ (T5).
- 9.3 `bump.yml` ✔ (T10), `./release` supprimé ✔, pas de release-please ✔, question branch protection → T10/T11. `templates-hotfix.yml` et manifest → Plan 3.
- 9.4 `pyproject.toml` ✔ (T1) ; `jinja2` ajouté au Plan 3 quand il est utilisé.
- 10 A : shippable stable ✔ (T11 step 5 le prouve avec un rc).

**Placeholder scan :** aucun TBD/TODO. Toutes les étapes ont leur contenu ou leur commande.

**Type consistency :** noms de jobs identiques entre T4 et T11 (`lint`, `test`, `gitleaks`, `plumber`, `build-smoke`) ; secret `RELEASE_TOKEN` cohérent T10/T11 ; SHAs identiques entre tâches.

**Écart connu :** T1 `per-file-ignores` liste des fichiers/règles déduits du run ruff du 2026-09-11 ; si ruff remonte une règle non listée sur un fichier legacy, l'ajouter à la liste de ce fichier (pas de correction de code).
