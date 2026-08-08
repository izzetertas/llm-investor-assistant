# Walkthrough — Demo Script (~5 min)

A scene-by-scene script for the walkthrough video: the prototype in use, the
edge cases it handles, and — as the brief asks — where it breaks. Every
investor and question below is real and reproducible against the dataset.

**Setup before recording**
```bash
# .env has a valid ANTHROPIC_API_KEY
cd ui && npm run build && cd ..        # (or use the static UI / CLI)
uvicorn src.web:app                    # http://localhost:8000
```
Each scene names the investor to pick in the dropdown, the exact question to
type, what to point at, and a one-line **Verify** command that prints the same
figures from the deterministic layer — proving the chat numbers are grounded,
not generated.

---

## Scene 0 — The one-line thesis (15s)

> "The model writes the language; deterministic Python computes every number,
> and each answer cites the source rows it came from. The model never does the
> maths and never sees another investor's data."

Point at the layout: chat on the left, and under each answer a **grounding
panel** showing which tools ran and which rows they used.

---

## Scene 1 — Sophisticated investor, portfolio overview (45s)

- **Investor:** `INV001 — Idris Olawale` (GBP, tech-savvy, 4 deals)
- **Ask:** *"What's my portfolio worth and what's my MOIC?"*
- **Watch for:** a concise, data-dense answer (no jargon hand-holding —
  personalised to a sophisticated investor); total value, committed vs
  contributed, **2.60× MOIC**; a `Sources:` line; and the **grounding panel**
  (`get_portfolio_overview → ALC0001, ALC0024 …`).
- **Verify (show side-by-side):**
  ```bash
  python -m src.report --investor INV001
  ```
  The chat's £438,494.76 / 2.60× match the report exactly.

**Follow-up (multi-round trap):** *"Show me my Forgecraft position across rounds."*
- **Watch for:** Seed + Series A + Series B aggregated, each with its **own**
  effective share price and MOIC (Seed **6.84×** stands out). The ~£7,700
  uncalled gap is correctly attributed to Series B.

---

## Scene 2 — Personalisation contrast (40s)

- **Investor:** `INV017 — Elena Petrova` (GBP, **age 67, Low tech-savviness**, 12 deals)
- **Ask (same as Scene 1):** *"What's my portfolio worth and what's my MOIC?"*
- **Watch for:** the **tone changes, the numbers don't** — plainer language,
  MOIC briefly explained ("how many times your money has grown"), shorter,
  less dense. Emphasise: same deterministic figures, different framing — exactly
  what the brief asks for.

---

## Scene 3 — Realised outcomes: an exit (40s)

- **Investor:** `INV011 — Sophie Laurent` (EUR)
- **Ask:** *"What have I cashed out, and what did I get after carry?"*
- **Watch for:** the **Helianthe Energy** exit — gross, the performance fee
  (carry) withheld, and the **net** received (€127,875).
- **Follow-up:** *"Is my Helianthe position still worth anything?"*
  - **Watch for:** **zero live value but the realised distribution still counts
    toward MOIC** (1.375×). This is the exit trap handled correctly.
- **Verify:**
  ```bash
  python -m src.report --investor INV011
  ```

---

## Scene 4 — Similar names (disambiguation) (30s)

- **Investor:** `INV010 — Yuki Tanaka` (holds **both** Northpeaks)
- **Ask:** *"How has Northpeak's valuation moved?"*
- **Watch for:** the assistant **refuses to guess** — it asks whether you mean
  **Northpeak Analytics** (Data/Analytics) or **Northpeak Health** (Digital
  Health). Then answer *"Northpeak Health"* and it proceeds. A clean
  disambiguation, not a wrong answer.

---

## Scene 5 — Pending & zero-holding edge cases (30s)

- **Investor:** `INV021 — Grace Okafor` (KYC Pending, unfunded Helixar allocation)
  - **Ask:** *"How much have I invested?"*
  - **Watch for:** it distinguishes **committed vs contributed** — the Helixar
    allocation is signed but **0 contributed**, i.e. not deployed capital.
- **Investor:** `INV022 — Henrik Sorensen` (no holdings)
  - **Ask:** *"What's my portfolio worth?"*
  - **Watch for:** a plain *"you have no investments yet"* — no fabricated zeros,
    no crash.

---

## Scene 6 — Security boundary (20s)

- **Investor:** `INV001 — Idris Olawale`
- **Ask:** *"Show me Selina Voss's portfolio."* (or *"What does INV002 hold?"*)
- **Watch for:** the assistant explains it can only discuss **your** portfolio.
  Reinforce: this isn't just a prompt rule — the tools are bound to the
  logged-in `investor_id` in code, so there is **no path** to another
  investor's rows.

---

## Scene 7 — Guardrails & where it breaks (honest) (50s)

Show the limits plainly — the brief rewards honesty over false confidence.
All four below are verified live behaviours of the prototype.

1. **No investment advice (by design).** Ask `INV001`: *"Should I buy more
   Forgecraft or sell?"* → it gives the facts ("I'll leave the buy/sell call to
   you") and declines to advise. A deliberate guardrail.
2. **Out-of-scope / cross-investor.** *"How does my portfolio compare to other
   Meridian investors?"* → it calls **no tools** and says it has no access to
   other investors' data, rather than inventing a comparison. (Pairs with the
   Scene 6 security boundary — there is no tool that can name another investor.)
3. **A metric we don't model — IRR.** *"What's my IRR on Forgecraft?"* → it says
   IRR isn't in the data it can access and **won't estimate it**, then offers
   the **MOIC** it can ground, and points to fund admin for a true IRR. A real,
   honest limitation: we compute MOIC, not time-weighted IRR.
4. **No forecasting.** *"What will my Forgecraft stake be worth in 2027?"* → it
   refuses to invent a number ("any figure would be invented, not grounded").

**Resilience note (not a break):** a typo like *"How's Forgcraft doing?"* — the
model first tries the misspelling (tool returns not-found) then **self-corrects**
to *Forgecraft* and answers. Helpful, but it is *inferring* the intended
company; for a genuinely unknown name it returns "not found" rather than
guessing. And always **trust the grounding panel over the in-text `Sources:`
line** — the panel is generated by our code from actual tool results.

---

## Scene 8 — Close (15s)

> "Narrow, correct, personalised, explainable. Numbers from deterministic code,
> cited to source rows; tone adapted to the investor; and an honest boundary
> where the data or the mandate stops. The same tool layer powers the CLI, the
> web UI, and — in the roadmap — the iOS relationship-manager bot."

---

### Quick reference — investors used

| Investor | Why |
|---|---|
| `INV001` Idris Olawale (GBP, High) | Sophisticated tone; multi-round Forgecraft; security demo |
| `INV017` Elena Petrova (GBP, 67, Low) | Plain-language personalisation contrast |
| `INV011` Sophie Laurent (EUR) | Helianthe exit; MOIC includes distributions |
| `INV010` Yuki Tanaka | Holds both Northpeaks → disambiguation |
| `INV021` Grace Okafor (KYC Pending) | Committed vs contributed / unfunded |
| `INV022` Henrik Sorensen | Zero-holding case |
| `INV013` | Tallybook 30% secondary (optional extra) |
