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

# Consultation + constantes + ordonnances (phase 3, CDC 4.2 / 4.3)
_PRESCRIRE = [
    "consultations.add_consultation",
    "consultations.change_consultation",
    "consultations.view_consultation",
    "consultations.add_constantes",
    "consultations.change_constantes",
    "consultations.view_constantes",
    "consultations.add_ordonnance",
    "consultations.change_ordonnance",
    "consultations.view_ordonnance",
    "consultations.add_ligneordonnance",
    "consultations.change_ligneordonnance",
    "consultations.delete_ligneordonnance",
    "consultations.view_ligneordonnance",
    "pharmacie.view_medicament",
    "pharmacie.view_interactionmedicamenteuse",
]

_RELEVER_CONSTANTES = [
    "consultations.view_consultation",
    "consultations.add_constantes",
    "consultations.change_constantes",
    "consultations.view_constantes",
    "consultations.view_ordonnance",
]

# Hospitalisation : séjours, lits, suivi (phase 4, CDC 4.4)
_HOSPIT_LECTURE = [
    "hospitalisation.view_service",
    "hospitalisation.view_chambre",
    "hospitalisation.view_lit",
    "hospitalisation.view_hospitalisation",
    "hospitalisation.view_notesuivi",
    "hospitalisation.view_mouvementlit",
]
_HOSPIT_SOIGNANT = _HOSPIT_LECTURE + [
    "hospitalisation.add_notesuivi",
    "hospitalisation.change_notesuivi",
]
_HOSPIT_MEDECIN = _HOSPIT_SOIGNANT + [
    "hospitalisation.add_hospitalisation",
    "hospitalisation.change_hospitalisation",
]
_HOSPIT_ADMISSION = _HOSPIT_LECTURE + [
    "hospitalisation.add_hospitalisation",
    "hospitalisation.change_hospitalisation",
]

# Officine : catalogue, stock, dispensation (phase 3, CDC 4.5)
_PHARMACIE = [
    "consultations.view_consultation",
    "consultations.view_ordonnance",
    "consultations.view_ligneordonnance",
    "pharmacie.add_medicament",
    "pharmacie.change_medicament",
    "pharmacie.view_medicament",
    "pharmacie.add_lotmedicament",
    "pharmacie.change_lotmedicament",
    "pharmacie.view_lotmedicament",
    "pharmacie.add_mouvementstock",
    "pharmacie.view_mouvementstock",
    "pharmacie.add_dispensation",
    "pharmacie.change_dispensation",
    "pharmacie.view_dispensation",
    "pharmacie.add_lignedispensation",
    "pharmacie.view_lignedispensation",
    "pharmacie.view_interactionmedicamenteuse",
]

PERMISSIONS_PAR_ROLE: dict[str, list[str]] = {
    Role.ADMIN: ["*"],
    Role.AGENT_ACCUEIL: [
        "patients.add_patient",
        "patients.change_patient",
        "patients.view_patient",
        "patients.view_dossiermedical",
    ] + _HOSPIT_ADMISSION,
    Role.MEDECIN: _SUIVI_MEDICAL + _PRESCRIRE + _HOSPIT_MEDECIN,
    Role.CHIRURGIEN: _SUIVI_MEDICAL + _PRESCRIRE + _HOSPIT_MEDECIN,
    Role.ANESTHESISTE: _LECTURE_PATIENT + [
        "consultations.view_consultation",
        "consultations.view_constantes",
        "consultations.view_ordonnance",
    ] + _HOSPIT_LECTURE,
    Role.INFIRMIER: _LECTURE_PATIENT + _RELEVER_CONSTANTES + _HOSPIT_SOIGNANT,
    Role.IBODE: ["patients.view_patient", "patients.view_dossiermedical"] + _HOSPIT_LECTURE,
    Role.PHARMACIEN: ["patients.view_patient"] + _PHARMACIE,
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
