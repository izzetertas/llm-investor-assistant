# Investor Assistant — React UI

A React (Vite + TypeScript) front-end for the Investor Assistant. It is
a thin client over the existing FastAPI backend — all correctness and grounding
stay in the deterministic Python layer; this app only renders chat and the
grounding panel.

## Run (two terminals)

**1. Backend** (from the repo root, with `ANTHROPIC_API_KEY` in `.env`):

```bash
uvicorn src.web:app --reload          # serves the API on http://localhost:8000
```

**2. Front-end** (from `ui/`):

```bash
npm install
npm run dev                            # http://localhost:5173
```

The Vite dev server proxies `/api/*` to the backend on `:8000`
(see `vite.config.ts`), so no CORS setup is needed.

## Single-port (production-like)

Build the front-end once, and the FastAPI backend serves it directly — no Vite
process, one port, one command:

```bash
npm run build                          # emits ui/dist/
cd .. && uvicorn src.web:app           # http://localhost:8000 serves the React build + API
```

`src/web.py` automatically serves `ui/dist/` when it exists, and falls back to
the no-build `static/index.html` otherwise. Use `npm run dev` (above) while
iterating on the UI; use the build for a clean single-port demo.

## What it does

- Investor picker (simulated login — in production the investor comes from the
  authenticated session, never the client).
- Chat over the portfolio: holdings, MOIC, fees, capital calls, distributions,
  statement.
- Renders the model's Markdown (GFM tables via `react-markdown` + `remark-gfm`).
- **Grounding panel** under each answer: which deterministic tools ran and the
  source row IDs they returned — generated from the backend trace, not the
  model, so it is the auditable record.

## Structure

```
ui/
  index.html            # Vite entry
  vite.config.ts        # dev server + /api proxy
  src/
    main.tsx            # React root
    App.tsx             # layout + chat state
    api.ts              # backend calls (typed)
    types.ts            # shared types
    styles.css          # styling (ported from the static UI)
    components/
      Message.tsx        # one chat row (Markdown render)
      GroundingTrace.tsx # the grounding panel
      Composer.tsx       # input + send
```
