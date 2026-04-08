from yoyo import step

__depends__ = {}

step(
    """
    -- 1. Codebase
    CREATE TABLE IF NOT EXISTS codebase (
        id          BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        git_origin  VARCHAR(512) NOT NULL UNIQUE
    );

    -- 2. Snapshot
    CREATE TABLE IF NOT EXISTS coverage_snapshot (
        id                      BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        codebase_id             BIGINT       NOT NULL REFERENCES codebase (id),
        git_branch              VARCHAR(255) NOT NULL,
        git_commit_hash         CHAR(40)     NOT NULL,
        uncommitted_files_hash  VARCHAR(64)  NOT NULL,
        captured_at             TIMESTAMP    NOT NULL,
        UNIQUE (codebase_id, git_commit_hash, uncommitted_files_hash)
    );

    CREATE INDEX IF NOT EXISTS idx_snapshot_codebase ON coverage_snapshot (codebase_id);
    CREATE INDEX IF NOT EXISTS idx_snapshot_branch   ON coverage_snapshot (codebase_id, git_branch);
    CREATE INDEX IF NOT EXISTS idx_snapshot_commit   ON coverage_snapshot (git_commit_hash);
    CREATE INDEX IF NOT EXISTS idx_snapshot_time     ON coverage_snapshot (captured_at);

    -- 3. Package
    CREATE TABLE IF NOT EXISTS package (
        id          BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        codebase_id BIGINT       NOT NULL REFERENCES codebase (id),
        name        VARCHAR(512) NOT NULL,
        UNIQUE (codebase_id, name)
    );

    CREATE INDEX IF NOT EXISTS idx_package_codebase ON package (codebase_id);

    -- 4. Source file
    CREATE TABLE IF NOT EXISTS source_file (
        id          BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        package_id  BIGINT       NOT NULL REFERENCES package (id),
        name        VARCHAR(255) NOT NULL,
        UNIQUE (package_id, name)
    );

    CREATE INDEX IF NOT EXISTS idx_source_file_package ON source_file (package_id);

    -- 5. Java class
    CREATE TABLE IF NOT EXISTS java_class (
        id             BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        source_file_id BIGINT       NOT NULL REFERENCES source_file (id),
        name           VARCHAR(512) NOT NULL,
        UNIQUE (source_file_id, name)
    );

    CREATE INDEX IF NOT EXISTS idx_java_class_source_file ON java_class (source_file_id);

    -- 6. Method
    CREATE TABLE IF NOT EXISTS method (
        id          BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        class_id    BIGINT       NOT NULL REFERENCES java_class (id),
        name        VARCHAR(255) NOT NULL,
        descriptor  VARCHAR(512) NOT NULL,
        start_line  INT NOT NULL,
        UNIQUE (class_id, name, descriptor)
    );

    CREATE INDEX IF NOT EXISTS idx_method_class ON method (class_id);

    -- 7. Line coverage sequence
    CREATE TABLE IF NOT EXISTS line_coverage_sequence (
        id              BIGINT   NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        snapshot_id     BIGINT   NOT NULL REFERENCES coverage_snapshot (id) ON DELETE CASCADE,
        source_file_id  BIGINT   NOT NULL REFERENCES source_file (id),
        start_line      INT      NOT NULL,
        end_line        INT      NOT NULL,
        coverage_status SMALLINT NOT NULL,
        CONSTRAINT chk_line_range      CHECK (end_line >= start_line),
        CONSTRAINT chk_coverage_status CHECK (coverage_status BETWEEN 0 AND 2)
    );

    CREATE INDEX IF NOT EXISTS idx_lcs_snapshot      ON line_coverage_sequence (snapshot_id);
    CREATE INDEX IF NOT EXISTS idx_lcs_source_file   ON line_coverage_sequence (source_file_id);
    CREATE INDEX IF NOT EXISTS idx_lcs_snap_file     ON line_coverage_sequence (snapshot_id, source_file_id);

    -- 8. Method coverage
    CREATE TABLE IF NOT EXISTS method_coverage (
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

    CREATE INDEX IF NOT EXISTS idx_method_cov_snapshot ON method_coverage (snapshot_id);
    CREATE INDEX IF NOT EXISTS idx_method_cov_method   ON method_coverage (method_id);

    -- 9. Class coverage
    CREATE TABLE IF NOT EXISTS class_coverage (
        id                    BIGINT  NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        snapshot_id           BIGINT  NOT NULL REFERENCES coverage_snapshot (id) ON DELETE CASCADE,
        class_id              BIGINT  NOT NULL REFERENCES java_class (id),
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

    CREATE INDEX IF NOT EXISTS idx_class_cov_snapshot ON class_coverage (snapshot_id);
    CREATE INDEX IF NOT EXISTS idx_class_cov_class    ON class_coverage (class_id);

    -- 10. File coverage
    CREATE TABLE IF NOT EXISTS file_coverage (
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

    CREATE INDEX IF NOT EXISTS idx_file_cov_snapshot    ON file_coverage (snapshot_id);
    CREATE INDEX IF NOT EXISTS idx_file_cov_source_file ON file_coverage (source_file_id);

    -- 11. Package coverage
    CREATE TABLE IF NOT EXISTS package_coverage (
        id                    BIGINT  NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        snapshot_id           BIGINT  NOT NULL REFERENCES coverage_snapshot (id) ON DELETE CASCADE,
        package_id            BIGINT  NOT NULL REFERENCES package (id),
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
        UNIQUE (snapshot_id, package_id)
    );

    CREATE INDEX IF NOT EXISTS idx_pkg_cov_snapshot ON package_coverage (snapshot_id);
    CREATE INDEX IF NOT EXISTS idx_pkg_cov_package  ON package_coverage (package_id);
    """,
    """
    DROP TABLE IF EXISTS package_coverage;
    DROP TABLE IF EXISTS file_coverage;
    DROP TABLE IF EXISTS class_coverage;
    DROP TABLE IF EXISTS method_coverage;
    DROP TABLE IF EXISTS line_coverage_sequence;
    DROP TABLE IF EXISTS method;
    DROP TABLE IF EXISTS java_class;
    DROP TABLE IF EXISTS source_file;
    DROP TABLE IF EXISTS package;
    DROP TABLE IF EXISTS coverage_snapshot;
    DROP TABLE IF EXISTS codebase;
    """
)
