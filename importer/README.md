# Parana Importer

The Parana Importer is a Python-based utility designed to parse JaCoCo XML coverage reports and persist the data into the Parana PostgreSQL database. It enriches coverage data with Git metadata (commit hash, branch, and working-tree status) to enable historical tracking and comparison of coverage across different points in time.

## Features

- **Efficient Parsing:** Uses `lxml.etree.iterparse` for streaming, memory-efficient processing of large JaCoCo reports.
- **Git Integration:** Automatically resolves Git origin URL, commit hash, and branch.
- **Working-Tree Fingerprinting:** Computes a deterministic `uncommitted_files_hash` to distinguish coverage snapshots taken with local changes.
- **Line Compression:** Collapses consecutive lines with identical coverage status into sequences to optimize database storage.
- **Atomic & Idempotent:** Imports are performed within a single database transaction and are idempotent; re-importing the same state will not create duplicate snapshots.

## Requirements

- Python 3.12+
- PostgreSQL (or a compatible database like TimescaleDB)

## Installation

This project uses `uv` for dependency management.

```bash
# Clone the repository
cd parana/importer

# Install dependencies and create a virtual environment
# For development and running tests, include the 'dev' extra:
uv sync --extra dev
```

## Usage

The importer provides a CLI entry point named `parana-import`.

### Database Setup

The importer uses `yoyo-migrations` to manage the database schema. You must run the migrations explicitly before the first import or whenever the schema changes:

```bash
# Run pending migrations
uv run parana-import migrate --dsn "postgresql://user:password@localhost:5432/parana"
```

### Basic CLI usage

The importer provides a CLI entry point named `parana-import`. It has two main subcommands: `import` and `migrate`.

```bash
# Basic import usage
uv run parana-import import --xml path/to/jacoco.xml --repo /path/to/project --dsn "postgresql://user:password@localhost:5432/parana"

# Using a .env file for the DSN
# Create a .env file with: DATABASE_URL=postgresql://user:password@localhost:5432/parana
uv run parana-import import --xml path/to/jacoco.xml --repo /path/to/project
```

### Options

- `--xml`: (Required) Path to the JaCoCo XML report file.
- `--repo`: (Required) Root directory of the Java project's git repository.
- `--dsn`: PostgreSQL connection string. Defaults to the `DATABASE_URL` environment variable.
- `--captured-at`: (Optional) ISO-8601 timestamp for the report. Defaults to current UTC time.

## Development

### Running Tests

Tests are located in the `tests/` directory and use `pytest`. Integration tests require Docker to run a PostgreSQL container via `testcontainers`.

**Note for Podman Users:** If you are using Podman instead of Docker, you may need to disable the Testcontainers "Ryuk" reaper to avoid connection issues:

```bash
# Run all tests (Podman compatible)
TESTCONTAINERS_RYUK_DISABLED=true uv run pytest
```

Otherwise, run with standard `uv`:

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=parana_importer
```

### Project Structure

- `src/parana_importer/`
  - `cli.py`: Command-line interface definition.
  - `importer.py`: Orchestrates the import process.
  - `parser.py`: Streaming XML parser logic.
  - `db.py`: Database access and schema management.
  - `git_meta.py`: Git metadata resolution using `gitpython`.
  - `sequences.py`: Line sequence compression algorithm.
  - `models.py`: Data structures for in-memory report representation.
  - `migrations/`: Directory containing versioned SQL migrations.
