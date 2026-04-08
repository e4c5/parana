from yoyo import step

__depends__ = {"0001_initial_schema"}

step(
    """
    -- 12. App User (authentication and authorization)
    CREATE TABLE app_user (
        id              BIGINT       NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        username        VARCHAR(255) NOT NULL UNIQUE,
        hashed_password VARCHAR(255) NOT NULL,
        is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX idx_app_user_username ON app_user (username);
    """,
    """
    DROP TABLE IF EXISTS app_user;
    """
)
