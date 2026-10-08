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
    "assurances", "maternite", "soins", "auth",  # "auth" : gestion des utilisateurs/groupes par l'admin
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

# Bloc opératoire (phases 5-6, CDC section 5)
_BLOC_REFERENTIEL = [
    "bloc_operatoire.view_salleoperatoire",
    "bloc_operatoire.view_typeintervention",
    "bloc_operatoire.view_materielbloc",
]
_BLOC_CHECKLIST = [
    "bloc_operatoire.add_etapechecklist",
    "bloc_operatoire.change_etapechecklist",
    "bloc_operatoire.view_etapechecklist",
]
_BLOC_LECTURE = _BLOC_REFERENTIEL + [
    "bloc_operatoire.view_intervention",
    "bloc_operatoire.view_membreequipe",
    "bloc_operatoire.view_etapechecklist",
    "bloc_operatoire.view_compterenduoperatoire",
]
_BLOC_EQUIPE = [
    "bloc_operatoire.add_membreequipe",
    "bloc_operatoire.change_membreequipe",
    "bloc_operatoire.delete_membreequipe",
    "bloc_operatoire.view_membreequipe",
]
_BLOC_CHIRURGIEN = _BLOC_LECTURE + _BLOC_CHECKLIST + _BLOC_EQUIPE + [
    "bloc_operatoire.add_intervention",
    "bloc_operatoire.change_intervention",
    "bloc_operatoire.add_compterenduoperatoire",
    "bloc_operatoire.change_compterenduoperatoire",
]
_BLOC_PROGRAMMATION = _BLOC_LECTURE + _BLOC_EQUIPE + [
    "bloc_operatoire.add_intervention",
    "bloc_operatoire.change_intervention",
    "bloc_operatoire.change_salleoperatoire",
    "bloc_operatoire.add_indisponibilitesalle",
    "bloc_operatoire.change_indisponibilitesalle",
    "bloc_operatoire.view_indisponibilitesalle",
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

# Laboratoire / imagerie (phase 7, CDC 4.6)
_LABO_PRESCRIRE = [
    "laboratoire.view_typeexamen",
    "laboratoire.add_demandeexamen",
    "laboratoire.change_demandeexamen",
    "laboratoire.view_demandeexamen",
    "laboratoire.add_ligneexamen",
    "laboratoire.view_ligneexamen",
    "laboratoire.view_resultat",
]
_LABO_EXECUTANT = [
    "laboratoire.view_typeexamen",
    "laboratoire.add_typeexamen",
    "laboratoire.view_demandeexamen",
    "laboratoire.change_demandeexamen",
    "laboratoire.view_ligneexamen",
    "laboratoire.add_resultat",
    "laboratoire.change_resultat",
    "laboratoire.view_resultat",
]

# Facturation & assurances (phase 6, CDC 4.8 / 4.9)
_ASSURANCE_LECTURE = [
    "assurances.view_assurance",
    "assurances.view_contratassurance",
    "assurances.view_patientassure",
]
_ASSURANCE_ADHESION = _ASSURANCE_LECTURE + [
    "assurances.add_patientassure",
    "assurances.change_patientassure",
]
_FACTURATION_COMPTABLE = _ASSURANCE_LECTURE + [
    "facturation.view_tarif",
    "facturation.add_facture",
    "facturation.change_facture",
    "facturation.view_facture",
    "facturation.add_lignefacture",
    "facturation.change_lignefacture",
    "facturation.delete_lignefacture",
    "facturation.view_lignefacture",
    "facturation.add_paiement",
    "facturation.view_paiement",
    "facturation.add_relance",
    "facturation.view_relance",
    "assurances.add_bordereauassurance",
    "assurances.change_bordereauassurance",
    "assurances.view_bordereauassurance",
    "assurances.view_lignebordereau",
    "assurances.add_patientassure",
    "assurances.change_patientassure",
]

# Maternité : dossier de grossesse et consultations prénatales
_MATERNITE_LECTURE = [
    "maternite.view_dossiergrossesse",
    "maternite.view_consultationprenatale",
]
_MATERNITE_SUIVI = _MATERNITE_LECTURE + [
    "maternite.add_dossiergrossesse",
    "maternite.change_dossiergrossesse",
    "maternite.add_consultationprenatale",
    "maternite.change_consultationprenatale",
]

# Soins : injections, pansements, pansements post-opératoires
_SOINS_LECTURE = ["soins.view_soin"]
_SOINS_REALISER = _SOINS_LECTURE + ["soins.add_soin", "soins.change_soin"]

PERMISSIONS_PAR_ROLE: dict[str, list[str]] = {
    Role.ADMIN: ["*"],
    Role.AGENT_ACCUEIL: [
        "patients.add_patient",
        "patients.change_patient",
        "patients.view_patient",
        "patients.view_dossiermedical",
        "facturation.view_facture",
    ] + _HOSPIT_ADMISSION + _ASSURANCE_ADHESION + _FACTURATION_COMPTABLE + _PHARMACIE + [
        # L'agent d'accueil cumule accueil, facturation, pharmacie et comptabilité.
        "consultations.view_consultation",
        "hospitalisation.view_hospitalisation",
        "bloc_operatoire.view_intervention",
    ],
    Role.MEDECIN: _SUIVI_MEDICAL + _PRESCRIRE + _HOSPIT_MEDECIN + _LABO_PRESCRIRE + _MATERNITE_SUIVI + [
        # Le médecin demande une intervention ; le chirurgien la réalise.
        "bloc_operatoire.add_intervention",
        "bloc_operatoire.view_intervention",
        "bloc_operatoire.view_compterenduoperatoire",
        "bloc_operatoire.view_salleoperatoire",
        "bloc_operatoire.view_typeintervention",
    ] + _SOINS_LECTURE,
    # La sage-femme suit la grossesse, hospitalise et prescrit dans la limite des
    # médicaments que l'hôpital lui autorise (Medicament.prescriptible_sage_femme).
    Role.SAGE_FEMME: (_SUIVI_MEDICAL + _PRESCRIRE + _LABO_PRESCRIRE + _MATERNITE_SUIVI
                      + _HOSPIT_MEDECIN + ["patients.add_patient"]),
    Role.CHIRURGIEN: (_SUIVI_MEDICAL + _PRESCRIRE + _HOSPIT_MEDECIN + _BLOC_CHIRURGIEN
                      + _LABO_PRESCRIRE + _SOINS_REALISER),
    # L'anesthésiste consulte, prescrit, demande des examens et participe aux interventions.
    Role.ANESTHESISTE: (_SUIVI_MEDICAL + _PRESCRIRE + _LABO_PRESCRIRE + _HOSPIT_SOIGNANT
                        + _BLOC_LECTURE + _BLOC_CHECKLIST + _SOINS_LECTURE + [
        "bloc_operatoire.change_intervention",  # validation de la faisabilité anesthésique
    ]),
    # L'infirmier consulte, prescrit, demande des examens et réalise les soins.
    Role.INFIRMIER: (_LECTURE_PATIENT + _PRESCRIRE + _LABO_PRESCRIRE + _HOSPIT_SOIGNANT
                     + _MATERNITE_LECTURE + _SOINS_REALISER),
    Role.IBODE: ["patients.view_patient", "patients.view_dossiermedical"]
    + _HOSPIT_LECTURE + _BLOC_LECTURE + _BLOC_CHECKLIST,
    Role.PHARMACIEN: ["patients.view_patient"] + _PHARMACIE,
    Role.LABORANTIN: ["patients.view_patient", "patients.view_dossiermedical"]
    + _LABO_EXECUTANT,
    Role.RADIOLOGUE: ["patients.view_patient", "patients.view_dossiermedical"]
    + _LABO_EXECUTANT,
    Role.COMPTABLE: ["patients.view_patient", "consultations.view_consultation",
                     "hospitalisation.view_hospitalisation",
                     "bloc_operatoire.view_intervention",
                     "pharmacie.view_dispensation"] + _FACTURATION_COMPTABLE,
    Role.CADRE_BLOC: ["patients.view_patient", "patients.view_dossiermedical"]
    + _BLOC_PROGRAMMATION,
    Role.AGENT_STERILISATION: [
        "bloc_operatoire.view_intervention",
        "bloc_operatoire.view_materielbloc",
        "bloc_operatoire.change_materielbloc",
    ],
}


def roles_avec_permission(codename_complet: str) -> set[str]:
    """Ensemble des rôles disposant de la permission donnée (utilitaire de test)."""
    resultat = set()
    for role, perms in PERMISSIONS_PAR_ROLE.items():
        if "*" in perms or codename_complet in perms:
            resultat.add(role)
    return resultat
