#!/usr/bin/env python3
"""Cron-friendly watchdog for Hermes context/cache pressure.

The script prints nothing when things look healthy. When it finds a session or
recent aggregate that looks risky, it emits a concise warning summary.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), __file__, *sys.argv[1:]])

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.context_pressure import format_context_pressure_lines
from agent.insights import InsightsEngine
from hermes_state import SessionDB


def _build_report(days: int) -> dict:
    db = SessionDB()
    try:
        engine = InsightsEngine(db)
        return engine.generate(days=days)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=1, help="Look back window for the watchdog")
    args = parser.parse_args()

    report = _build_report(max(1, args.days))
    pressure = report.get("context_pressure", {}) or {}
    aggregate = pressure.get("aggregate") or {}
    notable = pressure.get("sessions") or []

    should_report = (aggregate.get("status") or "ok") != "ok" or bool(notable)
    if not should_report:
        return 0

    lines = [f"🛡 Hermes context watchdog — last {args.days} day(s)"]
    if aggregate:
        lines.extend(format_context_pressure_lines(aggregate, markdown=True, include_summary=True))

    if notable:
        lines.append(f"Notable sessions: {len(notable)}")
        for item in notable[:3]:
            sess = item.get("session", {})
            assessment = item.get("assessment", {})
            short_id = str(sess.get("id", "?"))[:16]
            warning = (assessment.get("warnings") or ["attention needed"])[0]
            lines.append(f"• {short_id}: {warning}")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
