# Weather Risk Intelligence: chat UI

Angular 22 (standalone components, signals) + Angular Material. Talks only to the Python API
(`POST /chat`, `GET /chat/sessions`, `GET /chat/sessions/{id}`, `GET /hubs`); it contains no scoring
logic and shows the API's deterministic values as they are. Conversations are saved by the server
(SQLite): the side panel lists them and the most recent one is reopened on start.

## Run

```bash
npm ci

# Development: live reload on http://localhost:4200, API calls proxied to http://127.0.0.1:8000
npm start

# Production build: served by FastAPI at http://127.0.0.1:8000/
npm run build

# Unit tests (Vitest)
npx ng test --watch=false
```

The API must be running (`uv run uvicorn weather_risk.main:app` from the repository root).

## Structure

```
src/app/
  app.*                    Shell: top bar, hub panel | conversation | evidence panel
  core/
    api.models.ts          API types (ChatResponse, results per capability)
    chat-api.service.ts    HTTP calls + friendly error messages
    chat-store.ts          Conversation state (signals); saved conversations come from the API
    describe.ts            Plain-language "How I got this" steps and follow-up suggestions
    hazards.ts             Hazard colors/icons/sources, factor labels
    sources.ts             Data sources and caveats behind an answer
    export.ts              Conversation -> Markdown download
  chat/                    Welcome, message bubble, composer, thinking bubble, conversation list,
                           hub panel, dialog
  insights/                Evidence views: ranking, comparison, single hub, weather facts,
                           hazard data, sources & caveats, "How scores work"
  shared/                  Score bar, factor breakdown, markdown pipe
  testing/fixtures.ts      Test data shaped like real API results
```
