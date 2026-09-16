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


def _init_repo(tmp_path: Path, content: str = "# test\n") -> git.Repo:
    """Create a minimal git repo with an 'origin' remote.

    Pass a distinct *content* to get a distinct commit hash (and therefore a
    distinct snapshot) when several tests import into the same database.
    """
    repo = git.Repo.init(tmp_path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()
    repo.create_remote("origin", "https://example.com/test-project.git")
    readme = tmp_path / "README.md"
    readme.write_text(content)
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

    def test_snapshot_records_jacoco_format(self, postgres_dsn, tmp_path, sample_xml_path):
        from parana_importer.importer import run_import

        _init_repo(tmp_path)
        snapshot_id, _ = run_import(
            xml_path=sample_xml_path,
            repo_path=str(tmp_path),
            dsn=postgres_dsn,
            captured_at=datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc),
        )
        with psycopg.connect(postgres_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT format FROM coverage_snapshot WHERE id = %s", (snapshot_id,))
                assert cur.fetchone()[0] == "jacoco"


class TestRunImportCobertura:
    def test_cobertura_import(self, postgres_dsn, tmp_path):
        from parana_importer.importer import run_import

        _init_repo(tmp_path, "# cobertura\n")
        snapshot_id, _codebase_id = run_import(
            xml_path=str(FIXTURES_DIR / "coverage_py_cobertura.xml"),
            repo_path=str(tmp_path),
            dsn=postgres_dsn,
            captured_at=datetime(2024, 2, 1, 12, 0, 0, tzinfo=timezone.utc),
        )

        with psycopg.connect(postgres_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT format FROM coverage_snapshot WHERE id = %s", (snapshot_id,))
                assert cur.fetchone()[0] == "cobertura"

                cur.execute(
                    """
                    SELECT p.name FROM package_coverage pc
                    JOIN package p ON p.id = pc.package_id
                    WHERE pc.snapshot_id = %s ORDER BY p.name
                    """,
                    (snapshot_id,),
                )
                assert [r[0] for r in cur.fetchall()] == ["app", "app.models"]

                cur.execute(
                    """
                    SELECT sf.name, fc.missed_lines, fc.covered_lines,
                           fc.missed_branches, fc.covered_branches, fc.covered_complexity
                    FROM file_coverage fc JOIN source_file sf ON sf.id = fc.source_file_id
                    WHERE fc.snapshot_id = %s ORDER BY sf.name
                    """,
                    (snapshot_id,),
                )
                rows = cur.fetchall()
                assert [r[0] for r in rows] == [
                    "app/__init__.py",
                    "app/models/__init__.py",
                    "app/models/user.py",
                    "app/util.py",
                ]
                assert rows[3][1:] == (2, 6, 1, 3, 0)

                cur.execute(
                    "SELECT COUNT(*) FROM method_coverage WHERE snapshot_id = %s",
                    (snapshot_id,),
                )
                assert cur.fetchone()[0] == 0  # coverage.py emits no <method> elements

                cur.execute(
                    "SELECT COUNT(*) FROM line_coverage_sequence WHERE snapshot_id = %s",
                    (snapshot_id,),
                )
                assert cur.fetchone()[0] == 7 + 6  # user.py + util.py sequences

    def test_explicit_format_flag(self, postgres_dsn, tmp_path):
        from parana_importer.importer import run_import

        _init_repo(tmp_path, "# cobertura methods\n")
        snapshot_id, _ = run_import(
            xml_path=str(FIXTURES_DIR / "cobertura_methods.xml"),
            repo_path=str(tmp_path),
            dsn=postgres_dsn,
            captured_at=datetime(2024, 2, 1, 13, 0, 0, tzinfo=timezone.utc),
            report_format="cobertura",
        )
        with psycopg.connect(postgres_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM method_coverage WHERE snapshot_id = %s",
                    (snapshot_id,),
                )
                assert cur.fetchone()[0] == 4

    def test_format_column_added_to_existing_schema(self, postgres_dsn):
        """A database created before the format column existed is migrated in place."""
        from parana_importer import db

        with psycopg.connect(postgres_dsn) as conn:
            with conn.cursor() as cur:
                # Recreate the pre-format schema: no column, 3-column unique key.
                cur.execute("DELETE FROM coverage_snapshot")
                cur.execute("ALTER TABLE coverage_snapshot DROP COLUMN format")
                cur.execute(
                    "ALTER TABLE coverage_snapshot ADD UNIQUE "
                    "(codebase_id, git_commit_hash, uncommitted_files_hash)"
                )
            conn.commit()
            for _ in range(2):  # idempotent
                db.ensure_schema(conn)
                conn.commit()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT column_default FROM information_schema.columns
                    WHERE table_name = 'coverage_snapshot' AND column_name = 'format'
                    """
                )
                row = cur.fetchone()
                assert row is not None
                assert "jacoco" in row[0]
                cur.execute(
                    """
                    SELECT conname FROM pg_constraint
                    WHERE conrelid = 'coverage_snapshot'::regclass AND contype = 'u'
                    """
                )
                assert [r[0] for r in cur.fetchall()] == ["uq_snapshot_identity"]

    def test_two_formats_for_same_commit_are_distinct_snapshots(self, postgres_dsn, tmp_path):
        """A JaCoCo and a Cobertura report for one commit both get stored."""
        from parana_importer.importer import run_import

        _init_repo(tmp_path, "# polyglot\n")
        captured = datetime(2024, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
        jacoco_id, codebase_id = run_import(
            xml_path=str(FIXTURES_DIR / "sample.xml"),
            repo_path=str(tmp_path),
            dsn=postgres_dsn,
            captured_at=captured,
        )
        cobertura_id, codebase_id_2 = run_import(
            xml_path=str(FIXTURES_DIR / "coverage_py_cobertura.xml"),
            repo_path=str(tmp_path),
            dsn=postgres_dsn,
            captured_at=captured,
        )
        assert codebase_id == codebase_id_2
        assert jacoco_id != cobertura_id

        # Re-importing the Cobertura report is still idempotent.
        again, _ = run_import(
            xml_path=str(FIXTURES_DIR / "coverage_py_cobertura.xml"),
            repo_path=str(tmp_path),
            dsn=postgres_dsn,
            captured_at=captured,
        )
        assert again == cobertura_id

        with psycopg.connect(postgres_dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, format FROM coverage_snapshot WHERE id IN (%s, %s) ORDER BY id",
                (jacoco_id, cobertura_id),
            )
            assert cur.fetchall() == [(jacoco_id, "jacoco"), (cobertura_id, "cobertura")]
            cur.execute(
                "SELECT COUNT(*) FROM file_coverage WHERE snapshot_id = %s", (cobertura_id,)
            )
            assert cur.fetchone()[0] == 4
