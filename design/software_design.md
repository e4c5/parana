# Parana – Software Design

## Overview

Parana is a coverage-tracking system built on top of JaCoCo.  It imports
JaCoCo XML reports into a relational database so that coverage levels can be
queried and compared across points in time.

---

## 1. Problem Summary

JaCoCo produces a snapshot of test coverage for a Java project at one moment in
time.  Parana gives each such snapshot a permanent home in a database and
enriches it with version-control metadata (git commit hash, uncommitted-files
hash, timestamp).  Once multiple snapshots exist, coverage can be compared at
the file, class, or method level between any two of them.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CI / developer machine                                                  │
│                                                                          │
│   mvn test  ──jacoco:report──►  jacoco.xml                               │
│                                      │                                  │
│                              Parana Importer                             │
│                            ┌─────────────────┐                          │
│   git rev-parse HEAD ──────►  git_commit_hash │                          │
│   git status / hash   ─────►  uncommitted_    │                          │
│                              files_hash       │                          │
│   system clock        ─────►  captured_at     │                          │
│                            └────────┬────────┘                          │
│                                     │ JDBC / ORM                        │
└─────────────────────────────────────┼────────────────────────────────────┘
                                      │
                        ┌─────────────▼──────────────┐
                        │   Relational Database       │
                        │   (see design/schema.sql)   │
                        └─────────────┬──────────────┘
                                      │
                        ┌─────────────▼──────────────┐
                        │   Comparison Service        │
                        │   (file / class / method)   │
                        └─────────────────────────────┘
```

---

## 3. Components

### 3.1  Parana Importer

**Responsibility:** parse a JaCoCo XML report and persist all its data into the
database in one atomic transaction.

**Inputs**
| Input | Source |
|---|---|
| JaCoCo XML file | File path supplied on the command line or via API |
| `git_commit_hash` | Output of `git rev-parse HEAD` run in the project root |
| `uncommitted_files_hash` | Computed from the working tree (see §3.1.1) |
| `captured_at` | Current UTC timestamp at import time |

**Processing steps**

1. **Parse XML** – Walk the JaCoCo `<report>` element to extract packages,
   source files, classes, methods, per-line data, and counter elements.
2. **Resolve references** – For each package / source-file / class / method,
   look up or insert the corresponding normalised row (`package`, `source_file`,
   `class`, `method` tables).  These rows are write-once; the same entity
   discovered in a later snapshot reuses the existing row.
3. **Create snapshot** – Insert one row into `coverage_snapshot` with the three
   version-control columns plus `report_name`.
4. **Import line sequences** – For each source file, convert the ordered list of
   `<line>` elements into sequences (see §3.1.2) and insert them into
   `line_coverage_sequence`.
5. **Import aggregate counters** – Insert one row per method into
   `method_coverage`, one row per class into `class_coverage`, and one row per
   source file into `file_coverage`, all referencing the new snapshot.
6. **Commit transaction** – All writes succeed or all are rolled back.

#### 3.1.1  Computing `uncommitted_files_hash`

The goal is a stable, reproducible identifier for the state of the working tree
that is *not* yet committed.

Algorithm:
1. Run `git status --porcelain` to list modified, added, or deleted tracked
   files.
2. Sort the list deterministically (lexicographic order by path).
3. For each file in the sorted list, concatenate: `<status_code> <path> <sha256_of_file_content>`.
   For deleted files the content hash is replaced by the fixed string `DELETED`.
4. Compute SHA-256 of the entire concatenated string.
5. If the working tree is clean (no output from step 1), store the constant
   string `CLEAN` (or an empty string) instead of computing a hash.

#### 3.1.2  Line Sequence Algorithm

JaCoCo reports coverage per individual line.  Parana compresses consecutive
lines with identical counter values into a single sequence row.

```
sequences = []
current_seq = None

for each line in sorted order:
    if current_seq is None:
        current_seq = new sequence starting at this line
    else if line counters == current_seq counters AND line.nr == current_seq.end_line + 1:
        extend current_seq.end_line to line.nr
    else:
        flush current_seq to sequences
        current_seq = new sequence starting at this line

if current_seq is not None:
    flush current_seq to sequences
```

Two lines are considered to have "identical counter values" when their
`missed_instructions`, `covered_instructions`, `missed_branches`, and
`covered_branches` values are all equal.

---

### 3.2  Comparison Service

**Responsibility:** given two snapshot identifiers, produce a structured
comparison of coverage at the requested granularity level.

#### 3.2.1  Input

| Parameter | Description |
|---|---|
| `snapshot_before` | ID (or git commit hash) of the earlier snapshot |
| `snapshot_after` | ID (or git commit hash) of the later snapshot |
| `level` | One of `FILE`, `CLASS`, or `METHOD` |
| `filter` (optional) | Restrict results to a specific package, class, or file |

#### 3.2.2  Output (one row per entity)

| Column | Description |
|---|---|
| `entity_name` | Fully-qualified name of the entity |
| `covered_lines_before` | Covered lines in `snapshot_before` |
| `covered_lines_after` | Covered lines in `snapshot_after` |
| `delta_covered_lines` | `after - before` |
| `covered_branches_before` | Covered branches in `snapshot_before` |
| `covered_branches_after` | Covered branches in `snapshot_after` |
| `delta_covered_branches` | `after - before` |
| `coverage_pct_before` | `covered / (covered + missed)` for lines |
| `coverage_pct_after` | Same for `snapshot_after` |
| `delta_coverage_pct` | `after - before` |

Entities present in one snapshot but absent from the other (new or deleted
files/classes/methods) are included with `NULL` counters for the missing side.

#### 3.2.3  Comparison Queries

The service executes the pre-defined SQL patterns shown at the bottom of
`design/schema.sql`.  At each level a `FULL OUTER JOIN` on the entity key
between the two snapshots' coverage rows is used so that added and deleted
entities are captured:

- **File level** – join on `file_coverage.source_file_id`
- **Class level** – join on `class_coverage.class_id`
- **Method level** – join on `method_coverage.method_id`

---

## 4. Database Schema Summary

Full DDL is in `design/schema.sql`.  The entity-relationship diagram below
shows how the tables relate to one another.

```
coverage_snapshot
    │
    ├──(1:N)── line_coverage_sequence ──(N:1)── source_file ──(N:1)── package
    ├──(1:N)── file_coverage          ──(N:1)── source_file
    ├──(1:N)── class_coverage         ──(N:1)── class ──────(N:1)── source_file
    └──(1:N)── method_coverage        ──(N:1)── method ─────(N:1)── class
```

### Key design decisions

| Decision | Rationale |
|---|---|
| Normalise `package`, `source_file`, `class`, `method` as write-once lookup tables | Avoids duplicating large strings in every snapshot; enables cross-snapshot JOIN on stable IDs |
| Store line data as sequences, not individual lines | Reduces row count significantly for typical source files while preserving all information |
| Store aggregate counters in separate tables (`file_coverage`, `class_coverage`, `method_coverage`) | Comparison queries run against small aggregate rows without needing to re-aggregate sequences |
| Three separate version-control columns on `coverage_snapshot` | Allows querying by commit hash alone (clean builds), filtering by uncommitted-state hash, or ordering by wall-clock time |
| `ON DELETE CASCADE` on all snapshot foreign keys | Simplifies snapshot purging: deleting a `coverage_snapshot` row removes all associated data |

---

## 5. Data Flow Diagram

```
jacoco.xml
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  XML Parser                                         │
│  • SAX/StAX streaming parser for large reports      │
│  • Emits: Package, SourceFile, Class, Method,       │
│           Line[], Counter[] events                  │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Reference Resolver                                 │
│  • Upsert package / source_file / class / method    │
│  • Returns stable database IDs                      │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────┐
│  Snapshot Writer                                    │
│  • Creates coverage_snapshot row                    │
│  • Runs line-sequence algorithm                     │
│  • Bulk-inserts line_coverage_sequence rows         │
│  • Bulk-inserts method/class/file coverage rows     │
└──────────────────────────┬──────────────────────────┘
                           │
                           ▼
                    Relational Database
```

---

## 6. Assumptions and Constraints

1. A single JaCoCo XML report is produced per import run; multiple modules
   should be merged into one report before importing (JaCoCo supports this via
   the `merge` goal).
2. The `git` executable must be available in the environment where the importer
   runs so that commit and working-tree information can be retrieved.
3. The schema is written in standard SQL-2003 (`GENERATED ALWAYS AS IDENTITY`).
   Minor dialect adjustments (e.g., `SERIAL` for PostgreSQL, `AUTO_INCREMENT`
   for MySQL) may be needed.
4. All timestamps are stored in UTC.
5. Counter columns use INT (32-bit).  Projects with more than ~2 billion
   instructions per file should switch these to BIGINT.
