from cds_quizzes.config import get_settings, _normalize_database_url
from cds_quizzes.database import _postgres_connect_args


def test_normalize_supabase_postgres_urls_for_sqlalchemy():
    assert (
        _normalize_database_url("postgres://user:pass@example.com:5432/postgres")
        == "postgresql+psycopg2://user:pass@example.com:5432/postgres"
    )
    assert (
        _normalize_database_url("postgresql://user:pass@example.com:5432/postgres")
        == "postgresql+psycopg2://user:pass@example.com:5432/postgres"
    )


def test_supabase_postgres_connect_args_disable_gss_and_require_ssl():
    connect_args = _postgres_connect_args(
        "postgresql+psycopg2://user:pass@aws-1-eu-west-2.pooler.supabase.com:5432/postgres"
    )

    assert connect_args["connect_timeout"] == 10
    assert connect_args["gssencmode"] == "disable"
    assert connect_args["sslmode"] == "require"


def test_explicit_postgres_connect_args_are_respected():
    connect_args = _postgres_connect_args(
        "postgresql+psycopg2://user:pass@example.com:5432/postgres?gssencmode=require&sslmode=disable"
    )

    assert "gssencmode" not in connect_args
    assert "sslmode" not in connect_args


def test_postgres_pool_defaults_are_classroom_sized(monkeypatch):
    monkeypatch.setenv("CDS_DATABASE_URL", "postgresql+psycopg2://user:pass@example.com:5432/postgres")
    monkeypatch.delenv("CDS_DATABASE_POOL_SIZE", raising=False)
    monkeypatch.delenv("CDS_DATABASE_MAX_OVERFLOW", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.database_pool_size == 5
    assert settings.database_max_overflow == 0
