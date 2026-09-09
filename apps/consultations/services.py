"""
Contrôles d'aide à la prescription (CDC 4.3).

``alertes_prescription`` renvoie des alertes **non bloquantes** :
- allergies déclarées du patient concordant avec un médicament prescrit ;
- interactions médicamenteuses connues entre deux lignes de l'ordonnance.
"""

from __future__ import annotations

from itertools import combinations

NIVEAU_INFO = "info"
NIVEAU_ATTENTION = "warning"
NIVEAU_DANGER = "danger"


def _mots(texte: str) -> set[str]:
    return {m for m in texte.lower().replace("-", " ").split() if len(m) >= 4}


def alertes_prescription(ordonnance) -> list[dict]:
    """Liste de dicts ``{"niveau": ..., "message": ...}``."""
    from apps.pharmacie.models import InteractionMedicamenteuse

    alertes: list[dict] = []
    lignes = list(ordonnance.lignes.select_related("medicament"))

    # --- Allergies du patient -------------------------------------------------
    dossier = getattr(ordonnance.patient, "dossier_medical", None)
    allergies = list(dossier.allergies.all()) if dossier else []
    for ligne in lignes:
        libelle_med = str(ligne.medicament).lower()
        mots_med = _mots(ligne.medicament.denomination)
        for allergie in allergies:
            mots_allergie = _mots(allergie.libelle)
            if allergie.libelle.lower() in libelle_med or (mots_med & mots_allergie):
                alertes.append({
                    "niveau": NIVEAU_DANGER if allergie.severite == "SEVERE"
                    else NIVEAU_ATTENTION,
                    "message": (
                        f"Allergie déclarée « {allergie.libelle} » "
                        f"({allergie.get_severite_display().lower()}) — "
                        f"médicament prescrit : {ligne.medicament}."
                    ),
                })

    # --- Interactions entre médicaments prescrits ---------------------------
    for l1, l2 in combinations(lignes, 2):
        interaction = InteractionMedicamenteuse.pour_paire(
            l1.medicament_id, l2.medicament_id
        )
        if interaction:
            niveau = (NIVEAU_DANGER
                      if interaction.gravite in {"MAJEURE", "CONTRE_INDIQUEE"}
                      else NIVEAU_ATTENTION)
            message = (
                f"Interaction {interaction.get_gravite_display().lower()} : "
                f"{l1.medicament.denomination} + {l2.medicament.denomination}."
            )
            if interaction.description:
                message += f" {interaction.description}"
            alertes.append({"niveau": niveau, "message": message})

    return alertes
