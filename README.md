# Parana — AI-Powered Coverage Tracking

Parana is a comprehensive system designed to track, analyze, and query Java code coverage data (JaCoCo). It provides a complete pipeline from raw coverage reports to a natural-language chat interface where users can ask questions about their project's coverage evolution.

## Architecture Overview

The project is composed of three main components:

1.  **[Importer](./importer/)**: A Python CLI utility that parses JaCoCo XML reports, resolves Git metadata, and persists the data into a PostgreSQL database.
2.  **[Server](./server/)**: A FastAPI-based REST API that serves coverage data and orchestrates an AI-powered chat interface using LLM.
3.  **[Frontend](./frontend/)**: A modern React application providing a streaming chat interface and interactive, sortable coverage tables.

## Key Technologies

-   **Backend:** Python 3.12+, FastAPI, `psycopg` (Async), `uv` (Package Management).
-   **AI:** LLM models for intent resolution and data rendering.
-   **Database:** PostgreSQL (with a optimized schema for historical snapshots).
-   **Frontend:** React 19, TypeScript, Vite, Vanilla CSS.
-   **Security:** OAuth2 with JWT, Argon2 password hashing.

## Quick Start

### 1. Database Setup
Ensure you have a PostgreSQL instance running. The system is self-bootstrapping; the first time you run the importer, it will create the necessary schema.

```sql
-- Example: Create the database
CREATE DATABASE parana;
```

### 2. Run the Importer
Use the importer to upload your first JaCoCo report.

```bash
cd importer
uv sync --extra dev
uv run parana-import --xml path/to/jacoco.xml --repo /path/to/your/git/repo --dsn "postgresql://user:pass@localhost/parana"
```

### 3. Start the Server
Configure your `.env` file in the `server/` directory (see [Server README](./server/README.md) for details) and start the API.

```bash
cd server
uv sync --extra dev
uv run parana-server
```

### 4. Launch the Frontend
Install dependencies and start the Vite development server.

```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173` to log in and start chatting with your coverage data.

## Project Structure

```text
parana/
├── design/          # Architectural diagrams and SQL schema definitions
├── importer/        # Python JaCoCo parser and DB synchronizer
├── server/          # FastAPI REST API and LLM orchestration
├── frontend/        # React visualization and chat UI
└── README.md        # This file
```

## Documentation

For detailed information on each component, please refer to their respective READMEs:
-   [Importer Documentation](./importer/README.md)
-   [Server Documentation](./server/README.md)
-   [Frontend Documentation](./frontend/README.md)

## License

This project is licensed under the [MIT License](./LICENSE).
