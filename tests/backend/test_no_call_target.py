"""François removed « aim for 8 to 14 per employee » on Oct 13 — never surface it in app code."""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCAN = [
    _ROOT / "backend" / "modules" / "analytics",
    _ROOT / "apps" / "web" / "src" / "pages" / "Dashboard",
    _ROOT / "apps" / "web" / "src" / "pages" / "Utilization",
]

# Patterns that would reintroduce the retired daily-call target.
_FORBIDDEN = (
    "8-14",
    "8–14",
    "8 to 14",
    "8 à 14",
    "8 a 14",
    "viser 8",
    "aim for 8",
    "calls/day",
    "appels/jour",
    "appels par employé",
    "calls per employee",
)


def test_no_daily_call_target_in_dashboard_utilization_code():
    hits: list[str] = []
    for base in _SCAN:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx", ".css", ".md"}:
                continue
            text = path.read_text(encoding="utf-8")
            for pat in _FORBIDDEN:
                if pat.lower() in text.lower():
                    hits.append(f"{path.relative_to(_ROOT)}: {pat!r}")
    assert hits == [], "Forbidden daily-call target wording:\n" + "\n".join(hits)
