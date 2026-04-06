"""Shared pytest fixtures for the Parana importer test suite."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def sample_xml_path() -> str:
    """Return the path to the bundled sample JaCoCo XML fixture."""
    return str(FIXTURES_DIR / "sample.xml")


@pytest.fixture(scope="session")
def postgres_dsn():
    """Spin up a temporary Postgres container and yield a psycopg DSN.

    Requires the ``testcontainers[postgres]`` extra.  The container is started
    once per test session and shared across all integration tests.
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers[postgres] not installed")

    with PostgresContainer("postgres:16") as pg:
        # testcontainers returns a SQLAlchemy-style URL; convert to psycopg URI.
        url = pg.get_connection_url()
        # Replace "postgresql+psycopg2://" or "postgresql://" prefix
        dsn = url.replace("postgresql+psycopg2://", "postgresql://").replace(
            "postgresql+psycopg://", "postgresql://"
        )
        yield dsn
