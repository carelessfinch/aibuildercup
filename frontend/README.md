# Plasma Research Group Frontend

A React client for plasma physics literature search and expert simulation
review. It provides a chat-style research workspace, streaming answers, source
inspection, literature search, and `Literature` / `Reviewer` agent modes.

## Architecture

- **Frontend-only** React (CRA + craco) app. There is no bundled backend.
- `src/lib/api.js` talks to the Literature RAG API and includes a
  self-contained DEMO MODE so the UI remains usable before the API is configured.
- `src/lib/research.js` talks to the validation-team API and includes a
  scripted Postdoc → PhD → Professor demo replay.
- Chat history is retained in browser `localStorage` and restored per session.
- The interface uses React, Tailwind CSS, and shadcn/ui.

## Local development

From `frontend/`:

```bash
npm install --legacy-peer-deps
npm start
```

The app runs at <http://localhost:3000>.

## Environment variables

Create a local `.env` file in `frontend/` when needed:

| Variable | Purpose |
| --- | --- |
| `REACT_APP_RAG_API_URL` | Literature RAG API base URL. Leave empty for DEMO MODE, which also skips login. |
| `REACT_APP_RESEARCH_API_URL` | Validation-run API base URL. Leave empty for the scripted validation demo. |

When `REACT_APP_RAG_API_URL` is set, protected routes require the token returned
by `POST /v1/auth/login`. The browser stores the token and expiry in
`localStorage`, sends it as `Authorization: Bearer ...`, and clears it on any
401. No API key is embedded in the frontend bundle.

## Production build

```bash
cd frontend
CI=false npx craco build
```

The optimized app is emitted to `frontend/build/`.

## Deployment

Production deployment is handled by the separate deployment repository. It
packages the frontend build in an nginx container and deploys the image to
Cloud Run. Build this app with the deployment workflow before deploying.

## Product scope

The app supports:

- Sidebar chat history grouped by date, with rename and delete controls.
- New-chat creation and a source filter popover for the indexed corpus.
- Streaming answers with tool-call steps and a verdict badge for reviewer
  responses.
- Inline citation chips that open the source reader and related cited passages.
- Direct literature search and source-page reading.
- Copy BibTeX or cited passage text.
- Light and dark themes, persisted in `localStorage` and initialized before
  React paints to avoid theme flash.
- `/validate`, with demo presets, range-checked 4M form entry, a live research
  transcript, Professor rubric and citations, physics plots, KPI timer, and
  human sign-off when the run reaches `awaiting_signoff`.

Recent UI work completed the chat layout, citation and source-reader flows,
literature search, and the light/dark theme system. Current opportunities
include richer Markdown presentation, message copy/regenerate controls,
friendlier rate-limit handling, mobile layout improvements, and keyboard
shortcuts.
