<br />
<div align="center">
  <a href="https://portabase.io">
    <img src="https://github.com/Portabase/cli/blob/main/.github/assets/logo.png?raw=true" alt="Logo" width="80" height="80">
  </a>

<h3 align="center">Portabase CLI</h3>

  <p align="center" style="margin-top: 20px; font-style: italic;">
    <i>The official command line interface (CLI) for managing and deploying Portabase instances with ease.</i>
  </p>

[![Plumber Score](https://score.getplumber.io/github.com/Portabase/cli.svg)](https://score.getplumber.io/github.com/Portabase/cli)
[![License: Apache](https://img.shields.io/badge/License-apache-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos%20%7C%20windows-lightgrey)](https://github.com/Portabase/portabase)

[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![MySQL](https://img.shields.io/badge/MySQL-4479A1?logo=mysql&logoColor=white)](https://www.mysql.com/)
[![MariaDB](https://img.shields.io/badge/MariaDB-003545?logo=mariadb&logoColor=white)](https://mariadb.org/)
[![Self Hosted](https://img.shields.io/badge/self--hosted-yes-brightgreen)](https://github.com/Portabase/portabase)
[![Open Source](https://img.shields.io/badge/open%20source-❤️-red)](https://github.com/Portabase/portabase)



![Python][Python]
![Typer][Typer]
![Rich][Rich]


  <p>
    <strong>
        <a href="https://portabase.io">Website</a> •
        <a href="https://portabase.io/docs">Documentation</a> •
        <a href="https://portabase.io/docs/cli">Installation</a> •
        <a href="https://github.com/Portabase/cli/issues/new?labels=bug&template=bug-report---.md">Report Bug</a> •
        <a href="https://github.com/Portabase/cli/issues/new?labels=enhancement&template=feature-request---.md">Request Feature</a>
    </strong>
  </p>

</div>

## Installation

You can install Portabase CLI using bash with the following command:

```bash
curl -sSL https://portabase.io/install | bash
```

- Development setup - [details](https://portabase.io/docs/cli#development-setup)

For more installation options, please refer to the [official documentation](https://portabase.io/docs/cli).

## License

Distributed under the Apache License. See `LICENSE.txt` for more details.

[Python]: https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54

[Typer]: https://img.shields.io/badge/typer-FF5733?style=for-the-badge&logo=typer&logoColor=white

[Rich]: https://img.shields.io/badge/rich-5E60CE?style=for-the-badge&logo=rich&logoColor=white




## Commands

```
portabase agent create NAME            create an agent folder
portabase agent db add|remove|list NAME
portabase dashboard create NAME        create a dashboard folder
portabase dashboard show|set|unset NAME
portabase dashboard auth add|list|remove NAME
portabase start|stop|restart|logs|uninstall|build PATH
```

`portabase db` still works for one release as an alias of `portabase agent db`.

## Upgrading from 26.08 or earlier

From this release the CLI owns `docker-compose.yml`: it is re-rendered from your
`.env` and `databases.json` whenever you run `portabase agent db add`, `agent db remove` or
`build`. The first time that happens on an older install, the existing file is
copied to `docker-compose.legacy.yml` first.

- Preview the change before applying it: `portabase build <name> --diff`
- Keep your own customisations in `docker-compose.override.yml`; Docker Compose
  merges it automatically and the CLI never touches it.
