# Parana Implementation Plan

## App 1: Parser / Inserter (`importer/`)

**Language:** Python 3.12+ | **Package manager:** `uv` / `pyproject.toml`

### Project Scaffold
- [ ] Create `importer/` directory
- [ ] Create `pyproject.toml` with project metadata, entry-point `parana-import`, dependencies (`psycopg[binary]`, `lxml`, `click`, `python-dotenv`)
- [ ] Create `src/parana_importer/` package with `__init__.py`
- [ ] Create `tests/` directory with `conftest.py` and a pytest fixture that spins up a test Postgres instance (via `pytest-postgresql` or `testcontainers`)

### Database Layer (`db.py`)
- [ ] Implement `connect(dsn: str) -> Connection` using `psycopg`
- [ ] Implement `ensure_schema(conn)` — reads and applies `design/schema.sql` if tables are absent
- [ ] Implement `upsert_codebase(conn, git_origin) -> int` — INSERT … ON CONFLICT DO NOTHING, return id
- [ ] Implement `upsert_package(conn, codebase_id, name) -> int`
- [ ] Implement `upsert_source_file(conn, package_id, name) -> int`
- [ ] Implement `upsert_java_class(conn, source_file_id, name) -> int`
- [ ] Implement `upsert_method(conn, class_id, name, descriptor, start_line) -> int`
- [ ] Implement `insert_snapshot(conn, codebase_id, git_commit_hash, uncommitted_files_hash, captured_at) -> int`
- [ ] Implement `bulk_insert_line_sequences(conn, snapshot_id, rows: list[LineSeqRow])`
- [ ] Implement `bulk_insert_method_coverage(conn, snapshot_id, rows)`
- [ ] Implement `bulk_insert_class_coverage(conn, snapshot_id, rows)`
- [ ] Implement `bulk_insert_file_coverage(conn, snapshot_id, rows)`

### XML Parser (`parser.py`)
- [ ] Implement `parse_jacoco_xml(path: str) -> Report` using `lxml.etree.iterparse` (streaming / SAX-style to handle large files)
- [ ] Model dataclasses: `Report`, `Package`, `SourceFile`, `JavaClass`, `Method`, `Line`, `Counter`
- [ ] Parse `<counter>` elements at each level (instruction, branch, line, complexity, method, class) into typed counter objects
- [ ] Parse `<line>` elements within `<sourcefile>` into `Line(nr, mi, ci, mb, cb)`
- [ ] Parse `<method>` elements with `name`, `desc`, `line` attributes

### Line Sequence Compressor (`sequences.py`)
- [ ] Implement `derive_status(mi, ci, mb, cb) -> int` (0/1/2) using the rules from `design/software_design.md §3.1.2`
- [ ] Implement `compress_lines(lines: list[Line]) -> list[LineSeqRow]` — collapse consecutive same-status lines into `(start_line, end_line, status)` tuples

### Git Metadata (`git_meta.py`)
- [ ] Implement `resolve_git_origin(repo_path: str) -> str` using `gitpython` (`Repo.remotes["origin"].url`)
- [ ] Implement `resolve_commit_hash(repo_path: str) -> str` (`repo.head.commit.hexsha`)
- [ ] Implement `compute_uncommitted_files_hash(repo_path: str) -> str` — replicate the algorithm from `design/software_design.md §3.1.1`:
  - Get changed tracked files + untracked files (respecting `.gitignore`)
  - Sort lexicographically
  - For each file: `<status_code> <path> <sha256_of_content>`; deleted = "DELETED"
  - SHA-256 of concatenated string; empty = "CLEAN"

### Import Orchestrator (`importer.py`)
- [ ] Implement `run_import(xml_path, repo_path, dsn)` that:
  1. Resolves git metadata
  2. Parses XML
  3. Opens a DB transaction
  4. Upserts codebase, packages, source files, classes, methods
  5. Creates snapshot
  6. Bulk-inserts line sequences and all three coverage aggregate tables
  7. Commits (all-or-nothing)

### CLI Entry Point (`cli.py`)
- [ ] Implement `@click.command` with options `--xml`, `--repo`, `--dsn` (also reads `DATABASE_URL` env var via `python-dotenv`)
- [ ] Output success: `Imported snapshot #{id} for codebase #{codebase_id}`
- [ ] Output error: clear message + non-zero exit code

### Tests
- [ ] Unit test `derive_status` with all edge-case combinations
- [ ] Unit test `compress_lines` with single-line, all-same, mixed sequences
- [ ] Unit test `compute_uncommitted_files_hash` using a temp git repo (via `gitpython`)
- [ ] Integration test `run_import` against a real Postgres (testcontainers), using a fixture JaCoCo XML

---

## App 2: gRPC Server (`server/`)

**Language:** Python 3.12+ | **Frameworks:** `grpcio`, `grpcio-tools`, `psycopg[binary]`

### Proto Definition (`proto/parana.proto`)
- [ ] Create `proto/parana.proto` with `syntax = "proto3"`
- [ ] Define `Codebase` message: `id`, `git_origin`
- [ ] Define `Snapshot` message: `id`, `codebase_id`, `git_commit_hash`, `uncommitted_files_hash`, `captured_at`
- [ ] Define `CoverageRow` message: all coverage counter fields plus `entity_name`, `covered_pct_before`, `covered_pct_after`, `delta_covered_pct`
- [ ] Define `ListCodebasesRequest/Response`
- [ ] Define `ListSnapshotsRequest` (codebase_id, optional limit, optional offset) / `ListSnapshotsResponse`
- [ ] Define `GetSnapshotRequest/Response`
- [ ] Define `CompareSnapshotsRequest` (snapshot_before_id, snapshot_after_id, level enum FILE/CLASS/METHOD, optional filter string) / `CompareSnapshotsResponse` (repeated CoverageRow)
- [ ] Define `service ParanaService` with the four RPCs above

### Code Generation
- [ ] Create `server/generate_proto.sh` (or `Makefile` target) to run `python -m grpc_tools.protoc` and output stubs into `server/src/parana_server/proto/`
- [ ] Commit generated `parana_pb2.py` and `parana_pb2_grpc.py` to the repo

### Project Scaffold
- [ ] Create `server/pyproject.toml` with entry-point `parana-server`, dependencies (`grpcio`, `grpcio-tools`, `psycopg[binary]`, `python-dotenv`)
- [ ] Create `src/parana_server/` package

### Database Query Layer (`queries.py`)
- [ ] Implement `list_codebases(conn) -> list[CodebaseRow]`
- [ ] Implement `list_snapshots(conn, codebase_id, limit, offset) -> list[SnapshotRow]`
- [ ] Implement `get_snapshot(conn, snapshot_id) -> SnapshotRow | None`
- [ ] Implement `compare_snapshots_file(conn, before_id, after_id, filter) -> list[CoverageRow]` — using FULL OUTER JOIN on `file_coverage` (exact SQL from `design/schema.sql`)
- [ ] Implement `compare_snapshots_class(conn, before_id, after_id, filter) -> list[CoverageRow]`
- [ ] Implement `compare_snapshots_method(conn, before_id, after_id, filter) -> list[CoverageRow]`
- [ ] Compute `covered_pct = covered_lines / (covered_lines + missed_lines)` in SQL (CASE to avoid div-by-zero)

### gRPC Servicer (`servicer.py`)
- [ ] Implement `ParanaServicer(parana_pb2_grpc.ParanaServiceServicer)` class
- [ ] Implement `ListCodebases(request, context)` — calls `queries.list_codebases`
- [ ] Implement `ListSnapshots(request, context)` — calls `queries.list_snapshots`
- [ ] Implement `GetSnapshot(request, context)` — calls `queries.get_snapshot`; set `NOT_FOUND` status if missing
- [ ] Implement `CompareSnapshots(request, context)` — dispatches on `request.level`; set `INVALID_ARGUMENT` for unknown levels
- [ ] Implement connection pool acquisition (use thread-local or `psycopg.pool.ThreadedConnectionPool`)

### Server Bootstrap (`main.py`)
- [ ] Implement `serve(dsn, port, max_workers)` using `grpc.server(ThreadPoolExecutor)`
- [ ] Add `grpc.reflection` for service discovery
- [ ] Read `DATABASE_URL`, `PORT`, `MAX_WORKERS` from env
- [ ] Graceful shutdown on `SIGTERM` / `SIGINT`

### Tests
- [ ] Unit test each query function against a Postgres testcontainer pre-populated with known fixture data
- [ ] Integration test: start a full `grpc.server` in-process, send real RPC calls, verify responses
- [ ] Test `CompareSnapshots` with an entity present in only one snapshot (verify NULL handling)
- [ ] Test `GetSnapshot` with unknown ID returns gRPC `NOT_FOUND`

---

## App 3: Frontend (`frontend/`)

**Language:** TypeScript | **Framework:** React 18 + Vite | **HTTP:** `fetch` with SSE (`EventSource` or manual `ReadableStream`)

### Project Scaffold
- [ ] `cd frontend && npm create vite@latest . -- --template react-ts`
- [ ] Add dependencies: `tailwindcss` (optional for base styling)
- [ ] Configure `vite.config.ts` proxy: `/chat` → `http://localhost:8000` (chat service)

### Types (`src/types.ts`)
- [ ] Define `Message { id, role: "user"|"assistant", text: string, result?: ResultPayload }`
- [ ] Define `ResultPayload { result_type: "table"|"text"; columns?: string[]; rows?: Record<string, unknown>[] }`
- [ ] Define `SSEChunk { type: "text_delta"|"result"|"done"|"error"; data: string | ResultPayload }`

### API Client (`src/api.ts`)
- [ ] Implement `sendMessage(sessionId, message, onChunk, onResult, onDone, onError)`:
  - `POST /chat` with JSON body `{ session_id, message }`
  - Consume `text/event-stream` response via `ReadableStream` + `TextDecoder`
  - Parse SSE lines, dispatch to the appropriate callback

### Session Management (`src/useSession.ts`)
- [ ] Custom hook that generates a UUID `session_id` on first load and persists it in `localStorage`
- [ ] Exposes `sessionId: string`

### State Management (`src/useChat.ts`)
- [ ] Custom hook managing `messages: Message[]`, `isStreaming: boolean`
- [ ] `sendMessage(text)` — appends user message, calls `api.sendMessage`, streams assistant reply into a growing assistant message, attaches `result` on completion

### Components
- [ ] **`ChatPanel`** (`src/components/ChatPanel.tsx`) — full-height flex column: message list + input bar; auto-scrolls to bottom on new message
- [ ] **`MessageBubble`** (`src/components/MessageBubble.tsx`) — renders one `Message`; user messages right-aligned, assistant left-aligned; renders `<TextBlock>` and optionally `<DynamicResult>`
- [ ] **`TextBlock`** (`src/components/TextBlock.tsx`) — renders plain text (pre-wrap); typing cursor animation while `isStreaming`
- [ ] **`DynamicResult`** (`src/components/DynamicResult.tsx`) — switch on `result_type`:
  - `"table"` → `<ResultTable>`
  - `"text"` → nothing extra (already in TextBlock)
- [ ] **`ResultTable`** (`src/components/ResultTable.tsx`) — renders `columns` as `<thead>` and `rows` as `<tbody>`; sortable by clicking column header (client-side); numeric delta columns highlight red/green

### App Shell (`src/App.tsx`)
- [ ] Render `<ChatPanel>` full-screen; no navigation, no routes; `<SessionContext.Provider>` wraps everything
- [ ] Minimal CSS reset / base styles in `src/index.css`

### Tests
- [ ] Unit test `sendMessage` API client against a mock SSE stream (using `msw` or manual `ReadableStream`)
- [ ] Unit test `ResultTable` renders correct number of rows and headers
- [ ] Unit test sort behaviour in `ResultTable`

---

## Shared Infrastructure

### `proto/` directory
- [ ] `proto/parana.proto` (serves both `server/` and `chat/` service)

### `chat/` FastAPI service (LLM orchestration, bridges frontend ↔ gRPC server)
- [ ] *(Separate checklist when implementation begins)*

### `docker-compose.yml` (root)
- [ ] `postgres` service (image `postgres:16`, volume, `POSTGRES_DB/USER/PASSWORD`, healthcheck)
- [ ] `server` service — build `./server`, depends on postgres, exposes gRPC port `50051`
- [ ] `chat` service — build `./chat`, depends on server, exposes HTTP port `8000`
- [ ] `frontend` service — build `./frontend`, depends on chat, exposes port `5173` (dev) or `80` (prod nginx)
- [ ] `.env.example` with `DATABASE_URL`, `OPENAI_API_KEY`, `GRPC_SERVER_HOST`, `PORT`
