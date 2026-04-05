-- =============================================================================
-- Parana – JaCoCo Coverage Tracking Schema
-- =============================================================================
-- Design goals
--   • The system supports multiple independent codebases.  Each codebase is
--     identified by its git remote origin URL.
--   • Every snapshot captures the full JaCoCo XML for one run of the test suite
--     against a specific codebase.
--   • A snapshot is uniquely tied to a point in time via three columns:
--       git_commit_hash       – SHA-1 of the HEAD commit at measurement time
--       uncommitted_files_hash – deterministic hash of every modified tracked
--                                file AND every untracked file present in the
--                                working tree at measurement time
--       captured_at           – UTC wall-clock timestamp of the measurement
--   • Line-level data is stored as *sequences* of consecutive lines that share
--     the same coverage status, rather than one row per line.  A sequence of
--     length 1 (start_line = end_line) is valid and common.
--   • Aggregate counters (at file, class, and method level) are stored
--     separately to support fast comparison queries without re-aggregating
--     line sequences.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1.  Codebase  (one row per tracked repository)
-- ---------------------------------------------------------------------------
CREATE TABLE codebase (
    id          BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Remote origin URL of the git repository, e.g.
    -- "https://github.com/example/myproject.git".
    -- This is the stable identifier that ties all snapshots and structural
    -- entities (packages, classes, methods) to one codebase.
    git_origin  VARCHAR(512) NOT NULL UNIQUE
);


-- ---------------------------------------------------------------------------
-- 2.  Snapshot  (one row per JaCoCo report import)
-- ---------------------------------------------------------------------------
CREATE TABLE coverage_snapshot (
    id                      BIGINT      NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The codebase this snapshot belongs to.
    codebase_id             BIGINT      NOT NULL REFERENCES codebase (id),
    -- The SHA-1 hash of the git HEAD commit at the time the report was captured.
    git_commit_hash         CHAR(40)    NOT NULL,
    -- A deterministic hash (e.g. SHA-256) computed from the sorted list of
    -- paths + content-hashes of every file that is modified (tracked, staged,
    -- or unstaged) OR untracked at measurement time.  The constant 'CLEAN'
    -- indicates a clean working tree with no untracked files.
    uncommitted_files_hash  VARCHAR(64) NOT NULL DEFAULT 'CLEAN',
    -- UTC timestamp when the JaCoCo report was imported.
    captured_at             TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_snapshot_codebase ON coverage_snapshot (codebase_id);
CREATE INDEX idx_snapshot_commit   ON coverage_snapshot (git_commit_hash);
CREATE INDEX idx_snapshot_time     ON coverage_snapshot (captured_at);


-- ---------------------------------------------------------------------------
-- 3.  Package  (Java package – normalised lookup table, scoped to codebase)
-- ---------------------------------------------------------------------------
CREATE TABLE package (
    id          BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The codebase that owns this package.  The same package name (e.g.
    -- "com/example/service") can exist in multiple codebases without collision.
    codebase_id BIGINT       NOT NULL REFERENCES codebase (id),
    -- Package name in JVM slash-separated form, e.g. "com/example/service".
    name        VARCHAR(512) NOT NULL,
    UNIQUE (codebase_id, name)
);

CREATE INDEX idx_package_codebase ON package (codebase_id);


-- ---------------------------------------------------------------------------
-- 4.  Source file  (one row per unique <sourcefile> across all packages)
-- ---------------------------------------------------------------------------
CREATE TABLE source_file (
    id          BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    package_id  BIGINT       NOT NULL REFERENCES package (id),
    -- File name as it appears in the JaCoCo XML, e.g. "UserService.java".
    name        VARCHAR(255) NOT NULL,
    UNIQUE (package_id, name)
);

CREATE INDEX idx_source_file_package ON source_file (package_id);


-- ---------------------------------------------------------------------------
-- 5.  Class  (one row per unique <class> across all source files)
-- ---------------------------------------------------------------------------
CREATE TABLE class (
    id             BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_file_id BIGINT       NOT NULL REFERENCES source_file (id),
    -- Fully-qualified class name in JVM form, e.g. "com/example/service/UserService".
    name           VARCHAR(512) NOT NULL UNIQUE
);

CREATE INDEX idx_class_source_file ON class (source_file_id);


-- ---------------------------------------------------------------------------
-- 6.  Method  (one row per unique <method> within a class)
-- ---------------------------------------------------------------------------
CREATE TABLE method (
    id          BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    class_id    BIGINT       NOT NULL REFERENCES class (id),
    -- Method simple name, e.g. "findById".
    name        VARCHAR(255) NOT NULL,
    -- JVM method descriptor, e.g. "(Ljava/lang/Long;)Ljava/util/Optional;".
    descriptor  VARCHAR(512) NOT NULL,
    -- First source line of the method as reported by JaCoCo.
CREATE INDEX idx_method_start_line ON method (start_line);
    UNIQUE (class_id, name, descriptor)
);

CREATE INDEX idx_method_class ON method (class_id);


-- ---------------------------------------------------------------------------
-- 7.  Line coverage sequence
--
--     Core line-level data.  Instead of storing one row per line number,
--     consecutive lines that share the same coverage *status* are collapsed
--     into a single sequence row (start_line … end_line).  A sequence of
--     length 1 is represented as start_line = end_line.
--
--     Coverage status values (matching JaCoCo's HTML colour coding):
--       COVERED        – every instruction on every line was executed
--                        (covered_instructions > 0, missed_instructions = 0,
--                         and any branches present are fully covered)
--       NOT_COVERED    – no instruction on any line was executed
--                        (covered_instructions = 0)
--       PARTLY_COVERED – at least one instruction or branch was missed but at
--                        least one was also executed
--
--     Rationale: large source files typically have long runs of lines in the
--     same status (e.g. an entire fully-covered method body); sequences reduce
--     row count while preserving actionable line-range information.  Precise
--     numeric counters (missed_instructions, covered_branches, etc.) are
--     captured at method / class / file level in the aggregate tables below.
-- ---------------------------------------------------------------------------
CREATE TABLE line_coverage_sequence (
    id              BIGINT      NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id     BIGINT      NOT NULL REFERENCES coverage_snapshot (id) ON DELETE CASCADE,
    source_file_id  BIGINT      NOT NULL REFERENCES source_file (id),
    -- First line number of the sequence (1-based, matching JaCoCo <line nr="…">).
    start_line      INT         NOT NULL,
    -- Last line number of the sequence.  start_line = end_line for length-1 sequences.
    end_line        INT         NOT NULL,
    -- Coverage status shared by every line in this sequence.
    coverage_status VARCHAR(16) NOT NULL,
    CONSTRAINT chk_line_range     CHECK (end_line >= start_line),
    CONSTRAINT chk_coverage_status CHECK (coverage_status IN ('COVERED', 'NOT_COVERED', 'PARTLY_COVERED'))
);

CREATE INDEX idx_lcs_snapshot      ON line_coverage_sequence (snapshot_id);
CREATE INDEX idx_lcs_source_file   ON line_coverage_sequence (source_file_id);
CREATE INDEX idx_lcs_snap_file     ON line_coverage_sequence (snapshot_id, source_file_id);


-- ---------------------------------------------------------------------------
-- 8.  Method coverage  (aggregate counters per method per snapshot)
-- ---------------------------------------------------------------------------
CREATE TABLE method_coverage (
    id                    BIGINT  NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id           BIGINT  NOT NULL REFERENCES coverage_snapshot (id) ON DELETE CASCADE,
    method_id             BIGINT  NOT NULL REFERENCES method (id),
    missed_instructions   INT     NOT NULL DEFAULT 0,
    covered_instructions  INT     NOT NULL DEFAULT 0,
    missed_branches       INT     NOT NULL DEFAULT 0,
    covered_branches      INT     NOT NULL DEFAULT 0,
    missed_lines          INT     NOT NULL DEFAULT 0,
    covered_lines         INT     NOT NULL DEFAULT 0,
    missed_complexity     INT     NOT NULL DEFAULT 0,
    covered_complexity    INT     NOT NULL DEFAULT 0,
    UNIQUE (snapshot_id, method_id)
);

CREATE INDEX idx_method_cov_snapshot ON method_coverage (snapshot_id);
CREATE INDEX idx_method_cov_method   ON method_coverage (method_id);


-- ---------------------------------------------------------------------------
-- 9.  Class coverage  (aggregate counters per class per snapshot)
-- ---------------------------------------------------------------------------
CREATE TABLE class_coverage (
    id                    BIGINT  NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id           BIGINT  NOT NULL REFERENCES coverage_snapshot (id) ON DELETE CASCADE,
    class_id              BIGINT  NOT NULL REFERENCES class (id),
    missed_instructions   INT     NOT NULL DEFAULT 0,
    covered_instructions  INT     NOT NULL DEFAULT 0,
    missed_branches       INT     NOT NULL DEFAULT 0,
    covered_branches      INT     NOT NULL DEFAULT 0,
    missed_lines          INT     NOT NULL DEFAULT 0,
    covered_lines         INT     NOT NULL DEFAULT 0,
    missed_complexity     INT     NOT NULL DEFAULT 0,
    covered_complexity    INT     NOT NULL DEFAULT 0,
    missed_methods        INT     NOT NULL DEFAULT 0,
    covered_methods       INT     NOT NULL DEFAULT 0,
    UNIQUE (snapshot_id, class_id)
);

CREATE INDEX idx_class_cov_snapshot ON class_coverage (snapshot_id);
CREATE INDEX idx_class_cov_class    ON class_coverage (class_id);


-- ---------------------------------------------------------------------------
-- 10.  File coverage  (aggregate counters per source file per snapshot)
-- ---------------------------------------------------------------------------
CREATE TABLE file_coverage (
    id                    BIGINT  NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id           BIGINT  NOT NULL REFERENCES coverage_snapshot (id) ON DELETE CASCADE,
    source_file_id        BIGINT  NOT NULL REFERENCES source_file (id),
    missed_instructions   INT     NOT NULL DEFAULT 0,
    covered_instructions  INT     NOT NULL DEFAULT 0,
    missed_branches       INT     NOT NULL DEFAULT 0,
    covered_branches      INT     NOT NULL DEFAULT 0,
    missed_lines          INT     NOT NULL DEFAULT 0,
    covered_lines         INT     NOT NULL DEFAULT 0,
    missed_complexity     INT     NOT NULL DEFAULT 0,
    covered_complexity    INT     NOT NULL DEFAULT 0,
    missed_methods        INT     NOT NULL DEFAULT 0,
    covered_methods       INT     NOT NULL DEFAULT 0,
    missed_classes        INT     NOT NULL DEFAULT 0,
    covered_classes       INT     NOT NULL DEFAULT 0,
    UNIQUE (snapshot_id, source_file_id)
);

CREATE INDEX idx_file_cov_snapshot    ON file_coverage (snapshot_id);
CREATE INDEX idx_file_cov_source_file ON file_coverage (source_file_id);


-- =============================================================================
-- Example comparison queries
-- =============================================================================

-- --- A) Compare file-level line coverage between two snapshots ---------------
--
-- SELECT
--     sf.name                                              AS file,
--     p.name                                               AS package,
--     a.covered_lines                                      AS covered_lines_before,
--     b.covered_lines                                      AS covered_lines_after,
--     b.covered_lines - a.covered_lines                    AS delta_covered_lines,
--     a.covered_lines + a.missed_lines                     AS total_lines_before,
--     b.covered_lines + b.missed_lines                     AS total_lines_after
-- FROM       file_coverage  a
-- JOIN       file_coverage  b  ON b.source_file_id = a.source_file_id
-- JOIN       source_file    sf ON sf.id = a.source_file_id
-- JOIN       package        p  ON p.id  = sf.package_id
-- WHERE      a.snapshot_id = :snapshot_id_before
--   AND      b.snapshot_id = :snapshot_id_after
-- ORDER BY   delta_covered_lines;


-- --- B) Compare class-level coverage between two snapshots -------------------
--
-- SELECT
--     c.name                                               AS class,
--     a.covered_lines                                      AS covered_lines_before,
--     b.covered_lines                                      AS covered_lines_after,
--     b.covered_lines - a.covered_lines                    AS delta_covered_lines,
--     a.covered_branches                                   AS covered_branches_before,
--     b.covered_branches                                   AS covered_branches_after
-- FROM       class_coverage  a
-- JOIN       class_coverage  b  ON b.class_id = a.class_id
-- JOIN       class           c  ON c.id = a.class_id
-- WHERE      a.snapshot_id = :snapshot_id_before
--   AND      b.snapshot_id = :snapshot_id_after
-- ORDER BY   c.name;


-- --- C) Compare method-level coverage between two snapshots ------------------
--
-- SELECT
--     c.name                                               AS class,
--     m.name                                               AS method,
--     m.descriptor                                         AS descriptor,
--     a.covered_lines                                      AS covered_lines_before,
--     b.covered_lines                                      AS covered_lines_after,
--     b.covered_lines - a.covered_lines                    AS delta_covered_lines
-- FROM       method_coverage  a
-- JOIN       method_coverage  b  ON b.method_id = a.method_id
-- JOIN       method           m  ON m.id = a.method_id
-- JOIN       class            c  ON c.id = m.class_id
-- WHERE      a.snapshot_id = :snapshot_id_before
--   AND      b.snapshot_id = :snapshot_id_after
-- ORDER BY   c.name, m.name;
