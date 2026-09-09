"""
Cartographie RBAC : rôle métier -> permissions Django (CDC 4.10 / 7.1).

Ce fichier est la source de vérité du contrôle d'accès. Les permissions sont
désignées par ``"<app_label>.<codename>"``. La valeur spéciale ``"*"`` accorde
toutes les permissions des applications gérées (réservée à l'administrateur).

À chaque phase du planning (CDC 11.2), les nouveaux modules ajoutent leurs
permissions ici plutôt que dans du code dispersé.
"""

from __future__ import annotations

from .models import Utilisateur

Role = Utilisateur.Role

# Applications dont les permissions sont pilotées par ce module.
APPS_GEREES = {
    "core", "accounts", "patients", "consultations", "pharmacie",
    "hospitalisation", "bloc_operatoire", "laboratoire", "facturation",
    "assurances", "auth",  # "auth" : gestion des utilisateurs/groupes par l'admin
}

_LECTURE_PATIENT = [
    "patients.view_patient",
    "patients.view_dossiermedical",
    "patients.view_allergie",
]

_SUIVI_MEDICAL = _LECTURE_PATIENT + [
    "patients.change_patient",
    "patients.change_dossiermedical",
    "patients.add_allergie",
    "patients.change_allergie",
    "patients.delete_allergie",
]

PERMISSIONS_PAR_ROLE: dict[str, list[str]] = {
    Role.ADMIN: ["*"],
    Role.AGENT_ACCUEIL: [
        "patients.add_patient",
        "patients.change_patient",
        "patients.view_patient",
        "patients.view_dossiermedical",
    ],
    Role.MEDECIN: list(_SUIVI_MEDICAL),
    Role.CHIRURGIEN: list(_SUIVI_MEDICAL),
    Role.ANESTHESISTE: list(_LECTURE_PATIENT),
    Role.INFIRMIER: list(_LECTURE_PATIENT),
    Role.IBODE: ["patients.view_patient", "patients.view_dossiermedical"],
    Role.PHARMACIEN: ["patients.view_patient"],
    Role.LABORANTIN: ["patients.view_patient"],
    Role.RADIOLOGUE: ["patients.view_patient"],
    Role.COMPTABLE: ["patients.view_patient"],
    Role.CADRE_BLOC: ["patients.view_patient"],
    Role.AGENT_STERILISATION: [],
}


def roles_avec_permission(codename_complet: str) -> set[str]:
    """Ensemble des rôles disposant de la permission donnée (utilitaire de test)."""
    resultat = set()
    for role, perms in PERMISSIONS_PAR_ROLE.items():
        if "*" in perms or codename_complet in perms:
            resultat.add(role)
    return resultat
