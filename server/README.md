# Parana Server

The Parana Server is a FastAPI-based REST API and chat service for the Parana coverage-tracking system. It provides endpoints for querying JaCoCo coverage snapshots, comparing coverage between different points in time, and a natural-language chat interface for interacting with coverage data.

## Features

- **Coverage API:** Endpoints to list codebases, snapshots, and perform detailed comparisons at the file, class, or method level.
- **AI Chat Interface:** A natural-language interface that translates plain-English questions (e.g., "What is the coverage of the payment module compared to last week?") into database queries.
- **Streaming Responses:** Supports Server-Sent Events (SSE) for the chat interface, providing real-time feedback and data rendering.
- **Asynchronous & Scalable:** Built on FastAPI with `psycopg` connection pooling for efficient, non-blocking database operations.
- **Secure Authentication:** JWT-based authentication using OAuth2 Password Flow and Argon2 password hashing.

## Requirements

- Python 3.12+
- PostgreSQL (populated by the [Parana Importer](../importer/))
- LLM API Key (required for the chat feature)

## Installation

This project uses `uv` for dependency management.

```bash
# Clone the repository
cd parana/server

# Install dependencies and create a virtual environment
# For development and running tests, include the 'dev' extra:
uv sync --extra dev
```

## Configuration

Create a `.env` file in the `server/` directory with the following variables:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/parana
PORT=8000
LLM_API_KEY=your_llm_api_key
LLM_MODEL=gpt-4o-mini
FRONTEND_ORIGIN=http://localhost:5173
JWT_SECRET_KEY=your_long_random_secret_string
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

- `DATABASE_URL`: Connection string for the Parana PostgreSQL database.
- `LLM_API_KEY`: Your LLM API key (used for intent resolution and response rendering).
- `LLM_MODEL`: The LLM model to use (default: `gpt-4o-mini`).
- `FRONTEND_ORIGIN`: Allowed CORS origin for the frontend application.
- `JWT_SECRET_KEY`: A secure random string for signing JWTs.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: How long an access token remains valid (default: 30).

## Usage

The server provides a CLI entry point named `parana-server`.

```bash
# Start the server
uv run parana-server
```

The API will be available at `http://localhost:8000` by default. You can access the interactive Swagger documentation at `http://localhost:8000/docs`.

## API Endpoints

### Auth
- `POST /auth/register`: Register a new user.
- `POST /auth/token`: Login and receive a JWT access token.

### Coverage (Requires Authentication)
- `GET /codebases`: List all tracked repositories.
- `GET /codebases/{id}/snapshots`: List coverage snapshots for a codebase.
- `GET /snapshots/{id}`: Get detailed metadata for a specific snapshot.
- `GET /compare`: Compare coverage between two snapshots.
  - Query Params: `before` (ID), `after` (ID), `level` (`file`|`class`|`method`), `filter` (optional string).

### Chat (Requires Authentication)
- `POST /chat`: Stream natural-language responses via SSE.
  - Request Body: `{ "session_id": "string", "message": "string" }`

## Development

### Running Tests

Tests use `pytest` and `testcontainers` for integration testing.

**Note for Podman Users:** Similar to the importer, if you are using Podman, the tests are configured to automatically disable the "Ryuk" reaper for compatibility.

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=parana_server
```

### Project Structure

- `src/parana_server/`
  - `main.py`: FastAPI application bootstrap and configuration.
  - `auth_utils.py`: Security utilities for hashing and JWT.
  - `deps.py`: Authentication and authorization dependencies.
  - `db.py`: Async connection pool management.
  - `queries.py`: SQL query logic for coverage and users.
  - `models.py`: Pydantic models for API and Auth.
  - `routers/`
    - `auth.py`: Registration and login routes.
    - `coverage.py`: Coverage query endpoints.
    - `chat.py`: LLM-orchestrated chat logic and SSE streaming.
