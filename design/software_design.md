# Parana – Software Design

## Overview

Parana is a coverage-tracking system built on top of JaCoCo.  It imports
JaCoCo XML reports into a relational database so that coverage levels can be
queried and compared across points in time.  The system supports multiple
independent codebases, each identified by its git remote origin URL.

---

## 1. Problem Summary

JaCoCo produces a snapshot of test coverage for a Java project at one moment in
time.  Parana gives each such snapshot a permanent home in a database and
enriches it with version-control metadata (git origin URL, git commit hash,
uncommitted-files hash, timestamp).  Once multiple snapshots exist, coverage
can be compared at the file, class, or method level between any two of them.
Because Parana supports multiple codebases, all structural entities (packages,
classes, methods) are scoped to their codebase so that identically-named
packages in different projects never conflict.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CI / developer machine                                                  │
│                                                                          │
│   mvn test  ──jacoco:report──►  jacoco.xml                               │
│                                      │                                  │
│                              Parana Importer  (Python)                   │
│                            ┌─────────────────┐                          │
│   gitpython: origin  ──────►  git_origin      │                          │
│   gitpython: HEAD    ──────►  git_commit_hash │                          │
│   gitpython: status  ──────►  uncommitted_    │                          │
│                               files_hash      │                          │
│   system clock       ──────►  captured_at     │                          │
│                            └────────┬────────┘                          │
│                                     │ psycopg                           │
└─────────────────────────────────────┼────────────────────────────────────┘
                                      │
                        ┌─────────────▼──────────────┐
                        │   Relational Database       │
                        │   (see design/schema.sql)   │
                        └─────────────┬──────────────┘
                                      │
                        ┌─────────────▼──────────────┐
                        │   REST API + Chat Service   │
                        │   (Python / FastAPI)        │
                        │                             │
                        │  • Coverage query endpoints │
                        │  • /chat  ── LLM ──► DB     │
                        └─────────────┬──────────────┘
                                      │ HTTP / REST
                        ┌─────────────▼──────────────┐
                        │   Frontend  (React / TS)    │
                        │   • Coverage display        │
                        │   • Chat interface          │
                        └─────────────────────────────┘
```

---

## 3. Components

### 3.1  Parana Importer  *(Python)*

**Responsibility:** parse a JaCoCo XML report and persist all its data into the
database in one atomic transaction.

**Inputs**
| Input | Source |
|---|---|
| JaCoCo XML file | File path supplied on the command line or via API |
| `git_origin` | `gitpython` — `Repo.remotes["origin"].url` from the project's `.git` directory |
| `git_commit_hash` | `gitpython` — `repo.head.commit.hexsha` (SHA-1 of the HEAD commit) |
| `git_branch` | `gitpython` — `repo.active_branch.name` — symbolic name of the current branch (e.g. `main`, `feature/foo`) |
| `uncommitted_files_hash` | Computed from the working tree via `gitpython` (see §3.1.1); the caller must supply the explicit value `CLEAN` for a clean working tree — there is no default |
| `captured_at` | UTC timestamp of the JaCoCo report generation, supplied by the caller; the importer must not rely on the database `CURRENT_TIMESTAMP` default, which would record insert time rather than report time |

**Processing steps**

1. **Parse XML** – Walk the JaCoCo `<report>` element to extract packages,
   source files, classes, methods, per-line data, and counter elements.
2. **Resolve codebase** – Look up or insert a `codebase` row for `git_origin`.
3. **Resolve references** – For each package / source-file / class / method,
   look up or insert the corresponding normalised row (`package`, `source_file`,
   `java_class`, `method` tables), scoped to the resolved `codebase_id`.  These
   rows are write-once; the same entity discovered in a later snapshot reuses
   the existing row.
4. **Create snapshot** – Insert one row into `coverage_snapshot` with
   `codebase_id`, `git_branch`, and the three version-control columns.  If a
   row with the same `(codebase_id, git_commit_hash, uncommitted_files_hash)`
   already exists the importer must return the existing snapshot ID and skip all
   subsequent writes (idempotent import).
5. **Import line sequences** – For each source file, convert the ordered list of
   `<line>` elements into sequences (see §3.1.2) and insert them into
   `line_coverage_sequence`.
6. **Import aggregate counters** – Insert one row per method into
   `method_coverage`, one row per class into `class_coverage`, and one row per
   source file into `file_coverage`, all referencing the new snapshot.
7. **Commit transaction** – All writes succeed or all are rolled back.

#### 3.1.1  Computing `uncommitted_files_hash`

The goal is a stable, reproducible identifier for the state of the working tree
that is *not* yet committed.  This includes both modified tracked files and any
untracked files that have not been explicitly ignored.

The importer uses the **gitpython** library (`git`) to query repository state
without requiring a `git` executable in the environment.

Algorithm:
1. Open the project's `.git` directory with `git.Repo(repo_path)`.
2. Obtain **modified / staged / deleted tracked files** via `repo.index.diff(None)` (unstaged) and `repo.index.diff("HEAD")` (staged).
3. Obtain **untracked files** from `repo.untracked_files` (respects `.gitignore`).
4. Combine both sets and sort deterministically (lexicographic order by path).
5. For each entry in the sorted list, concatenate:
   `<status_code> <path> <sha256_of_file_content>`.
   - For deleted tracked files the content hash is replaced by the fixed string
     `DELETED`.
   - For untracked files the status code is `?`.
6. Compute SHA-256 of the entire concatenated string.
7. If both sets in steps 2 and 3 are empty, store the constant string `CLEAN`
   instead of computing a hash.

#### 3.1.2  Line Sequence Algorithm

JaCoCo reports coverage per individual line via `<line mi="…" ci="…" mb="…" cb="…"/>` attributes.
Parana first maps each line to one of three statuses, then compresses consecutive
lines with the same status into a single sequence row.

**Coverage status derivation (per line) — maps to SMALLINT stored in DB:**
- `2` (COVERED) — all instructions executed: `ci > 0` and `mi = 0`, and either no branches exist or all are covered (`mb = 0`)
- `0` (NOT_COVERED) — no instructions executed: `ci = 0`
- `1` (PARTLY_COVERED) — some instructions or branches executed, some missed: `ci > 0` and (`mi > 0` or `mb > 0`)

**Sequence compression:**
```
sequences = []
current_seq = None

for each line in sorted order:
    status = derive_status(line)
    if current_seq is None:
        current_seq = new sequence starting at this line with status
    else if status == current_seq.status AND line.nr == current_seq.end_line + 1:
        extend current_seq.end_line to line.nr
    else:
        flush current_seq to sequences
        current_seq = new sequence starting at this line with status

if current_seq is not None:
    flush current_seq to sequences
```

Precise numeric counters (missed/covered instructions, branches, complexity)
are stored separately at method, class, and file granularity in the aggregate
tables.

---

### 3.2  REST API & Chat Service  *(Python / FastAPI)*

**Responsibility:** expose coverage data over HTTP REST endpoints and provide a
natural-language chat interface that allows users to query the database in plain
English.

#### 3.2.1  Coverage REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/codebases` | List all tracked codebases |
| `GET` | `/codebases/{id}/snapshots` | List snapshots for a codebase (supports `?limit=` and `?offset=`) |
| `GET` | `/snapshots/{id}` | Get details of a single snapshot |
| `GET` | `/compare` | Compare two snapshots — query params: `before`, `after`, `level` (`file`/`class`/`method`), optional `filter` |

#### 3.2.2  Chat Endpoint

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat` | Accept a plain-English question, translate it via LLM to the appropriate REST endpoint call or SQL query, execute it, and stream the response as Server-Sent Events |

**Chat flow:**

1. The frontend `POST /chat` with `{ session_id, message }`.
2. The backend sends the message and the available API schema to an LLM to
   determine which endpoint(s) or query to invoke.
3. The backend executes the resolved endpoint call or database query.
4. The raw result is sent to a second LLM call together with the original
   question to decide how to render the response (table, text summary, etc.).
5. The backend streams the final answer back as `text/event-stream` SSE chunks
   with typed events: `text_delta`, `result`, `done`, `error`.

#### 3.2.3  Comparison Input

| Parameter | Description |
|---|---|
| `before` | ID (or git commit hash) of the earlier snapshot |
| `after` | ID (or git commit hash) of the later snapshot |
| `level` | One of `file`, `class`, or `method` |
| `filter` (optional) | Restrict results to a specific package, class, or file |

#### 3.2.4  Comparison Output (one row per entity)

| Column | Description |
|---|---|
| `entity_name` | Fully-qualified name of the entity |
| `covered_lines_before` | Covered lines in `before` snapshot |
| `covered_lines_after` | Covered lines in `after` snapshot |
| `delta_covered_lines` | `after - before` |
| `covered_branches_before` | Covered branches in `before` snapshot |
| `covered_branches_after` | Covered branches in `after` snapshot |
| `delta_covered_branches` | `after - before` |
| `coverage_pct_before` | `covered / (covered + missed)` for lines |
| `coverage_pct_after` | Same for `after` snapshot |
| `delta_coverage_pct` | `after - before` |

Only entities present in **both** snapshots are returned.  Files, classes, or
methods that were added or deleted between the two snapshots are excluded from
the comparison result.

#### 3.2.5  Comparison Queries

The service executes the pre-defined SQL patterns shown at the bottom of
`design/schema.sql`.  At each level an `INNER JOIN` on the entity key between
the two snapshots' coverage rows is used, which naturally restricts results to
entities that exist in both snapshots:

- **File level** – join on `file_coverage.source_file_id`
- **Class level** – join on `class_coverage.class_id`
- **Method level** – join on `method_coverage.method_id`

---

## 4. Database Schema Summary

Full DDL is in `design/schema.sql`.  The entity-relationship diagram below
shows how the tables relate to one another.

```
codebase
    │
    ├──(1:N)── package ──(1:N)── source_file ──(1:N)── java_class ──(1:N)── method
    │
    └──(1:N)── coverage_snapshot
                    │
                    ├──(1:N)── line_coverage_sequence ──(N:1)── source_file
                    ├──(1:N)── file_coverage          ──(N:1)── source_file
                    ├──(1:N)── class_coverage         ──(N:1)── java_class
                    ├──(1:N)── method_coverage        ──(N:1)── method
                    └──(1:N)── package_coverage       ──(N:1)── package
```

### Key design decisions

| Decision | Rationale |
|---|---|
| `codebase` table keyed on `git_origin` | Uniquely identifies each project; scopes all structural entities so identical package/class names in different repos never collide |
| Table named `java_class` rather than `class` | `CLASS` is a reserved word in standard SQL and most database dialects; prefixing avoids quoting every reference |
| Normalise `package`, `source_file`, `java_class`, `method` as write-once lookup tables scoped to `codebase` | Avoids duplicating large strings in every snapshot; enables cross-snapshot JOIN on stable IDs |
| `java_class.name` unique per `source_file_id`, not globally | The same fully-qualified class name can exist in multiple repositories; the uniqueness scope must be `(source_file_id, name)` to prevent cross-repo collisions |
| Store line data as status-based sequences with `SMALLINT` constants | A sequence is a run of consecutive lines sharing the same status (0/1/2); integers save storage and avoid case-sensitivity issues across dialects |
| Store aggregate counters in separate tables (`package_coverage`, `file_coverage`, `class_coverage`, `method_coverage`) | Comparison queries run against small aggregate rows without needing to re-aggregate sequences |
| Four version-control columns on `coverage_snapshot` (`git_branch`, `git_commit_hash`, `uncommitted_files_hash`, `captured_at`) | `git_branch` enables branch-scoped queries (e.g. find the latest snapshot on `main`); commit hash identifies clean builds; uncommitted hash distinguishes dirty working trees; wall-clock timestamp allows ordering |
| `UNIQUE (codebase_id, git_commit_hash, uncommitted_files_hash)` on `coverage_snapshot` | Prevents duplicate snapshots from CI retries; makes import idempotent — re-importing the same report returns the existing snapshot ID |
| `uncommitted_files_hash` has no database default | Forcing the importer to supply an explicit value (including the string `CLEAN`) prevents a missing computation from being silently recorded as a clean state |
| `captured_at` supplied by caller, not by `CURRENT_TIMESTAMP` default | The timestamp should reflect when the JaCoCo report was generated, not when the row was inserted; batch or queued imports can differ significantly |
| `uncommitted_files_hash` includes untracked files | Untracked source files can affect test results just as much as modified tracked files; omitting them would produce identical hashes for different working trees |
| Use `gitpython` rather than `git` CLI subprocess | `gitpython` reads the `.git` directory directly; no `git` executable is required in the runtime environment, avoiding process-launch overhead and PATH dependencies |
| `ON DELETE CASCADE` on all snapshot foreign keys | Simplifies snapshot purging: deleting a `coverage_snapshot` row removes all associated data |

---

## 5. Data Flow Diagram

```
jacoco.xml
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  XML Parser  (lxml / iterparse)                     │
│  • Streaming parser for large reports               │
│  • Emits: Package, SourceFile, Class, Method,       │
│           Line[], Counter[] events                  │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Reference Resolver                                 │
│  • Upsert codebase (keyed on git_origin via         │
│    gitpython)                                       │
│  • Upsert package / source_file / java_class /      │
│    method (all scoped to codebase_id)               │
│  • Returns stable database IDs                      │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Snapshot Writer                                    │
│  • Creates coverage_snapshot row                    │
│  • Derives status per line (0/1/2), runs            │
│    sequence-compression                             │
│  • Bulk-inserts line_coverage_sequence rows         │
│  • Bulk-inserts method/class/file coverage rows     │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
                    Relational Database
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  REST API + Chat Service  (FastAPI)                 │
│  • Coverage query endpoints                         │
│  • POST /chat ──► LLM (intent resolution)           │
│                   ──► DB query / endpoint call      │
│                   ──► LLM (render decision)         │
│                   ──► SSE stream to frontend        │
└──────────────────────────┬──────────────────────────┘
                           │ HTTP / SSE
                           ▼
                    Frontend  (React / TS)
```

---

## 6. Assumptions and Constraints

1. A single JaCoCo XML report is produced per import run; multiple modules
   should be merged into one report before importing (JaCoCo supports this via
   the `merge` goal).  The importer validates that the input contains exactly
   one `<report>` root element and rejects files with multiple roots with a
   descriptive error, rather than silently importing a partial report.
2. The importer uses **gitpython** (`git`) to read repository metadata
   (remote origin, HEAD commit, working-tree status, untracked files).  No
   `git` executable is required in the runtime environment.
3. The project root must contain a `.git` directory (bare repositories are not
   supported).  The `origin` remote must have a push or fetch URL configured.
4. The schema is written in standard SQL-2003 (`GENERATED ALWAYS AS IDENTITY`).
   Minor dialect adjustments (e.g., `SERIAL` for PostgreSQL, `AUTO_INCREMENT`
   for MySQL) may be needed.
5. All timestamps are stored in UTC.
6. Counter columns use INT (32-bit).  Projects with more than ~2 billion
   instructions per file should switch these to BIGINT.
