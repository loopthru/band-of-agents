import os
from urllib.parse import quote

import psycopg
from dotenv import dotenv_values
from psycopg.rows import dict_row


class DatabaseConfigurationError(RuntimeError):
    pass


def database_url_from_env() -> str:
    settings = dotenv_values(".env")
    database_url = _setting("DATABASE_URL", settings)
    if database_url:
        return database_url

    host = _setting("HOST", settings) or _setting("PGHOST", settings)
    port = _setting("PORT", settings) or _setting("PGPORT", settings) or "5432"
    database = _setting("DATABASE", settings) or _setting("PGDATABASE", settings)
    user = _setting("DB_USER", settings) or _setting("PGUSER", settings)
    password = _setting("DB_PASSWORD", settings) or _setting("PGPASSWORD", settings)

    if not all((host, database, user, password)):
        raise DatabaseConfigurationError(
            "Database configuration requires DATABASE_URL or "
            "HOST, DATABASE, DB_USER, and DB_PASSWORD."
        )

    return (
        f"postgresql://{quote(user)}:{quote(password)}@"
        f"{host}:{port}/{quote(database, safe='')}"
    )


def _setting(name: str, dotenv_settings: dict[str, str | None]) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    dotenv_value = dotenv_settings.get(name)
    return dotenv_value if dotenv_value else None


def connect() -> psycopg.Connection:
    return psycopg.connect(database_url_from_env(), row_factory=dict_row)
