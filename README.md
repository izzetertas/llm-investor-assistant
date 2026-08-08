# Investor Assistant

A grounded, personalised conversational assistant that answers an investor's
questions about **their own** portfolio — holdings, valuations, MOIC, fees,
capital calls, distributions, and account statement — from the Meridian mock
dataset.

The guiding principle: **the model talks, deterministic code does the maths.**
Every number is computed in plain Python from the source CSV rows and carries
the row IDs it came from, so each answer is auditable and cited. The LLM only
interprets the question, picks the right tool, and renders a personalised,
plain-language reply. It never does arithmetic and never sees another
investor's data.

---

## Architecture

```
  investor_id (assumed authenticated)  +  question
                     │
                     ▼
   ┌─────────────────────────────────────────────────────────┐
   │  SECURITY BOUNDARY (enforced in code, not in the prompt) │
   │  Every tool is bound to the logged-in investor_id.       │
   │  The model cannot pass or query a different investor.    │
   └─────────────────────────────────────────────────────────┘
                     │
        ┌────────────┴─────────────┐
        ▼                          ▼
  Deterministic tools        Personalisation signals
  (src/metrics.py)           (src/personalize.py)
  • portfolio_overview       • age, tech_savviness
  • position(company)        • # deals, top sectors
  • obligations              • concentration
  • realised_outcomes        → tone / depth knobs in
  • fees(company)              the system prompt
  • valuation_history
  • account_statement
        │  each returns figures + source row IDs (ALC…, VAL…, FEE…)
        ▼
   Claude Sonnet 4.6  (src/assistant.py — manual tool-use loop)
   interprets → calls tools → receives grounded JSON → writes the answer
        │
        ▼
   Personalised, plain-language reply with citations
```

### Layer responsibilities

| Layer | File | Responsibility |
|---|---|---|
| **Input / UI** | `ui/` + `src/web.py` | React (Vite + TS) chat UI over a thin FastAPI backend; selects the logged-in `investor_id`. |
| **Data / retrieval** | `src/loaders.py` | Load & index the 10 CSVs into typed tables. |
| **FX** | `src/fx.py` | All cross-currency conversion, via USD. |
| **Reasoning (deterministic)** | `src/metrics.py` | Every financial figure + its source rows. |
| **Personalisation** | `src/personalize.py` | Derive signals; build the tone/depth directive. |
| **Tools** | `src/tools.py` | Tool schemas + dispatch, bound to one investor. |
| **Model reasoning** | `src/assistant.py` | Claude tool-use loop + system prompt. |
| **Tests** | `tests/` | Edge cases & invariants on the deterministic layer. |

This separation is deliberate: the parts that must be **correct** (the maths)
are pure functions with tests; the part that must be **fluent** (the prose) is
the model. Swapping the model, or replacing the CLI with a web UI, touches
nothing in `metrics.py`.

---

## Why this design

- **Reliability & verification (the hard part).** LLMs are unreliable at
  multi-step arithmetic, FX conversion, and joins across tables. So none of
  that is left to the model. `metrics.py` computes MOIC, FX-converted totals,
  effective-vs-standard fees, and cross-round aggregation, and every result
  ships with the source row IDs. The model is told to cite them.
- **Personalisation that never changes the numbers.** Tone, depth, and framing
  adapt to the investor (age, tech-savviness, number of deals, top sectors).
  The figures are identical for everyone — they come from the same
  deterministic functions regardless of who is asking.
- **Security by construction.** The `investor_id` is injected into the tool
  layer as a closure, not exposed as a tool parameter. There is no code path by
  which the model can read another investor's rows.

---

## Models / APIs used

| Purpose | Model | Why |
|---|---|---|
| Conversational tool-use loop | **Claude Sonnet 4.6** (`claude-sonnet-4-6`) | Excellent tool-use and instruction-following at a fraction of Opus cost; correctness is carried by the deterministic layer, so a frontier model isn't required. Adaptive thinking on. |

Anthropic Python SDK (`anthropic`), manual agentic tool-use loop. Set
`ANTHROPIC_API_KEY` in the environment.

> The assistant runs the **dataset maths offline** even without an API key —
> see "Running without an API key" below. The key is only needed for the
> conversational layer.

---

## Dataset

Reads the 10 CSVs in `data/`. Report date is fixed
at **2026-06-25**. No external data is used. Edge cases handled:

- Multi-round companies (Forgecraft Seed/A/B) aggregated per position.
- Per-allocation share-price & fee discounts (cost basis is per-allocation).
- Multi-currency, converted via USD to the investor's reporting currency.
- Commitment vs contributed (partial capital calls), pending/unfunded.
- Exits (Helianthe), write-offs (Yappio), down rounds (Qubrium B).
- Partial secondaries (Tallybook — 30% realised, 70% still live).
- Similar names (Northpeak Analytics vs Northpeak Health) — disambiguated.
- Newly-onboarded investors with zero holdings.

---

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Provide your Anthropic API key (get one at https://console.anthropic.com)
cp .env.example .env        # then edit .env and paste your key
# ...or: export ANTHROPIC_API_KEY=sk-ant-...

# React UI (Vite + TypeScript) — see ui/README.md
# Build the front-end once; the FastAPI backend serves it + the API on one port:
cd ui && npm install && npm run build && cd ..
uvicorn src.web:app                    # open http://localhost:8000

# ...or dev mode with hot reload (two terminals):
#   uvicorn src.web:app --reload         # backend on :8000
#   cd ui && npm run dev                 # front-end on :5173 (proxies /api)
```

Then ask, in plain language:

- "What's my portfolio worth and what's my MOIC?"
- "Show me my Forgecraft position across rounds."
- "What fees am I paying on Inferna, and did I get a discount?"
- "Do I have any capital calls or overdue fees coming up?"
- "How did Qubrium's valuation move, and what did that do to my MOIC?"
- "Give me my account statement."

### Running without an API key (deterministic layer only)

To verify the numbers without the model, run the metrics directly:

```bash
python -m src.report --investor INV001     # prints the grounded figures + sources
```

### Tests

```bash
pip install pytest
pytest -q
```

The tests assert hand-checked figures and structural invariants for the trap
cases (exit MOIC includes distributions, write-off shows a loss, pending =
0 contributed, Tallybook 30%/70% split, Northpeak disambiguation, zero-holding
investor).

---

## Assumptions

- The investor is already authenticated; the app is told which `investor_id` is
  logged in — selected in the UI here, but in production this comes from the
  authenticated session, never the client (per the brief).
- **Current value** of a position = remaining units × latest mark, FX-converted;
  0 for fully exited or written-off rounds.
- **MOIC** = (current value + distributions net of carry) ÷ capital contributed.
  Undefined (not zero) when nothing has been contributed (pending allocations).
- "How much have I invested?" is reported as **contributed**, with committed
  shown alongside, because the two differ under partial calls.
- Admin fees are denominated in USD even on non-USD deals (per the data guide).
- A fully-waived fee produces no row; absence of a fee row is not an error.

---

## Known limitations

- The prototype is a single-process demo (React UI + FastAPI), not a production
  service — no real auth, no rate limiting, no persistence of conversation
  history beyond the in-memory session.
- Company resolution is substring/exact match; a vaguer query than the
  disambiguation set may need a follow-up.
- Figures use float arithmetic rounded at display; a production ledger would use
  fixed-point/decimal.
- No evaluation harness beyond the unit tests — see `ai-workflow.md` for what a
  further 8 hours would add (a golden-answer eval set and an answer-grounding
  checker).

---

## Repository layout

```
llm-investor-assistant/
  data/               # the 10 synthetic CSVs
  src/
    loaders.py       # CSV load + indexing
    fx.py            # currency conversion (via USD)
    metrics.py       # deterministic financial figures + source IDs
    personalize.py   # personalisation signals + tone directive
    tools.py         # tool schemas + investor-bound dispatch
    assistant.py     # Claude tool-use loop + system prompt (+ grounding trace)
    web.py           # FastAPI backend (API + serves the React build)
    report.py        # offline deterministic report (no API key) — for verification
  ui/                # React UI (Vite + TypeScript) — the front-end; see ui/README.md
  tests/             # edge-case + invariant tests
  README.md
  ai-workflow.md     # how AI was used, what was verified/rejected
  system-design.md   # staged design, prototype → full RM bot
  Dataset Guide.md   # data schema + edge-case guide
  WALKTHROUGH.md     # demo script
  requirements.txt
```

> `src/cli.py` (terminal chat) exists as an optional alternative over the same
> backend, but the **React UI in `ui/` is the primary interface**.
