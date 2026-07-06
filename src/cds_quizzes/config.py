from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_WORKBOOK_PATH = DATA_DIR / "causal_dag_peer_discussion_question_bank.xlsx"
DEFAULT_SAMPLE_ROSTER_PATH = DATA_DIR / "sample_roster.csv"
DEFAULT_SQLITE_PATH = DATA_DIR / "dev.sqlite"


@dataclass(frozen=True)
class Settings:
    database_url: str
    admin_password: str | None
    database_pool_size: int = 2
    database_max_overflow: int = 0
    database_pool_timeout: int = 10
    database_pool_recycle: int = 300

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def _streamlit_secret(*keys: str) -> Any | None:
    try:
        import streamlit as st

        value: Any = st.secrets
        for key in keys:
            value = value[key]
        return value
    except Exception:
        return None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    database_url = (
        os.getenv("CDS_DATABASE_URL")
        or _streamlit_secret("database", "url")
        or f"sqlite:///{DEFAULT_SQLITE_PATH}"
    )
    database_url = _normalize_database_url(str(database_url))
    admin_password = os.getenv("CDS_ADMIN_PASSWORD") or _streamlit_secret("app", "admin_password")
    if not admin_password and database_url.startswith("sqlite"):
        admin_password = "admin"
    return Settings(
        database_url=database_url,
        admin_password=admin_password,
        database_pool_size=_int_setting("CDS_DATABASE_POOL_SIZE", ("database", "pool_size"), 2),
        database_max_overflow=_int_setting("CDS_DATABASE_MAX_OVERFLOW", ("database", "max_overflow"), 0),
        database_pool_timeout=_int_setting("CDS_DATABASE_POOL_TIMEOUT", ("database", "pool_timeout"), 10),
        database_pool_recycle=_int_setting("CDS_DATABASE_POOL_RECYCLE", ("database", "pool_recycle"), 300),
    )


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg2://" + database_url.removeprefix("postgres://")
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + database_url.removeprefix("postgresql://")
    return database_url


def _int_setting(env_name: str, secret_keys: tuple[str, str], default: int) -> int:
    raw_value = os.getenv(env_name) or _streamlit_secret(*secret_keys)
    if raw_value in (None, ""):
        return default
    return int(raw_value)
