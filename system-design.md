# System Design (staged)

A staged design, from the prototype in this repo up to a full investor
relationship-manager bot. The one idea that runs through every layer:
**deterministic code owns the numbers and the decisions; the model owns the
language.** Everything else is built to protect that.

## Index

- **[System Design (staged)](#system-design-staged)**
  - [1. Problem statement](#1-problem-statement)
  - [2. Functional requirements](#2-functional-requirements)
  - [3. Non-functional requirements](#3-non-functional-requirements)
  - [4. Scope, assumptions, and (honest) scale](#4-scope-assumptions-and-honest-scale)
  - [5. Core components](#5-core-components)
  - [6. High-level architecture](#6-high-level-architecture)
  - [7. Deep dive — component by component](#7-deep-dive--component-by-component)
  - [8. Data model (key entities)](#8-data-model-key-entities)
  - [9. API design (key surfaces)](#9-api-design-key-surfaces)
  - [10. Request flows (sequences)](#10-request-flows-sequences)
  - [11. Key design decisions & trade-offs](#11-key-design-decisions--trade-offs)
  - [12. Failure modes & mitigations](#12-failure-modes--mitigations)
  - [13. Scaling & evolution](#13-scaling--evolution)
  - [14. Cost model (shape)](#14-cost-model-shape)
  - [15. Six-month phasing](#15-six-month-phasing)
  - [In one paragraph](#in-one-paragraph)

---

## 1. Problem statement

Investors need to understand their position with the firm — holdings, value,
MOIC, obligations, distributions, statements — and today they get it from static
reports and by emailing a human RM, then waiting. Build an assistant that answers
their questions accurately, cites its sources, adapts to the investor, and
eventually acts proactively like an RM. It must never expose another investor's
data and must never give investment advice.

[↑ Index](#index)

---

## 2. Functional requirements

**Prototype (built):**
- Q&A over the investor's **own** portfolio: overview, single position (across
  rounds), obligations (calls + fees), realised outcomes, fees vs standard,
  valuation history, account statement.
- Grounded answers with **citations** to source rows.
- Personalised tone/depth (age, tech level, portfolio shape) — numbers unchanged.
- Multi-currency, converted to the investor's reporting currency.
- **Minimal data exposure to the model**: sending customer data to an external
  LLM takes it outside our security boundary, so the assistant must send the
  model only what's strictly needed to answer this turn (the question + the
  computed figures), **redact direct identifiers** (real name → first name or a
  token; no email, KYC details, or account numbers), and never send the full
  dataset. (Deep dive: §7.11.)

**Full product (future stages):**
- **Proactive nudges**: capital-call/fee reminders, new marks, distributions,
  expiring KYC.
- **Actions** (human-in-the-loop): document requests, KYC/AML onboarding,
  e-signature hand-off, drafting investor comms, reporting exports.
- Delivered in the iOS investor app (chat + push).

[↑ Index](#index)

---

## 3. Non-functional requirements

| Dimension | Target / stance |
|---|---|
| **Correctness** | Non-negotiable. Every figure deterministic + cited; zero tolerance for a wrong number stated confidently. |
| **Trust / grounding** | No figure the model authored; every number traces to a ledger row. |
| **Security / isolation** | Strict per-investor access; no path to another investor's data (enforced in code, not prompt). |
| **Compliance** | No investment advice; full audit trail; human approval for material actions; data protection (PII minimisation, regional hosting if required). |
| **Data protection (model exposure)** | Sending data to an external LLM leaves our boundary. Minimise + redact what the model sees; use provider terms with **no-training + short/zero retention (ZDR)** under a DPA; in-region hosting (Bedrock/Vertex) as an option; encrypted, access-controlled, minimally-retained prompt/response logs; disclose AI processing to investors. |
| **Latency** | Interactive chat: first token in ~1-2s, full answer in a few seconds (tool loop). Nudges are async. |
| **Availability** | Read-heavy; the ledger mirror + assistant should tolerate source-system downtime (serve last-synced). |
| **Cost efficiency** | Small grounded payloads + cacheable prefixes + cheap model for most traffic. |
| **Auditability / explainability** | Every tool call, message, and action logged immutably. |

[↑ Index](#index)

---

## 4. Scope, assumptions, and (honest) scale

**Scope decisions:**

| Decision | Choice |
|---|---|
| Scope | **Full product (RM bot)** — grounded Q&A + proactive nudges + actions (KYC/docs/e-sign), human-in-the-loop for anything material |
| Scale | **Modest** — 100s–1000s of LPs, low QPS. No sharding/exotic scaling. The hard problems are correctness, integrations, and compliance — not throughput |
| Optimise for | **Correctness & compliance first** — accept higher latency/cost where needed; grounding, audit, and human approval take priority |
| Clients | **iOS app (primary)** — chat + push for nudges — and a **web ops console** for RMs (approval queue, audit view) |
| Data protection | **Minimise + redact** customer data sent to the external LLM; provider must contractually **not train** on it and support short/zero retention (ZDR/DPA); in-region hosting as an option |

- **Auth is assumed** — the app is told which investor is logged in (production:
  from the authenticated session, never the client).
- **Scale is modest, and that shapes the design.** A VC firm's investor base is
  hundreds to low-thousands of LPs, not millions. So:
  - QPS is low (interactive chats + periodic nudges). No need for heavy sharding,
    global caches, or exotic scaling.
  - **The hard problems are correctness, integrations, compliance, and
    proactivity — not throughput.** Say this out loud; it signals maturity.
- Back-of-envelope: ~1-5k investors, ~5-10 positions each → ~10-50k allocations;
  data in the low millions of rows total; chat volume maybe hundreds-thousands
  of messages/day. Comfortably a single Postgres + a few app instances.

[↑ Index](#index)

---

## 5. Core components

```
1. Client            iOS app (chat + push); web console for ops
2. API gateway / BFF auth, rate limit, request/response audit
3. Orchestrator      the agent loop: model + tool selection (stateless per turn)
4. Tool layer        deterministic domain tools (metrics/obligations/fees/...)
                     + action tools (request_doc, start_kyc, draft_comm)  ← internal MCP service
5. Data layer        portfolio-ledger mirror (Postgres) + object store (docs)
6. Retrieval         pgvector — documents & policy text ONLY (never numbers)
7. Event/nudge engine  ingests ledger/fund-admin events → rules → nudges
8. Model provider    Claude (Sonnet for chat, Opus for hard reasoning)
9. Eval & guardrails golden-set evals, grounding linter, no-advice classifier
10. Observability    tracing, metrics, immutable audit log
11. Integrations     ledger, fund admin, CRM, KYC/AML, e-sign, comms, valuation/FX
```

[↑ Index](#index)

---

## 6. High-level architecture

```
        ┌───────────┐        push (nudges)
        │  iOS app  │◀─────────────────────────────┐
        │  (chat)   │                              │
        └─────┬─────┘                              │
              │ HTTPS                              │
        ┌─────▼────────────────────────────────────┴──────┐
        │  API gateway / BFF  (auth · rate limit · audit) │
        └─────┬────────────────────────────────────┬──────┘
              │ chat                               │ events
        ┌─────▼────────────────┐            ┌──────▼────────────────┐
        │   Orchestrator       │            │  Event / Nudge engine │
        │  (agent loop: model  │            │  rules decide WHEN;   │
        │   + tool selection)  │            │  model drafts TEXT    │
        └───┬─────────────┬────┘            └───────┬───────────────┘
            │ tool calls  │ retrieval               │ triggers
   ┌────────▼────────┐ ┌──▼───────────┐             │
   │  Tool layer     │ │ Retrieval    │             │
   │ (deterministic  │ │ (pgvector —  │             │
   │  metrics +      │ │  docs only)  │             │
   │  actions) [MCP] │ └───┬──────────┘             │
   └───┬─────────────┘     │                        │
       │ reads             │                        │
   ┌───▼───────────────────▼────────────────────────▼─────────┐
   │  Data layer:  Postgres ledger mirror · object store      │
   │               event bus · cache                          │
   └───┬──────────────────────────────────────────────────────┘
       │ replication / event feeds
   ┌───▼───────────────────────────────────────────────────────┐
   │ Source systems: portfolio ledger · fund admin · CRM ·     │
   │                 KYC/AML · e-sign · comms · valuation/FX   │
   └───────────────────────────────────────────────────────────┘

   Cross-cutting: Eval & guardrails · Observability & audit log · Model provider
```

**Two entry paths, one tool layer:** interactive chat (reactive) and the nudge
engine (proactive) both call the *same* deterministic tools. Reuse = one place to
keep correct and audited.

[↑ Index](#index)

---

## 7. Deep dive — component by component

### 7.1 Data layer (the source of truth)

- **Ledger mirror**: replicate the portfolio ledger + fund-admin into a
  read-optimised **Postgres** (CDC / scheduled sync). The assistant reads the
  mirror, never the live source, so source downtime doesn't take chat down and
  read load never hits the system of record.
- **Reconciliation**: periodic checksum/counts vs source; alert on drift.
  Contract tests against source schemas.
- **Object store** (S3/GCS) for documents (statements, side letters, KYC docs).
- **Event bus** (SQS/PubSub/Kafka-lite): fund-admin emits calls/fees/marks/
  distributions → feeds the nudge engine.
- **FX**: rates table, refreshed on a schedule; all conversion via USD.

**Why mirror, not query source live?** Isolation (source is the system of
record — don't add read load or coupling), availability (serve last-synced),
and shape (optimise for the assistant's access patterns).

### 7.2 Deterministic tool layer (the trust boundary)

- Pure functions: `portfolio_overview`, `position(company)`, `obligations`,
  `realised_outcomes`, `fees(company)`, `valuation_history`, `account_statement`,
  plus action tools later.
- Each returns **figures + the source row IDs** used → citations for free.
- **Investor-scoped by construction**: the investor_id is injected (closure /
  row-level filter), never a tool parameter. No tool can name another investor.
- **Exposed as an internal MCP service** so chat, nudges, iOS, and any internal
  agent share identical tools. (Prototype keeps them in-process; product
  promotes to a service without changing the math.)
- All money math is fixed-point/decimal in production; FX centralised.

### 7.3 Retrieval (documents only)

- pgvector over **document/policy text** (statements, fund docs, FAQ, side
  letters). Used for "what does my side letter say about fees?" style questions.
- **Hard rule: numbers never come from retrieval.** RAG grounds *prose*;
  deterministic tools ground *figures*. This avoids the classic RAG failure of a
  hallucinated or mis-extracted number.

### 7.4 Orchestrator (the agent loop)

- Stateless per turn; conversation state passed in (API is stateless).
- Manual tool-use loop: model → tool_use → execute deterministic tool → feed
  result back → repeat until final text.
- System prompt: grounding rules (never invent a number; cite sources; use
  reporting-currency `_reporting` fields; never FX-convert) + the personalisation
  directive.
- **Model routing**: Sonnet for everyday chat; escalate to Opus for hard
  reasoning (multi-doc synthesis, onboarding). Same code path; provider-agnostic
  (API / Bedrock for data residency).
- **Prompt caching**: stable tool schemas + system prompt as a cached prefix;
  volatile content (the question, history) after the breakpoint.

### 7.5 Personalisation

- Signals: stored (age, tech_savviness) + derived (deal count, top sectors,
  concentration).
- Turned into a tone/depth directive in the system prompt.
- **Invariant**: personalisation changes tone/depth/framing only — numbers are
  identical for everyone because they come from the same deterministic functions.

### 7.6 Event / nudge engine (proactivity)

- Event-driven: ledger/fund-admin events → **rules engine decides WHETHER and
  WHEN to nudge** (deterministic) → model drafts the message text → delivery.
- Examples: capital-call due in N days, fee overdue, new mark, distribution
  posted, KYC expiring.
- **Deterministic decides, model phrases** — the proactive analog of the whole
  design. Material comms are human-approved before send.
- Delivery via push/in-app; dedup + quiet-hours + preference controls.

### 7.7 Actions (human-in-the-loop)

- Action tools: `request_document`, `start_kyc`, `initiate_esign`, `draft_comm`,
  `generate_report`.
- Gated: hard-to-reverse or material actions require human approval; every
  action writes an audit entry. The bot **drafts and routes; a human decides**.
- Reporting is a **deterministic artifact** (PDF/XLSX) with the model writing
  only narrative around fixed figures.

### 7.8 Security & multi-tenancy

- AuthN/Z at the gateway; **row-level authorization** in the tool layer scoped to
  the investor.
- Secrets in a vault; PII-minimised prompts (only what the answer needs).
- The investor_id closure/RLS is the structural guarantee — a prompt-injection
  can't make a tool return someone else's rows because the tool has no parameter
  for it.
- Red-team tests in CI for cross-investor leakage and advice-seeking.

### 7.9 Evaluation & guardrails

- **Golden-set evals** in CI: question → expected figure + required citation.
  Blocks releases on regressions.
- **Grounding linter** (online): extract every number in a reply; confirm it
  appears in a tool result for that turn; flag/block ungrounded figures.
- **No-advice classifier** on inputs and outputs.
- Refusal handling; adversarial prompts for leakage/advice.

### 7.10 Observability & audit

- Request tracing (turn → tools → model calls), token/cost metrics.
- **Immutable audit log**: every tool call, message, action — for regulatory
  review and debugging.
- Alerting on drift (ledger reconciliation), grounding-linter flags, error rates.

---

### 7.11 LLM data exposure & minimisation

Sending customer data to an external model provider takes it **outside our
security boundary** — so this is a first-class requirement, not an afterthought.
Layered mitigations:

1. **The architecture already minimises exposure.** Because deterministic code
   does the maths, the model never sees the raw dataset or the ledger — only the
   small, already-authorised, computed result for *this one turn*. There is no
   bulk PII in the prompt.
2. **Redact direct identifiers before the model call.** The model doesn't need a
   legal name, email, KYC data, or account numbers to compute tone or phrase an
   answer. Pass a first name or an opaque token; strip the rest. Personalisation
   runs on *signals* (age band, tech level, sectors), not identity.
3. **Late-binding of sensitive values (optional, strongest).** For flows where
   the narrative doesn't need magnitudes, have the model emit a templated answer
   with placeholders (`Your MOIC is {moic}`) and let deterministic code fill the
   real figures *after* the model returns — so the actual numbers never leave our
   boundary. Trade-off: the model can't comment on magnitude ("your Seed is the
   standout at 6.84×") unless it sees values, so use this selectively; bucketed/
   rounded values are a middle ground.
4. **Provider contract: no training + zero/short retention.** Use API terms that
   guarantee the provider does **not train** on our data and supports **zero
   data retention (ZDR)** under a DPA. This is the single most important control.
5. **Residency / self-hosting option.** For strict data-residency, route
   inference in-region (Bedrock/Vertex); for the most sensitive slices, a
   self-hosted/open model is an option (cost/quality trade-off).
6. **Control the logs.** Prompts and responses contain data — encrypt them,
   access-control them, minimise retention, and never log secrets.
7. **Consent & disclosure.** Investors are told an AI processes their data, with
   an easy path to a human.

**Key reassurance for the room:** even in the worst case (a prompt injection),
the model can only ever receive *that one investor's already-authorised, minimal*
data — because the model is **never in the authorization path**. Authorization is
deterministic and upstream of the model.

[↑ Index](#index)

---

## 8. Data model (key entities)

Mirrors the dataset's grain:

```
companies (1) ──< deals(SPV) (1) ──< allocations >── (1) investors
                        │                 │
                        ├──< valuations   ├──< capital_calls
                        │                 ├──< fees
                        │                 └──< distributions
   fx_rates             └──────────────────< statement_lines >── investors
```

- **allocation** is the core grain (investor × deal): commitment, contributed,
  units, per-investor effective fees.
- **valuations**: time series per deal; latest mark drives current value.
- **statement_lines**: per-investor signed ledger.
- Add for production: `documents`, `kyc_records`, `nudges`, `actions`,
  `audit_log`, `sessions`.

[↑ Index](#index)

---

## 9. API design (key surfaces)

```
POST /v1/chat            {message, session_id}  → {answer, citations, trace}
GET  /v1/portfolio       (server derives investor from auth)
GET  /v1/obligations
GET  /v1/statement
POST /v1/actions/:type   (gated; returns pending-approval)
GET  /v1/nudges          / push subscription
```

- Investor identity comes from the authenticated session — **never a request
  parameter**.
- `/chat` returns the grounding trace so the client can render the panel.

[↑ Index](#index)

---

## 10. Request flows (sequences)

**A) Q&A**

```
user → gateway (authZ, investor_id) → orchestrator
orchestrator → model (tool menu only)         # decide
model → "position(company='Forgecraft')"
orchestrator → tool layer (scoped) → ledger mirror   # compute (deterministic)
tool → {figures + source IDs}
orchestrator → model (grounded result)        # render, personalised
model → final text + citations → grounding linter → user
```

**B) Proactive nudge**

```
fund-admin event (capital call due) → event bus → nudge engine
rules: due in 7d & unpaid → yes                # deterministic decision
nudge engine → tool layer (amount, FX) → figures
nudge engine → model (draft text)              # phrase only
→ (human approval if material) → push to iOS
```

[↑ Index](#index)

---

## 11. Key design decisions & trade-offs

| Decision | Why | Trade-off accepted |
|---|---|---|
| Deterministic maths, model language | Correctness/trust; numbers can't be hallucinated | More code than "ask the model"; worth it |
| Numbers from tools, prose from RAG | Avoids hallucinated figures | Two grounding paths to maintain |
| Ledger mirror, not live queries | Isolation, availability, shaped reads | Sync lag + reconciliation to build |
| Tool layer as internal MCP service | One shared, audited toolset across clients | Slight infra overhead vs in-process |
| Sonnet default, Opus on demand | Cost/latency; correctness carried by code | Routing logic to maintain |
| Human-in-the-loop for material actions | Compliance, reversibility | Not fully autonomous — by design |
| Modest-scale posture | Real base is 100s-1000s of LPs | Don't over-build for throughput |

[↑ Index](#index)

---

## 12. Failure modes & mitigations

- **Model hallucinates a number** → structurally impossible (tools own numbers) +
  grounding linter catches any leak.
- **Cross-investor leak** → row-level scope + closure; no tool parameter for
  another investor; red-team CI.
- **Ledger drift / stale mirror** → reconciliation + "as of" timestamps on
  answers; alert on divergence.
- **Source system down** → serve last-synced mirror; degrade gracefully.
- **Model gives advice / out-of-scope** → no-advice classifier + refusal +
  human escalation.
- **Over-automation** → gates on material/irreversible actions.
- **Cost spike** → caching + Sonnet default + token budgets; alert on anomalies.
- **Customer data leaves our boundary via the LLM** → send minimal, redact direct
  identifiers, late-bind sensitive values where possible, no-training/ZDR provider
  terms, encrypted + minimally-retained logs (§7.11).

[↑ Index](#index)

---

## 13. Scaling & evolution

- Scale is modest → vertical Postgres + read replicas is plenty; cache hot
  portfolios; the model provider handles inference scale.
- Evolve by adding tools (comparison within own portfolio, time-bounded queries,
  "what changed since last statement") — not by loosening grounding.
- Multi-region only if data residency demands it (Bedrock/Vertex path exists).

[↑ Index](#index)

---

## 14. Cost model (shape)

- **People dominate** (5-6 FTE).
- **Inference is low**: deterministic layer keeps prompts small; Sonnet carries
  most traffic; cacheable tool/system prefix; small grounded payloads.
- **SaaS** (KYC, e-sign, observability, vector store) is predictable per-seat/
  per-check.
- Net: intentionally cost-efficient; cost grows with investor count but bounded
  by caching and cheap-model routing.

[↑ Index](#index)

---

## 15. Six-month phasing

- **P0 Foundations (M0-1):** ledger mirror + event bus; tool layer as internal
  service; authZ; audit log; CI eval harness. Ships: hardened grounded Q&A
  (internal).
- **P1 Q&A in app (M1-2):** iOS chat, streaming, personalisation, citations;
  grounding linter online. Ships: grounded Q&A to a pilot cohort.
- **P2 Proactive (M2-3.5):** event-driven nudges; human-gated drafted comms.
  Ships: reminders + reporting export.
- **P3 Actions & onboarding (M3.5-5):** documents, KYC/AML, e-sign hand-off,
  onboarding wizard (human-in-the-loop). Ships: end-to-end onboarding.
- **P4 Hardening & GA (M5-6):** scale, red-team, compliance review, observability,
  cost tuning. Ships: GA to all investors.

[↑ Index](#index)

---

## In one paragraph

> "The whole system is organised around one boundary: deterministic code computes
> and decides — the numbers, the authorization, when to nudge — and the model
> only turns that into language. Everything else — the mirror, the eval harness,
> the guardrails, the human-in-the-loop gates — exists to protect that boundary,
> because in finance a confident wrong number is the worst possible outcome."

[↑ Index](#index)
