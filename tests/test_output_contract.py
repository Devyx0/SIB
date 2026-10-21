"""
34 gate checks duplicated from output_contract.py __main__.
output_contract.py itself is frozen — this file owns the pytest version.
"""
import pytest
from backend.triage.output_contract import validate

_BASE = {
    "verdict": "single", "duplicate_of_request_id": None, "addition_to_request_id": None,
    "title": "Robinet qui fuit", "problems": ["Fuite sous le lavabo"],
    "entry_permission": None, "urgency_tier": None,
    "complexity_tier": "C1", "congestion_level": "N2",
    "time_estimate_bucket": "UNDER_30_MIN", "delegable_status": "YES",
    "report_status": "CAN_WAIT", "routing_rule": "A1", "subcontractor_name": None,
    "vendor_id": None, "synergy_request_ids": [], "other_notes": None,
    "recommended_tasks": [{"description": "Réparer le robinet"}],
}


def chk(d, expected, conn=None, rid=1):
    result, _ = validate(d, conn, rid)
    assert result == expected


def test_clean_response():                    chk(_BASE, "accepted")
def test_assignee_field():                    chk({**_BASE, "assignee": "Jean Tremblay"}, "rejected_no_assignee_field")
def test_currency_in_problems():              chk({**_BASE, "problems": ["Loyer 500$ impayé"]}, "rejected_financial_content_problems")
def test_financial_term_loyer():              chk({**_BASE, "other_notes": "Voir pour le loyer"}, "rejected_financial_content")
def test_depot_with_amount():                 chk({**_BASE, "other_notes": "Dépôt de 500$ requis"}, "rejected_financial_content")
def test_depot_montant():                     chk({**_BASE, "other_notes": "dépôt: voir montant dû"}, "rejected_financial_content")
def test_depot_no_context():                  chk({**_BASE, "other_notes": "Dépôt de trousseau de clés"}, "accepted")
def test_home_depot_price():                  chk({**_BASE, "other_notes": "pièce vendue chez Home Depot (~15 $)"}, "accepted")
def test_code_colon_digit():                  chk({**_BASE, "entry_permission": "code: 4821"}, "rejected_access_code_content")
def test_code_clavier():                      chk({**_BASE, "entry_permission": "le code du clavier est 4821"}, "rejected_access_code_content")
def test_boite_combinaison():                 chk({**_BASE, "entry_permission": "boîte à clé #3 — combinaison 7729"}, "rejected_access_code_content")
def test_nip_porte():                         chk({**_BASE, "other_notes": "NIP de la porte : 1234"}, "rejected_access_code_content")
def test_building_number():                   chk({**_BASE, "title": "2160-4 Cardinal-Villeneuve: Robinet"}, "accepted")
def test_civic_addr_near_serrure():           chk({**_BASE, "other_notes": "serrure principale 3485-103 — historique"}, "accepted")
def test_request_ref_near_boite():            chk({**_BASE, "other_notes": "#7722 (boîte à clés, 2 juil, réglé) — suivi"}, "accepted")
def test_year_in_text():                      chk({**_BASE, "problems": ["Fin de bail le 2026-08-31"]}, "accepted")
def test_year_near_access_term():             chk({**_BASE, "other_notes": "Serrure à vérifier avant 2026-09-15"}, "accepted")
def test_request_id_ref():                    chk({**_BASE, "problems": ["voir demande originale #7042 du 10 juil"]}, "accepted")
def test_du_addr_near_keybox():               chk({**_BASE, "other_notes": "clés dans la keybox 2 du 3094 Châtelets — standard"}, "accepted")
def test_au_addr_near_serrure():              chk({**_BASE, "other_notes": "serrure externe de l'immeuble au 5875 Costebelle"}, "accepted")
def test_depot_dropoff_paiement():            chk({**_BASE, "problems": ["Paiement reçu. Accès autorisé pour dépôt sans présence du locataire."]}, "accepted")
def test_internal_vocab():                    chk({**_BASE, "other_notes": "Appliquer règle 6"}, "rejected_internal_vocabulary")
def test_routing_a2_no_gym():                 chk({**_BASE, "routing_rule": "A2", "subcontractor_name": "Duclos"}, "rejected_routing_inconsistent")
def test_routing_a3_no_sub():                 chk({**_BASE, "routing_rule": "A3", "subcontractor_name": None}, "rejected_routing_inconsistent")
def test_routing_a3_body_gym():               chk({**_BASE, "routing_rule": "A3", "subcontractor_name": "Body Gym"}, "rejected_routing_inconsistent")
def test_routing_a3_duclos():                 chk({**_BASE, "routing_rule": "A3", "subcontractor_name": "Duclos"}, "accepted")
def test_routing_a3b_no_duclos():             chk({**_BASE, "routing_rule": "A3b", "subcontractor_name": None}, "accepted")
def test_routing_a3b_rejects_duclos():        chk({**_BASE, "routing_rule": "A3b", "subcontractor_name": "Duclos"}, "rejected_routing_inconsistent")
def test_extermination_requires_eric():
    chk({**_BASE, "routing_rule": "A4", "problems": ["Fourmis partout"], "subcontractor_name": None}, "rejected_routing_inconsistent")
def test_extermination_eric_ok():
    chk({**_BASE, "routing_rule": "A4", "problems": ["Fourmis partout"], "subcontractor_name": "Éric"}, "accepted")
def test_c4_plumbing_requires_fortin():
    chk({**_BASE, "complexity_tier": "C4", "routing_rule": "A0", "problems": ["Colonne de plomberie bouchée"], "subcontractor_name": None}, "rejected_routing_inconsistent")
def test_c4_plumbing_fortin_ok():
    chk({**_BASE, "complexity_tier": "C4", "routing_rule": "A0", "problems": ["Colonne de plomberie bouchée"], "subcontractor_name": "Fortin"}, "accepted")
def test_a0_with_subcontractor():             chk({**_BASE, "routing_rule": "A0", "subcontractor_name": "H2Pro (piscine)"}, "accepted")
def test_a1_with_subcontractor():             chk({**_BASE, "routing_rule": "A1", "subcontractor_name": "H2Pro"}, "rejected_routing_inconsistent")
def test_addition_missing_ref():              chk({**_BASE, "verdict": "addition", "addition_to_request_id": None}, "rejected_invalid_addition_ref")
def test_addition_self_ref():                 chk({**_BASE, "verdict": "addition", "addition_to_request_id": 1}, "rejected_invalid_addition_ref", rid=1)
def test_parking_stationnement_a5():          chk({**_BASE, "title": "Activation borne recharge stationnement A5 (temporaire)"}, "accepted")
def test_parking_borne_a5_notes():            chk({**_BASE, "other_notes": "Clé borne stationnement A5 à programmer"}, "accepted")
def test_a5_sector_label_still_fires():       chk({**_BASE, "other_notes": "Périmètre A5 rive-sud — immeuble attitré"}, "rejected_internal_vocabulary")
def test_fiche_ref_before_digit():            chk({**_BASE, "other_notes": "Boîte à clé : voir fiche Chamonix 1175 pour accès"}, "accepted")
def test_fiche_ref_after_digit():             chk({**_BASE, "other_notes": "Fiche Sully 7885 (boîte à clé dans la fiche)"}, "accepted")
def test_urgent_plain_title_ok():             chk({**_BASE, "urgency_tier": "URGENT", "title": "3048-2 Châtelets: Goutte d'eau dans le mur"}, "accepted")
def test_medium_plain_title_ok():             chk({**_BASE, "urgency_tier": "Intermédiaire", "title": "125-103 Cèdres: Fourmis"}, "accepted")
def test_faible_ok():                         chk({**_BASE, "urgency_tier": "Faible", "title": "Peinture écaille couloir"}, "accepted")
def test_invalid_urgency_value():             chk({**_BASE, "urgency_tier": "HIGH"}, "rejected_invalid_urgency")
def test_employee_initials_rejected():        chk({**_BASE, "other_notes": "À voir avec CHGE demain"}, "rejected_assignee_initials")
def test_sdb_is_not_initials():               chk({**_BASE, "problems": ["Ventilateur SDB à réinstaller"]}, "accepted")
def test_duplicate_missing_mark():
    chk(
        {**_BASE, "verdict": "duplicate", "duplicate_of_request_id": 99,
         "title": "103 Cedres: Fuite"},
        "rejected_missing_doublon_mark",
    )
def test_single_must_not_set_refs():
    chk({**_BASE, "duplicate_of_request_id": 99}, "rejected_invalid_verdict_refs")
def test_duplicate_missing_ref():
    chk(
        {**_BASE, "verdict": "duplicate", "duplicate_of_request_id": None,
         "title": "103: DOUBLON POTENTIEL — Fuite"},
        "rejected_invalid_duplicate_ref",
    )


# ── recommended_tasks[] (Task 7) ──────────────────────────────────────────────

def _task(**kw):
    return {"description": "Réparer le robinet", **kw}


def test_single_requires_recommended_tasks():
    chk({**_BASE, "recommended_tasks": []}, "rejected_missing_recommended_tasks")


def test_single_missing_key_rejected():
    d = {k: v for k, v in _BASE.items() if k != "recommended_tasks"}
    chk(d, "rejected_missing_recommended_tasks")


def test_single_null_tasks_rejected():
    chk({**_BASE, "recommended_tasks": None}, "rejected_missing_recommended_tasks")


def test_accepts_two_tasks():
    d = {**_BASE, "recommended_tasks": [
        {"description": "Plomberie", "suggested_trade": "plomberie"},
        {"description": "Plancher", "urgency_tier": "Faible", "notes": "après la plomberie"},
    ]}
    chk(d, "accepted")
    assert len(d["recommended_tasks"]) == 2


def test_task_full_shape_accepted():
    chk({**_BASE, "routing_rule": "A0", "recommended_tasks": [_task(
        suggested_trade="plomberie", urgency_tier="URGENT", vendor_id=None,
        subcontractor_name="Fortin", notes=None,
    )]}, "accepted")


def test_duplicate_needs_no_tasks():
    chk({**_BASE, "verdict": "duplicate", "duplicate_of_request_id": 99,
         "title": "103: DOUBLON POTENTIEL — Fuite", "recommended_tasks": []}, "accepted")


def test_addition_tasks_optional():
    add = {**_BASE, "verdict": "addition", "addition_to_request_id": 99, "routing_rule": "A0"}
    chk({**add, "recommended_tasks": []}, "accepted")
    chk({**add, "recommended_tasks": [_task()]}, "accepted")


def test_exclusive_addition_requires_tasks():
    """Exclusive routing rewrites addition → single downstream, so it needs tasks like single."""
    for rule, sub in (("A1", None), ("A2", "Body Gym"), ("A3", "Duclos"), ("A3b", None), ("A4", "Éric")):
        add = {**_BASE, "verdict": "addition", "addition_to_request_id": 99,
               "routing_rule": rule, "subcontractor_name": sub, "problems": ["Autre problème"]}
        chk({**add, "recommended_tasks": []}, "rejected_missing_recommended_tasks")
        chk({**add, "recommended_tasks": [_task()]}, "accepted")
    chk({**_BASE, "verdict": "addition", "addition_to_request_id": 99, "routing_rule": "A5",
         "recommended_tasks": []}, "accepted")


def test_task_vendor_must_match_routing():
    chk({**_BASE, "recommended_tasks": [_task(subcontractor_name="Duclos")]}, "rejected_routing_inconsistent")
    chk({**_BASE, "routing_rule": "A0", "recommended_tasks": [_task(subcontractor_name="Body Gym")]},
        "rejected_routing_inconsistent")
    chk({**_BASE, "routing_rule": "A0", "recommended_tasks": [_task(subcontractor_name="Éric")]},
        "rejected_routing_inconsistent")
    chk({**_BASE, "routing_rule": "A3", "subcontractor_name": "Duclos",
         "recommended_tasks": [_task(subcontractor_name="Duclos")]}, "accepted")
    chk({**_BASE, "routing_rule": "A0", "recommended_tasks": [_task(subcontractor_name="Fortin")]}, "accepted")


def test_task_assignee_field_rejected():
    chk({**_BASE, "recommended_tasks": [_task(assignee="Jean")]}, "rejected_no_assignee_field")
    chk({**_BASE, "recommended_tasks": [_task(assigned_employee_id=4)]}, "rejected_no_assignee_field")


def test_task_description_required():
    chk({**_BASE, "recommended_tasks": [_task(description="  ")]}, "rejected_invalid_recommended_tasks")
    chk({**_BASE, "recommended_tasks": [{"suggested_trade": "plomberie"}]}, "rejected_invalid_recommended_tasks")


def test_task_shape_rejected():
    chk({**_BASE, "recommended_tasks": "Plomberie"}, "rejected_invalid_recommended_tasks")
    chk({**_BASE, "recommended_tasks": ["Plomberie"]}, "rejected_invalid_recommended_tasks")
    chk({**_BASE, "recommended_tasks": [_task(vendor_id="x")]}, "rejected_invalid_recommended_tasks")
    chk({**_BASE, "recommended_tasks": [_task(notes=5)]}, "rejected_invalid_recommended_tasks")


def test_task_invalid_urgency_rejected():
    chk({**_BASE, "recommended_tasks": [_task(urgency_tier="HIGH")]}, "rejected_invalid_urgency")


def test_task_financial_content_rejected():
    chk({**_BASE, "recommended_tasks": [_task(description="Réclamer le loyer")]}, "rejected_financial_content")
    chk({**_BASE, "recommended_tasks": [_task(notes="Dépôt de 500$ requis")]}, "rejected_financial_content")


def test_task_access_code_rejected():
    chk({**_BASE, "recommended_tasks": [_task(notes="clavier code 4821")]}, "rejected_access_code_content")


def test_task_internal_vocab_and_initials_rejected():
    chk({**_BASE, "recommended_tasks": [_task(description="Appliquer règle 6")]}, "rejected_internal_vocabulary")
    chk({**_BASE, "recommended_tasks": [_task(notes="À voir avec CHGE")]}, "rejected_assignee_initials")
