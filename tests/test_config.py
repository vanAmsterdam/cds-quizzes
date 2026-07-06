from cds_quizzes.config import _normalize_database_url


def test_normalize_supabase_postgres_urls_for_sqlalchemy():
    assert (
        _normalize_database_url("postgres://user:pass@example.com:5432/postgres")
        == "postgresql+psycopg2://user:pass@example.com:5432/postgres"
    )
    assert (
        _normalize_database_url("postgresql://user:pass@example.com:5432/postgres")
        == "postgresql+psycopg2://user:pass@example.com:5432/postgres"
    )
