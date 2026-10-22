"""Same-problem vs different-problem classification (guide rule 12)."""
from __future__ import annotations

from backend.triage.context_builder import same_problem


def test_same_problem_shared_tokens():
    assert same_problem(
        "3048-2 Châtelets: Bruit de goutte d'eau dans le mur",
        "3048-2 Châtelets: Goutte d'eau mur salle de bain",
    )


def test_different_problem_unrelated():
    assert not same_problem(
        "3140-501 France-Prime: Frigo glace congélateur",
        "3140-501 France-Prime: Fourmis partout dans l'appartement",
    )


def test_empty_text_is_not_same():
    assert not same_problem("", "Fuite sous le lavabo")
    assert not same_problem("Fuite sous le lavabo", "")
