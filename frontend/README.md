# Parana Frontend

The Parana Frontend is a modern React application that provides a natural-language chat interface for interacting with coverage data. It allows users to ask questions about code coverage, compare snapshots, and view detailed results in an interactive, sortable format.

## Features

- **Natural Language Chat:** A seamless, streaming chat interface for querying the Parana AI.
- **Interactive Data Rendering:** Complex coverage data is automatically rendered into sortable, themed tables.
- **Secure Authentication:** Integrated login and registration system using JWT (JSON Web Tokens).
- **Real-time Updates:** Uses Server-Sent Events (SSE) for streaming LLM responses.
- **Modern Tech Stack:** Built with React 19, Vite, TypeScript, and Vanilla CSS.

## Getting Started

### Prerequisites

- Node.js (v18 or higher)
- npm or yarn
- Parana Server running locally (default: `http://localhost:8000`)

### Installation

```bash
# Navigate to the frontend directory
cd parana/frontend

# Install dependencies
npm install
```

### Development

Start the development server with Vite:

```bash
npm run dev
```

The application will be available at `http://localhost:5173`.

**Note on API Proxying:** The development server is configured to proxy requests starting with `/api` and `/chat` to the backend server at `http://localhost:8000`. Ensure the backend is running for full functionality.

## Usage

1.  **Register/Login:** Upon opening the app, you will be prompted to create an account or sign in.
2.  **Chat:** Use the input bar at the bottom to ask questions like:
    - *"What is the coverage of the payment module?"*
    - *"Compare the latest snapshot with the one from last week."*
    - *"Which classes have the most missed lines?"*
3.  **Interact:** Click table headers to sort coverage data by name or delta values.

## Development

### Running Tests

This project uses **Vitest** and **React Testing Library** for unit and integration testing.

```bash
# Run all tests once
npm test

# Run tests in watch mode
npm run test:watch
```

### Linting

```bash
npm run lint
```

## Project Structure

- `src/`
  - `components/`: Reusable UI components (ChatPanel, ResultTable, AuthForm).
  - `test/`: Test suites and setup.
  - `api.ts`: API client logic (Auth, Chat SSE).
  - `useAuth.ts`: Hook for managing authentication state and persistence.
  - `useChat.ts`: Hook for managing chat message history and streaming.
  - `useSession.ts`: Hook for generating and persisting session IDs.
  - `App.tsx`: Main application orchestrator.
  - `index.css`: Global styles and design tokens.
  - `types.ts`: Shared TypeScript interfaces.
