"""Integration tests for run_import against a real Postgres database.

These tests require the ``testcontainers[postgres]`` extra.  They are skipped
automatically when testcontainers is not installed (see conftest.py).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import git

import psycopg

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _init_repo(tmp_path: Path) -> git.Repo:
    """Create a minimal git repo with an 'origin' remote."""
    repo = git.Repo.init(tmp_path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    repo.create_remote("origin", "https://example.com/test-project.git")
    readme = tmp_path / "README.md"
    readme.write_text("# test\n")
    repo.index.add(["README.md"])
    repo.index.commit("initial commit")
    return repo


class TestRunImport:
    def test_basic_import(self, postgres_dsn, tmp_path, sample_xml_path):
        from parana_importer.importer import run_import

        _init_repo(tmp_path)
        captured_at = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        snapshot_id, codebase_id = run_import(
            xml_path=sample_xml_path,
            repo_path=str(tmp_path),
            dsn=postgres_dsn,
            captured_at=captured_at,
        )

        assert isinstance(snapshot_id, int)
        assert snapshot_id > 0
        assert isinstance(codebase_id, int)
        assert codebase_id > 0

    def test_import_populates_tables(self, postgres_dsn, tmp_path, sample_xml_path):
        from parana_importer.importer import run_import

        _init_repo(tmp_path)
        captured_at = datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc)

        snapshot_id, codebase_id = run_import(
            xml_path=sample_xml_path,
            repo_path=str(tmp_path),
            dsn=postgres_dsn,
            captured_at=captured_at,
        )

        with psycopg.connect(postgres_dsn) as conn:
            with conn.cursor() as cur:
                # codebase row
                cur.execute("SELECT git_origin FROM codebase WHERE id = %s", (codebase_id,))
                row = cur.fetchone()
                assert row is not None
                assert row[0] == "https://example.com/test-project.git"

                # snapshot row
                cur.execute(
                    "SELECT codebase_id FROM coverage_snapshot WHERE id = %s",
                    (snapshot_id,),
                )
                assert cur.fetchone()[0] == codebase_id

                # package row
                cur.execute(
                    "SELECT name FROM package WHERE codebase_id = %s",
                    (codebase_id,),
                )
                pkg = cur.fetchone()
                assert pkg is not None
                assert pkg[0] == "com/example"

                # method coverage rows
                cur.execute(
                    "SELECT COUNT(*) FROM method_coverage WHERE snapshot_id = %s",
                    (snapshot_id,),
                )
                assert cur.fetchone()[0] == 3  # add, subtract, multiply

                # file coverage row
                cur.execute(
                    "SELECT COUNT(*) FROM file_coverage WHERE snapshot_id = %s",
                    (snapshot_id,),
                )
                assert cur.fetchone()[0] == 1

                # line coverage sequences (expect 3 from the fixture)
                cur.execute(
                    "SELECT COUNT(*) FROM line_coverage_sequence WHERE snapshot_id = %s",
                    (snapshot_id,),
                )
                assert cur.fetchone()[0] == 3

    def test_idempotent_import(self, postgres_dsn, tmp_path, sample_xml_path):
        """Re-importing the same report returns the same snapshot id."""
        from parana_importer.importer import run_import

        _init_repo(tmp_path)
        captured_at = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

        snap1, _ = run_import(
            xml_path=sample_xml_path,
            repo_path=str(tmp_path),
            dsn=postgres_dsn,
            captured_at=captured_at,
        )
        snap2, _ = run_import(
            xml_path=sample_xml_path,
            repo_path=str(tmp_path),
            dsn=postgres_dsn,
            captured_at=captured_at,
        )

        assert snap1 == snap2

        # And it should not have inserted duplicate coverage rows.
        with psycopg.connect(postgres_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM method_coverage WHERE snapshot_id = %s",
                    (snap1,),
                )
                assert cur.fetchone()[0] == 3  # still only 3, not 6
