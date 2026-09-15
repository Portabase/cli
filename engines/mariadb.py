from __future__ import annotations

from engines.base import StandardSqlEngine


class MariaDbEngine(StandardSqlEngine):
    key, display, default_port = "mariadb", "MariaDB", 3306
    template, slug, db_prefix = "engines/mariadb.yml.j2", "mariadb", "mysql"
