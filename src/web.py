"""Thin web layer over the assistant.

A FastAPI shell with no business logic of its own: it serves a single-page chat
UI, lists investors for the (simulated) login picker, and forwards each message
to the existing InvestorAssistant. All correctness and grounding stay in the
deterministic layer; this file only speaks HTTP.

Run:
    uvicorn src.web:app --reload   # then open http://localhost:8000
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .loaders import load_dataset

try:  # load ANTHROPIC_API_KEY from .env if python-dotenv is present
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
UI_DIST = ROOT / "ui" / "dist"      # the built React UI (`cd ui && npm run build`)

app = FastAPI(title="Investor Assistant")
_ds = load_dataset()

# session_id -> (investor_id, InvestorAssistant). Kept in-process; this is a
# prototype, not a multi-tenant service.
_sessions: dict[str, tuple[str, object]] = {}


class ChatRequest(BaseModel):
    investor_id: str
    message: str
    session_id: str | None = None


@app.get("/api/investors")
def list_investors() -> list[dict]:
    """Investors for the login picker (simulated auth — in production the
    investor_id comes from the authenticated session, never the client)."""
    out = [
        {
            "id": iid,
            "name": inv["investor_name"],
            "reporting_currency": inv["reporting_currency"],
        }
        for iid, inv in _ds.investors.items()
    ]
    return sorted(out, key=lambda x: x["id"])


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    if req.investor_id not in _ds.investors:
        raise HTTPException(status_code=404, detail=f"Unknown investor_id: {req.investor_id}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY is not set on the server (add it to .env).",
        )

    # Reuse the session only if it exists AND is bound to the same investor.
    session_id = req.session_id
    entry = _sessions.get(session_id) if session_id else None
    if entry is None or entry[0] != req.investor_id:
        from .assistant import InvestorAssistant  # lazy: needs the anthropic pkg

        session_id = uuid.uuid4().hex
        assistant = InvestorAssistant(_ds, req.investor_id)
        _sessions[session_id] = (req.investor_id, assistant)
    else:
        assistant = entry[1]

    try:
        answer, trace = assistant.ask_with_trace(req.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")

    return {"session_id": session_id, "answer": answer, "trace": trace}


# Serve the React build last, so the /api/* routes above always win.
# If the UI hasn't been built yet, show a clear instruction instead of a 404.
if UI_DIST.exists():
    app.mount("/", StaticFiles(directory=UI_DIST, html=True), name="ui")
else:

    @app.get("/")
    def index() -> HTMLResponse:
        return HTMLResponse(
            "<h2>React UI not built</h2>"
            "<p>Run <code>cd ui &amp;&amp; npm install &amp;&amp; npm run build</code>, "
            "then restart the server. (The API at <code>/api/*</code> is already running.)</p>",
            status_code=503,
        )
