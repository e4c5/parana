"""CLI entry point for the Parana coverage importer.

Usage::

    parana-import --xml path/to/jacoco.xml --repo /path/to/project [--dsn DSN]
    parana-import --xml coverage.xml --format cobertura --repo . [--dsn DSN]

The report format is auto-detected from the XML root element unless
``--format`` is given.

The ``DATABASE_URL`` environment variable (loaded from a ``.env`` file if
present) is used as the fallback DSN when ``--dsn`` is not provided.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

import click
from dotenv import load_dotenv

from .formats import SUPPORTED_FORMATS

load_dotenv()


@click.command()
@click.option(
    "--xml",
    "xml_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the coverage report file (JaCoCo or Cobertura XML).",
)
@click.option(
    "--format",
    "report_format",
    type=click.Choice(SUPPORTED_FORMATS, case_sensitive=False),
    default=None,
    help="Report format. Auto-detected from the XML root element when omitted.",
)
@click.option(
    "--repo",
    "repo_path",
    required=True,
    type=click.Path(exists=True, file_okay=False),
    help="Root directory of the project's git repository.",
)
@click.option(
    "--dsn",
    "dsn",
    envvar="DATABASE_URL",
    required=True,
    help="psycopg DSN / URI for the Parana database (or set DATABASE_URL).",
)
@click.option(
    "--captured-at",
    "captured_at_str",
    default=None,
    help=(
        "UTC timestamp of the report generation in ISO-8601 format "
        "(e.g. '2024-01-15T12:00:00').  Defaults to the current time."
    ),
)
def main(
    xml_path: str,
    report_format: str | None,
    repo_path: str,
    dsn: str,
    captured_at_str: str | None,
) -> None:
    """Import a coverage report (JaCoCo or Cobertura XML) into the Parana database."""
    # Lazy import to keep startup fast and avoid import errors surfacing as
    # unformatted tracebacks when the user just runs ``parana-import --help``.
    from .importer import run_import

    captured_at: datetime | None = None
    if captured_at_str is not None:
        try:
            parsed = datetime.fromisoformat(captured_at_str)
            if parsed.tzinfo is not None:
                captured_at = parsed.astimezone(timezone.utc)
            else:
                captured_at = parsed.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            click.echo(f"Error: invalid --captured-at value: {exc}", err=True)
            sys.exit(1)

    try:
        snapshot_id, codebase_id = run_import(
            xml_path=xml_path,
            repo_path=repo_path,
            dsn=dsn,
            captured_at=captured_at,
            report_format=report_format.lower() if report_format else None,
        )
    except Exception as exc:  # noqa: BLE001
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Imported snapshot #{snapshot_id} for codebase #{codebase_id}")
