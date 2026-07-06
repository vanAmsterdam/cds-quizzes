from cds_quizzes.config import _normalize_database_url
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
