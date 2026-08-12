import os
from pathlib import Path

import mysql.connector
from mysql.connector import Error


def load_env_file():
    env_path = Path(__file__).resolve().parents[2] / ".env"

    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_db_config():
    load_env_file()

    config = {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "cognitive_load_db"),
    }

    ssl_ca = os.getenv("MYSQL_SSL_CA")
    if ssl_ca:
        config["ssl_ca"] = ssl_ca

    if os.getenv("MYSQL_SSL_DISABLED", "").lower() in ("false", "0", "no"):
        config["ssl_disabled"] = False

    return config


def get_db_connection():
    try:
        return mysql.connector.connect(**get_db_config())
    except Error as exc:
        print(f"MySQL connection unavailable: {exc}")
        return None
