"""Database URL normalisation and platform detection.

Both run at import time, so they are extracted into pure functions that can be
tested without importing ``app.db`` and opening a connection.
"""
from app.db import is_hosted_platform, normalize_database_url


class TestNormalizeDatabaseUrl:
    def test_mysql_scheme_gets_the_pymysql_driver(self):
        assert normalize_database_url(
            "mysql://user:pass@host:3306/db"
        ) == "mysql+pymysql://user:pass@host:3306/db"

    def test_mariadb_scheme_gets_the_pymysql_driver(self):
        assert normalize_database_url("mariadb://u:p@h/db").startswith(
            "mysql+pymysql://"
        )

    def test_postgres_scheme_gets_psycopg_and_tls(self):
        assert normalize_database_url("postgres://u:p@h/db") == (
            "postgresql+psycopg://u:p@h/db?sslmode=require"
        )

    def test_postgresql_scheme_gets_psycopg_and_tls(self):
        assert normalize_database_url("postgresql://u:p@h/db") == (
            "postgresql+psycopg://u:p@h/db?sslmode=require"
        )

    def test_tls_is_appended_with_an_ampersand_when_a_query_exists(self):
        url = normalize_database_url("postgresql://u:p@h/db?connect_timeout=10")

        assert url.endswith("&sslmode=require")
        assert "connect_timeout=10" in url

    def test_existing_sslmode_is_respected(self):
        url = normalize_database_url("postgresql://u:p@h/db?sslmode=verify-full")

        assert url.count("sslmode=") == 1
        assert "verify-full" in url

    def test_sqlite_is_left_alone(self):
        assert normalize_database_url("sqlite:///./app.db") == "sqlite:///./app.db"

    def test_already_correct_url_is_unchanged(self):
        url = "mysql+pymysql://u:p@h:3306/db"

        assert normalize_database_url(url) == url


class TestIsHostedPlatform:
    def test_vercel_marks_a_hosted_platform(self):
        assert is_hosted_platform({"VERCEL": "1"}) is True

    def test_other_known_platforms_are_detected(self):
        for environ in (
            {"RENDER": "true"},
            {"RAILWAY_ENVIRONMENT": "production"},
            {"FLY_APP_NAME": "app"},
            {"RENDER_EXTERNAL_URL": "https://x.onrender.com"},
        ):
            assert is_hosted_platform(environ) is True, environ

    def test_local_environment_is_not_hosted(self):
        assert is_hosted_platform({}) is False
        assert is_hosted_platform({"PATH": "/usr/bin"}) is False