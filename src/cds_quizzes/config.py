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
    admin_password = os.getenv("CDS_ADMIN_PASSWORD") or _streamlit_secret("app", "admin_password")
    if not admin_password and database_url.startswith("sqlite"):
        admin_password = "admin"
    return Settings(database_url=str(database_url), admin_password=admin_password)
