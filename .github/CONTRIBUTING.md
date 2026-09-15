---

# Contributing to Portabase

Thank you for considering contributing to **Portabase!** 🎉 Contributions help make this project better for everyone.

Please take a moment to review this guide. It will help you understand how to contribute effectively.

---

## Table of Contents

1. [How to Get Started](#how-to-get-started)
2. [Running the CLI (Development)](#running-the-cli-development)
3. [Reporting Issues](#reporting-issues)
4. [Submitting Changes](#submitting-changes)
5. [Code Style Guidelines](#code-style-guidelines)
6. [Pull Request Process](#pull-request-process)
7. [Community Guidelines](#community-guidelines)

---

## How to Get Started

1. **Fork the repository**  
   Click the "Fork" button at the top-right corner of this repository.

2. **Clone the repository**
   ```bash
   git clone https://github.com/Portabase/cli.git
   ```

3. **Set up the development environment**  
   Follow the steps in the `README.md` to install dependencies and configure the project.

4. **Create a branch**  
   Use the feature branch to work on changes.
   ```bash
   git checkout -b feature/<feature-name>
   ```

---

## Running the CLI (Development)

The project is a [Typer](https://typer.tiangolo.com/) CLI managed with
[uv](https://docs.astral.sh/uv/). The entry point is `main.py`.

### Set up the environment

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then sync
the dependencies (creates `.venv` and installs everything from `uv.lock`):

```bash
uv sync
```

### Run any command from source

While developing, run the CLI through `uv run` instead of the installed
`portabase` binary. The pattern is:

```bash
uv run python main.py <command> [ARGS] [OPTIONS]
```

Anything after `main.py` is a normal CLI invocation, so `portabase <command>`
(once built/installed) and `uv run python main.py <command>` are equivalent.

Show the top-level help and version:

```bash
uv run python main.py --help
uv run python main.py --version
```

> Tip: append `--help` to any command to see its arguments, e.g.
> `uv run python main.py agent --help`.

### Creation commands

Create an agent (interactive; flags pre-fill the prompts):

```bash
# name is required (creates a folder); everything else is optional
uv run python main.py agent my-agent
uv run python main.py agent my-agent --key <EDGE_KEY> --tz Europe/Paris --polling 10 --start
```

| Arg / Option | Default | Description |
| --- | --- | --- |
| `name` (arg) | — | Agent name; creates a folder of that name. |
| `--key`, `-k` | prompt | Edge Key (Base64 or JSON). Prompted if omitted. |
| `--tz` | `UTC` | Timezone. |
| `--polling` | `5` | Polling frequency in seconds. |
| `--start`, `-s` | off | Start the agent immediately after setup. |

Create a dashboard:

```bash
uv run python main.py dashboard my-dashboard
uv run python main.py dashboard my-dashboard --port 9000 --start
```

| Arg / Option | Default | Description |
| --- | --- | --- |
| `name` (arg) | — | Dashboard name; creates a folder of that name. |
| `--port` | `8887` | Web port. |
| `--start`, `-s` | off | Start the dashboard immediately after setup. |

### Lifecycle commands

Each takes the path to a component folder (the one created above):

```bash
uv run python main.py start my-agent
uv run python main.py stop my-agent
uv run python main.py restart my-agent
uv run python main.py logs my-agent            # follows by default
uv run python main.py logs my-agent --no-follow
uv run python main.py uninstall my-agent       # prompts for confirmation
uv run python main.py uninstall my-agent --force
```

| Command | Arg / Option | Description |
| --- | --- | --- |
| `start` / `stop` / `restart` | `path` (arg) | Path to the component folder. |
| `logs` | `path` (arg), `--follow/--no-follow`, `-f` | Stream logs; follows unless `--no-follow`. |
| `uninstall` | `path` (arg), `--force`, `-f` | Remove containers and data; `--force` skips the prompt. |

### Configuration commands

Decrypt Portabase `.enc` backup files (single file or a folder of `.enc` files):

```bash
# single file -> explicit output
uv run python main.py decrypt backup.tar.gz.enc backup.tar.gz --key master_key.bin
# folder -> decrypt every .enc into an output folder
uv run python main.py decrypt ./backups ./restored --key master_key.bin
# omit output to write next to the input; omit --key to use ./master_key.bin
uv run python main.py decrypt backup.tar.gz.enc
```

| Arg / Option | Default | Description |
| --- | --- | --- |
| `input_path` (arg) | — | A `.enc` file, or a folder containing `.enc` files. |
| `output_path` (arg) | input's directory | Output file or folder (must match the input type). |
| `--key`, `-k` | `./master_key.bin` | Path to the master key file (raw 32-byte or Base64 AES-256 key). |

Manage the configured databases of an agent:

```bash
uv run python main.py db list my-agent
uv run python main.py db add my-agent
uv run python main.py db remove my-agent
```

Manage global CLI configuration:

```bash
uv run python main.py config show
uv run python main.py config channel stable   # or: beta
```

### System commands

```bash
uv run python main.py update
```

### Running the tests

Unit tests live in `tests/`, mirroring `core/`, `services/` and `engines/`. They call
the functions directly: no Docker, no network, no built binary.

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```
---

## Reporting Issues

If you encounter a bug or have a suggestion for improvement, follow these steps:

1. **Check existing issues** to avoid duplicates.
2. **Open a new issue** if needed:
    - Provide a clear and descriptive title.
    - Describe the issue with steps to reproduce it (if applicable).
    - Include relevant logs, screenshots, or code snippets.

---

## Submitting Changes

1. **Ensure your branch is up to date**
   ```bash
   git pull origin main
   ```

2. **Write meaningful commit messages**  
   Follow this format:
   ```
   [type] Summary of changes
   ```
   Example:
   ```
   feat: add user authentication
   fix: resolve crash on login page
   ```

3. **Push your branch**
   ```bash
   git push origin feature/<feature-name>
   ```

4. **Open a Pull Request (PR)**  
   Go to the repository on GitHub and click "New Pull Request."

---

## Code Style Guidelines

- Follow the [specific coding style guide] (e.g., Prettier, ESLint, PEP8).
- Use meaningful variable names and include comments where necessary.
- Tests before submitting your changes.

---

## Pull Request Process

1. Ensure your code passes all tests and linters.
2. Provide a clear description of what your PR does.
3. Reference any related issues (e.g., `Closes #123`).
4. Wait for a review from a maintainer.

---

## Community Guidelines

- Be respectful and inclusive to all contributors.
- Follow the [Code of Conduct](CODE_OF_CONDUCT.md).
- Feel free to ask questions if you’re unsure about something.

---

Thank you for contributing! 🙌

---
## Releasing

Releases are cut from GitHub Actions, never from a local machine.

1. Open **Actions → Bump version → Run workflow**.
2. Pick the branch (`main` for stable, any branch for a release candidate).
3. Enter the version without a leading `v` (`26.09.0` for stable, `26.09.0rc1` for a candidate) and the matching channel.
4. The workflow commits `chore(release): <version>`, creates the tag and pushes. The tag triggers the build, the GitHub release and the Discord notification.

Stable versions must match `X.Y.Z` and can only be cut from `main`.

The workflow pushes with a token minted from the Portabase GitHub App (`APP_ID` repository variable, `APP_PRIVATE_KEY` secret), scoped to *Contents: write*. The app must be installed on this repository and allowed to push to `main`. A tag pushed with the default `GITHUB_TOKEN` would not trigger the release workflows.
