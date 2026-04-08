"""Import orchestrator — ties together git metadata, XML parsing, and DB writes.

The entire import of one JaCoCo report runs inside a single database
transaction.  If any step fails the transaction is rolled back so the database
is never left in a partially-imported state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from . import db
from .git_meta import (
    compute_uncommitted_files_hash,
    resolve_commit_hash,
    resolve_git_branch,
    resolve_git_origin,
)
from .parser import parse_jacoco_xml
from .sequences import compress_lines


def run_import(
    xml_path: str,
    repo_path: str,
    dsn: str,
    captured_at: Optional[datetime] = None,
) -> tuple[int, int]:
    """Parse a JaCoCo XML report and persist it into the Parana database.

    All writes happen inside one atomic transaction; if anything fails the
    database is left unchanged.

    Args:
        xml_path:    Path to the JaCoCo XML report file.
        repo_path:   Root directory of the Java project's git repository.
        dsn:         psycopg connection string / URI for the Parana database.
        captured_at: UTC timestamp to record as the report-generation time.
                     Defaults to the current UTC time when not supplied.

    Returns:
        ``(snapshot_id, codebase_id)`` — both are BIGINT primary-key values
        from the database.  If the same commit + uncommitted-hash combination
        was imported before, the existing snapshot id is returned and no data
        is written.
    """
    if captured_at is None:
        captured_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # 1. Gather git metadata (outside the DB transaction; these are
    #    read-only operations on the local repository).
    # ------------------------------------------------------------------
    git_origin = resolve_git_origin(repo_path)
    git_branch = resolve_git_branch(repo_path)
    git_commit_hash = resolve_commit_hash(repo_path)
    uncommitted_files_hash = compute_uncommitted_files_hash(repo_path)

    # ------------------------------------------------------------------
    # 2. Parse the JaCoCo XML report into memory.
    # ------------------------------------------------------------------
    report = parse_jacoco_xml(xml_path)

    # ------------------------------------------------------------------
    # 3. Persist everything in a single atomic transaction.
    # ------------------------------------------------------------------
    
    # First, ensure the schema is up to date (this handles its own locking/transaction)
    db.ensure_schema(dsn)

    conn = db.connect(dsn)
    try:
        with conn.transaction():
            codebase_id = db.upsert_codebase(conn, git_origin)

            snapshot_id, is_new = db.insert_snapshot(
                conn,
                codebase_id,
                git_branch,
                git_commit_hash,
                uncommitted_files_hash,
                captured_at,
            )

            if not is_new:
                # Idempotent import: this exact snapshot already exists.
                return snapshot_id, codebase_id

            # Accumulate bulk-insert rows across all packages.
            method_cov_rows: list[tuple[int, list]] = []
            class_cov_rows: list[tuple[int, list]] = []
            file_cov_rows: list[tuple[int, list]] = []
            pkg_cov_rows: list[tuple[int, list]] = []
            line_seq_rows = []

            for package in report.packages:
                package_id = db.upsert_package(conn, codebase_id, package.name)

                # Build source_file_id lookup for this package.
                sf_id_map: dict[str, int] = {}
                for sf in package.source_files:
                    sf_id = db.upsert_source_file(conn, package_id, sf.name)
                    sf_id_map[sf.name] = sf_id

                # Process classes and their methods.
                for cls in package.classes:
                    sf_id = sf_id_map.get(cls.source_file_name)
                    if sf_id is None:
                        # Shouldn't happen with well-formed JaCoCo XML, but
                        # guard against it defensively.
                        continue
                    class_id = db.upsert_java_class(conn, sf_id, cls.name)

                    for method in cls.methods:
                        method_id = db.upsert_method(
                            conn,
                            class_id,
                            method.name,
                            method.descriptor,
                            method.start_line,
                        )
                        method_cov_rows.append((method_id, method.counters))

                    class_cov_rows.append((class_id, cls.counters))

                # Process source files: line sequences + file-level counters.
                for sf in package.source_files:
                    sf_id = sf_id_map[sf.name]
                    seqs = compress_lines(sf.lines)
                    for seq in seqs:
                        seq.source_file_id = sf_id
                    line_seq_rows.extend(seqs)
                    file_cov_rows.append((sf_id, sf.counters))

                pkg_cov_rows.append((package_id, package.counters))

            # Bulk-insert all coverage data.
            db.bulk_insert_line_sequences(conn, snapshot_id, line_seq_rows)
            db.bulk_insert_method_coverage(conn, snapshot_id, method_cov_rows)
            db.bulk_insert_class_coverage(conn, snapshot_id, class_cov_rows)
            db.bulk_insert_file_coverage(conn, snapshot_id, file_cov_rows)
            db.bulk_insert_package_coverage(conn, snapshot_id, pkg_cov_rows)

        return snapshot_id, codebase_id
    finally:
        conn.close()
