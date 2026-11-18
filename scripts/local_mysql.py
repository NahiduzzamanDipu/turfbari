"""Project-local MySQL server for TURFOS development (no Windows service, no admin rights).

Uses the installed MySQL Server binaries, with data kept in <repo>/.mysql/ (git-ignored).
The server listens on 127.0.0.1 only.

    python scripts/local_mysql.py init     # one time: create data dir, root password, turfos DB + user
    python scripts/local_mysql.py start    # run the server in the foreground (Ctrl+C to stop)
    python scripts/local_mysql.py stop     # shut down a running server
    python scripts/local_mysql.py status

Run with the backend virtualenv's Python (it has the mysqlclient driver):
    backend\\.venv\\Scripts\\python scripts\\local_mysql.py start
"""

from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MYSQL_HOME = REPO / ".mysql"
DATA_DIR = MYSQL_HOME / "data"
INI = MYSQL_HOME / "my.ini"
LOG = MYSQL_HOME / "mysqld.err"
ENV_FILE = REPO / ".env"
DEFAULT_BASEDIR = Path(os.environ.get("MYSQL_BASEDIR", r"C:\Program Files\MySQL\MySQL Server 8.4"))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mysql_setup_sql import read_env  # noqa: E402


def mysqld() -> Path:
    exe = DEFAULT_BASEDIR / "bin" / ("mysqld.exe" if os.name == "nt" else "mysqld")
    if not exe.exists():
        sys.exit(f"mysqld not found at {exe}. Set MYSQL_BASEDIR to your MySQL install folder.")
    return exe


def port() -> int:
    return int(read_env().get("MYSQL_PORT", "3306"))


def write_ini() -> None:
    MYSQL_HOME.mkdir(exist_ok=True)
    posix = lambda p: p.as_posix()  # noqa: E731 — my.ini accepts forward slashes, avoids escape issues
    INI.write_text(
        "\n".join(
            [
                "[mysqld]",
                f'basedir="{posix(DEFAULT_BASEDIR)}"',
                f'datadir="{posix(DATA_DIR)}"',
                f'log-error="{posix(LOG)}"',
                "bind-address=127.0.0.1",
                f"port={port()}",
                "mysqlx=OFF",
                "character-set-server=utf8mb4",
                "collation-server=utf8mb4_0900_ai_ci",
                "default-time-zone='+06:00'",
                "max_connections=100",
                "innodb_buffer_pool_size=256M",
                "",
            ]
        ),
        encoding="utf-8",
    )


def connect(user: str, password: str, database: str | None = None):
    import MySQLdb

    kwargs = {"host": "127.0.0.1", "port": port(), "user": user, "passwd": password, "charset": "utf8mb4"}
    if database:
        kwargs["db"] = database
    return MySQLdb.connect(**kwargs)


def is_up() -> bool:
    import MySQLdb

    try:
        connect("__probe__", "x").close()
    except MySQLdb.OperationalError as exc:
        # 1045 = access denied -> the server answered, so it is up.
        return exc.args[0] == 1045
    return True


def wait_until_up(timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_up():
            return
        time.sleep(0.5)
    sys.exit(f"MySQL did not start within {timeout:.0f}s. See {LOG}")


def set_env_value(key: str, value: str) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            break
    else:
        lines += ["", "# Project-local MySQL root account (scripts/local_mysql.py)", f"{key}={value}"]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_init(_args) -> None:
    if DATA_DIR.exists() and any(DATA_DIR.iterdir()):
        sys.exit(f"{DATA_DIR} already exists — already initialised. Use 'start'.")
    if is_up():
        sys.exit(f"Something is already listening on 127.0.0.1:{port()}. Stop it first.")
    write_ini()
    print("Initialising data directory...")
    subprocess.run([str(mysqld()), f"--defaults-file={INI}", "--initialize-insecure"], check=True)

    print("Starting temporary server...")
    server = subprocess.Popen([str(mysqld()), f"--defaults-file={INI}"])
    try:
        wait_until_up()
        root_password = secrets.token_urlsafe(24)
        conn = connect("root", "")
        cur = conn.cursor()
        cur.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (root_password,))
        set_env_value("MYSQL_ROOT_PASSWORD", root_password)
        conn.close()

        from mysql_setup_sql import build_statements

        conn = connect("root", root_password)
        cur = conn.cursor()
        for statement in build_statements(read_env()):
            cur.execute(statement)
        conn.commit()
        conn.close()
        print("Created database and app user from .env; root password saved to .env (MYSQL_ROOT_PASSWORD).")
    finally:
        _shutdown(read_env().get("MYSQL_ROOT_PASSWORD", ""))
        server.wait(timeout=60)
    print("Done. Start the server with:  python scripts/local_mysql.py start")


def cmd_start(_args) -> None:
    if not DATA_DIR.exists():
        sys.exit("Not initialised. Run:  python scripts/local_mysql.py init")
    if is_up():
        print(f"MySQL is already running on 127.0.0.1:{port()}.")
        return
    write_ini()  # keeps paths correct if the repo folder moved
    print(f"MySQL starting on 127.0.0.1:{port()} (log: {LOG}). Ctrl+C to stop.")
    try:
        subprocess.run([str(mysqld()), f"--defaults-file={INI}", "--console"], check=False)
    except KeyboardInterrupt:
        pass


def _shutdown(root_password: str) -> None:
    conn = connect("root", root_password)
    try:
        conn.cursor().execute("SHUTDOWN")
    finally:
        conn.close()


def cmd_stop(_args) -> None:
    if not is_up():
        print("MySQL is not running.")
        return
    _shutdown(read_env()["MYSQL_ROOT_PASSWORD"])
    print("MySQL shut down.")


def cmd_status(_args) -> None:
    print(f"running on 127.0.0.1:{port()}" if is_up() else "not running")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("init", cmd_init), ("start", cmd_start), ("stop", cmd_stop), ("status", cmd_status)):
        sub.add_parser(name).set_defaults(func=fn)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
