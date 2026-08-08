"""Chat loop entry point.

Usage:
    python -m src.cli --investor INV001
"""

from __future__ import annotations

import argparse
import os
import sys

from .loaders import load_dataset


def _load_env() -> None:
    """Load ANTHROPIC_API_KEY from a local .env if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="Investor Assistant")
    parser.add_argument(
        "--investor",
        default="INV001",
        help="The logged-in investor_id (assumed already authenticated).",
    )
    args = parser.parse_args()

    ds = load_dataset()
    if args.investor not in ds.investors:
        print(f"Unknown investor_id: {args.investor}", file=sys.stderr)
        return 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY is not set. Add it to a .env file (see .env.example) "
            "or export it. The offline report (python -m src.report) needs no key.",
            file=sys.stderr,
        )
        return 1

    try:
        from .assistant import InvestorAssistant
    except ImportError:
        print(
            "The 'anthropic' package is not installed. Run: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    try:
        assistant = InvestorAssistant(ds, args.investor)
    except Exception as exc:
        print(f"Failed to start assistant: {exc}", file=sys.stderr)
        return 1

    inv = ds.investors[args.investor]
    print(f"Investor Assistant — logged in as {inv['investor_name']} ({args.investor})")
    print(f"Reporting currency: {inv['reporting_currency']}. Type your question, or 'exit' to quit.\n")

    while True:
        try:
            question = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit", ":q"}:
            break
        try:
            answer = assistant.ask(question)
        except Exception as exc:
            print(f"[error] {type(exc).__name__}: {exc}\n", file=sys.stderr)
            continue
        print(f"\nassistant > {answer}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
