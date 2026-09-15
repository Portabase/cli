from __future__ import annotations

from engines.mariadb import MariaDbEngine


class MySqlEngine(MariaDbEngine):
    key, display = "mysql", "MySQL"
    template = "engines/mysql.yml.j2"
