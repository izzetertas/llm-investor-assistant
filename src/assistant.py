"""The conversational layer: a manual Claude tool-use loop.

The model's only jobs are (1) choose which deterministic tool to call and (2)
turn the grounded result into a personalised, plain-language answer with
citations. It never computes figures and never sees another investor's data.
"""

from __future__ import annotations

import json

import anthropic

from .loaders import Dataset
from .personalize import investor_signals, personalisation_directive
from .tools import TOOL_SCHEMAS, build_dispatch

MODEL = "claude-sonnet-4-6"
# Safety cap on the agentic tool loop — bounds a runaway model that keeps
# calling tools without converging. In practice it settles in 1-3 rounds.
MAX_TOOL_ITERATIONS = 8

# Stable across all investors -> cacheable prefix. Keep byte-identical.
BASE_SYSTEM = """You are the Investor Assistant. You answer an investor's questions about THEIR OWN portfolio, in plain language, grounded strictly in the tools provided.

Hard rules:
- NEVER compute, estimate, or guess any figure yourself. Every number — value, MOIC, fee, FX-converted total — comes from a tool result. If a tool did not return a number, say you don't have it; do not invent one.
- Call a tool whenever the answer depends on the investor's data. You may call several tools for one question (e.g. portfolio + obligations) and combine them.
- Cite your sources. After stating figures, reference the source row IDs the tool returned (e.g. "source: ALC0001, VAL003"). Keep citations compact.
- You only ever serve the one logged-in investor. There is no way to access anyone else's data; never imply otherwise.
- Report figures in the investor's reporting currency unless they ask otherwise; mention the currency. Tool results may carry the same figure in two currencies: deal-currency fields (what the investor paid/holds) and reporting-currency fields suffixed `_reporting`. For display and totals always use the `_reporting` fields; if you quote a deal-currency figure (e.g. an entry share price), label its currency explicitly. Never FX-convert a number yourself — only use the values the tools return.
- Be honest about uncertainty and edge cases: pending/unfunded commitments are not deployed capital; exited or written-off rounds have zero live value but may have realised distributions; "invested" is ambiguous between committed and contributed — distinguish them.
- If a company name is ambiguous (the tool returns candidates), ask which one they mean rather than guessing.
- Format for a chat window: lead with the figure that answers the question, then keep it scannable with short paragraphs and compact bullet points. A small Markdown table is fine when listing several holdings; avoid large headings, horizontal rules, and walls of text.

Personalisation changes only tone, depth, and framing — never the numbers."""


class InvestorAssistant:
    def __init__(self, ds: Dataset, investor_id: str, client: anthropic.Anthropic | None = None):
        if investor_id not in ds.investors:
            raise ValueError(f"Unknown investor_id: {investor_id}")
        self.ds = ds
        self.investor_id = investor_id
        self.client = client or anthropic.Anthropic()
        self.dispatch = build_dispatch(ds, investor_id)
        self.signals = investor_signals(ds, investor_id)
        self.messages: list[dict] = []

        directive = personalisation_directive(self.signals)
        self.system = [
            {"type": "text", "text": BASE_SYSTEM, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "Investor profile for this session:\n" + directive},
        ]

    def _run_tool(self, name: str, args: dict) -> str:
        """Execute one deterministic tool and return its JSON result as a string."""
        fn = self.dispatch.get(name)
        if fn is None:
            return json.dumps({"error": f"unknown tool {name}"})
        try:
            result = fn(**args)
        except Exception as exc:  # surfaced to the model as a tool error
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        return json.dumps(result, default=str)

    def ask(self, user_message: str) -> str:
        """Send a user turn, run the tool loop, return the final assistant text."""
        text, _ = self.ask_with_trace(user_message)
        return text

    def ask_with_trace(self, user_message: str) -> tuple[str, list[dict]]:
        """Like `ask`, but also returns the tool calls made and the source row
        IDs each returned — so a UI can show how an answer was grounded."""
        self.messages.append({"role": "user", "content": user_message})
        trace: list[dict] = []

        for _ in range(MAX_TOOL_ITERATIONS):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=2000,
                system=self.system,
                tools=TOOL_SCHEMAS,
                thinking={"type": "adaptive"},
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return _final_text(response), trace

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    out = self._run_tool(block.name, block.input)
                    trace.append({"tool": block.name, "args": block.input, "sources": _sources(out)})
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": out}
                    )
            self.messages.append({"role": "user", "content": tool_results})

        # Hit the tool-call cap without converging. Make one final call that
        # forbids tools (tool_choice=none) so the model must return text — this
        # also keeps the message history valid (no dangling tool_use).
        final = self.client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=self.system,
            tools=TOOL_SCHEMAS,
            tool_choice={"type": "none"},
            thinking={"type": "adaptive"},
            messages=self.messages,
        )
        self.messages.append({"role": "assistant", "content": final.content})
        return _final_text(final), trace


def _final_text(response) -> str:
    parts = [b.text for b in response.content if b.type == "text"]
    return "\n".join(parts).strip() or "(no answer)"


def _sources(tool_output_json: str) -> list[str]:
    """Pull the source row IDs out of a tool result, for the grounding panel."""
    try:
        parsed = json.loads(tool_output_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, dict) and isinstance(parsed.get("sources"), list):
        return [str(s) for s in parsed["sources"]]
    return []
