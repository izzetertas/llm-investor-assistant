# AI Workflow

How AI was used to build this project, what was kept, what was changed, and how
the output was verified.

## Index

- **[AI Workflow](#ai-workflow)**
  - [Which AI tools and models, and for what](#which-ai-tools-and-models-and-for-what)
  - [How much of the code was AI-generated](#how-much-of-the-code-was-ai-generated)
  - [What was rejected or materially changed from AI suggestions](#what-was-rejected-or-materially-changed-from-ai-suggestions)
  - [How the answers were verified](#how-the-answers-were-verified)
  - [Next steps](#next-steps)

---

## Which AI tools and models, and for what

- **Claude (Opus-class, via an agentic coding assistant)** — the primary build
  tool. Used to: read the dataset guide, inspect the CSV schemas,
  propose the architecture, scaffold and write the Python modules, design the
  edge-case test suite, and draft the docs.
- **Claude Sonnet 4.6 (`claude-sonnet-4-6`)** — the model the *product itself*
  runs on at runtime, for the conversational tool-use loop. Chosen over an
  Opus-tier model because correctness is carried by the deterministic layer, so
  the model only needs strong tool-use and instruction-following — which Sonnet
  does well at a fraction of the cost and latency. Adaptive thinking is enabled.

The split is the whole point of the design: AI writes the *prose*; deterministic
Python computes the *numbers*.

[↑ Index](#index)

## How much of the code was AI-generated

~90% of the lines. But the *decisions* were human-directed and
that is where the value sat: the deterministic-compute-plus-citations
architecture, the security boundary (investor_id bound in a closure, never a
tool argument), the choice of which edge cases to test, and the model choice.
AI was fast at turning those decisions into clean, consistent code; it was not
trusted to decide what "correct" meant.

[↑ Index](#index)

## What was rejected or materially changed from AI suggestions

- **Letting the model do arithmetic / read raw CSVs.** The most tempting
  shortcut — dump the rows into the prompt and ask for the answer — was rejected
  outright. LLMs are unreliable at multi-step FX conversion, MOIC, and joins,
  and a grounded answer beats a confident wrong one. All
  maths lives in `metrics.py`; the model is forbidden (in the system prompt and
  by construction) from computing figures.
- **Text-to-SQL / code-execution tooling.** Considered and rejected as
  over-engineering at this scope — both weaken the grounding
  guarantee (the model could generate a wrong query) for no benefit at this
  scope.
- **MCP for the tool layer.** A reasonable production pattern, but overkill for a
  single-process CLI. Kept the tools in-process but separated the *pure*
  functions from the *schemas/dispatch* so they could be re-exposed over MCP
  later without touching `metrics.py`. (See `system-design.md`.)
- **"current_value = units × latest mark" without adjusting for realised units.**
  The first cut ignored partial secondaries. Changed to `remaining_units ×
  mark`, so Tallybook's 30%-sold / 70%-live position is correct.
- **Treating pending allocations as zero MOIC.** Changed to *undefined* (None),
  because dividing realised value by zero contributed capital is meaningless and
  reporting "0×" would mislead.
- **Decimal vs float.** AI defaulted to float; kept it for the prototype but
  flagged fixed-point as a production requirement in the README — a deliberate,
  documented trade-off rather than a silent one.

[↑ Index](#index)

## How the answers were verified

Verification targets the deterministic layer, because that is where the numbers
come from:

1. **An offline report path (`python -m src.report`)** prints every figure and
   its source row IDs with no model in the loop — so the maths can be checked
   directly against the CSVs.
2. **A 12-test suite** asserting the dataset's deliberate trap cases:
   - Exit (Helianthe): live value 0 but MOIC includes the distribution
     (verified: 127,875 ÷ 93,000 = 1.375).
   - Write-off (Yappio): value 0 and a loss.
   - Partial secondary (Tallybook): realised 0.3 / remaining 0.7 split.
   - Pending allocation: contributed 0, MOIC undefined.
   - Zero-holding investor: empty portfolio, MOIC None.
   - Similar names (Northpeak): resolves to two candidates, refuses to guess.
   - Multi-round (Forgecraft): aggregate equals sum of per-round reporting-ccy
     values.
   - Fee discount flag matches a genuinely-below-standard effective rate.
   - FX routes EUR→GBP via USD correctly.
   - Investor isolation: the dispatch only ever returns the bound investor's
     allocations.
   - MOIC definition holds for every allocation.
3. **Hand-checks against rows** I read directly (e.g. INV001's Series B 40%
   uncalled commitment surfacing as the exact upcoming capital call).
4. **Grounding by contract:** the system prompt forbids invented numbers and
   requires citing the source row IDs the tools return, so anyone can trace
   any figure in an answer back to a CSV row.
5. **Live answer + guardrail testing**, which caught a real bug: the single-
   position tool returned per-round `current_value` in *deal* currency but the
   total in *reporting* currency, and the model rendered the deal-currency
   per-round figures with the reporting currency's symbol (USD values shown as
   £). Fixed by adding explicit `_reporting` fields per round and instructing the
   model to use them and never FX-convert itself. The guardrails themselves
   verified clean: it declines investment advice, refuses cross-investor
   comparisons (no tool can name another investor), won't compute an IRR it has
   no data for, and won't forecast.

[↑ Index](#index)

## Next steps

1. **A golden-answer eval set + grader.** ~40 question/expected-figure pairs
   spanning every tool and trap, with an automated check that the assistant's
   stated numbers match the deterministic ground truth and that every figure is
   cited. This is the single highest-value addition for reliability.
2. **An answer-grounding linter.** Post-process each reply: extract every number,
   confirm it appears in a tool result for that turn, and flag any ungrounded
   figure before it reaches the user.
3. **Broaden coverage:** a `compare_holdings` / concentration tool, time-bounded
   queries ("fees due this quarter"), and a "what changed since last statement"
   diff.
4. **Decimal/fixed-point money** throughout, with currency-aware rounding rules.
5. **Wrap the tools as an MCP server** so the same grounded tools serve the CLI,
   a web UI, and the future iOS bot from one place.

[↑ Index](#index)
