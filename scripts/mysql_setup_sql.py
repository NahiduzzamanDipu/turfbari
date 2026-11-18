"""Print the SQL that creates the TURFOS database and app user, using values from .env.

Pipe it into the MySQL client as root (you'll be prompted for the root password):

    backend\\.venv\\Scripts\\python scripts\\mysql_setup_sql.py | & "C:\\Program Files\\MySQL\\MySQL Server 8.4\\bin\\mysql.exe" -u root -p

Safe to run more than once.
"""

import pathlib
import re
import sys

ENV = pathlib.Path(__file__).resolve().parent.parent / ".env"
IDENT = re.compile(r"^[A-Za-z0-9_]+$")


def read_env() -> dict[str, str]:
    values = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def build_statements(env: dict[str, str]) -> list[str]:
    db = env.get("MYSQL_DATABASE", "turfos")
    user = env.get("MYSQL_USER", "turfos")
    password = env.get("MYSQL_PASSWORD", "")
    if not IDENT.match(db) or not IDENT.match(user):
        sys.exit("MYSQL_DATABASE and MYSQL_USER may only contain letters, digits and underscores.")
    if not password or password == "change-me":
        sys.exit("Set MYSQL_PASSWORD in .env first.")
    pw = password.replace("\\", "\\\\").replace("'", "\\'")

    statements = [f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"]
    for host in ("localhost", "127.0.0.1"):
        statements += [
            f"CREATE USER IF NOT EXISTS '{user}'@'{host}' IDENTIFIED BY '{pw}';",
            f"ALTER USER '{user}'@'{host}' IDENTIFIED BY '{pw}';",
            f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'{host}';",
            # pytest creates and drops test_<db>.
            f"GRANT ALL PRIVILEGES ON `test_{db}`.* TO '{user}'@'{host}';",
        ]
    statements.append("FLUSH PRIVILEGES;")
    return statements


def main() -> None:
    print("\n".join(build_statements(read_env())))


if __name__ == "__main__":
    main()
