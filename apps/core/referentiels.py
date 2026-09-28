"""Données de départ d'un nouvel hôpital : catalogues usuels modifiables ensuite.

Appelé à l'inscription, dans le contexte de l'établissement créé. Les montants
des tarifs sont des valeurs indicatives (FCFA) que l'hôpital ajuste ensuite.
"""

from __future__ import annotations

TARIFS = [
    ("CONS-STD", "Consultation standard", "CONSULTATION", 5000),
    ("HOSP-JOUR", "Journée d'hospitalisation", "HOSPIT_JOUR", 15000),
    ("BLOC-STD", "Acte de bloc (forfait)", "ACTE_BLOC", 150000),
    ("ANALYSE-STD", "Analyse / examen (forfait)", "ANALYSE", 3000),
]

EXAMENS = [
    # code, libellé, catégorie, unité, valeurs de référence
    ("NFS", "Numération formule sanguine", "BIOLOGIE", "", ""),
    ("GLY", "Glycémie à jeun", "BIOLOGIE", "g/L", "0.70 - 1.10"),
    ("CREAT", "Créatininémie", "BIOLOGIE", "mg/L", "7 - 13"),
    ("GE", "Goutte épaisse (paludisme)", "BIOLOGIE", "", ""),
    ("RXTHORAX", "Radiographie du thorax", "IMAGERIE", "", ""),
    ("ECHOABDO", "Échographie abdominale", "IMAGERIE", "", ""),
]

ACTES = [
    ("Appendicectomie", "Chirurgie viscérale", 60),
    ("Césarienne", "Gynéco-obstétrique", 45),
    ("Herniorraphie inguinale", "Chirurgie viscérale", 75),
    ("Cholécystectomie", "Chirurgie viscérale", 90),
]


def initialiser_referentiels() -> None:
    from apps.bloc_operatoire.models import TypeIntervention
    from apps.facturation.models import Tarif
    from apps.laboratoire.models import TypeExamen

    for code, libelle, categorie, montant in TARIFS:
        Tarif.objects.get_or_create(
            code=code, defaults={"libelle": libelle, "categorie": categorie, "montant": montant})
    for code, libelle, categorie, unite, ref in EXAMENS:
        TypeExamen.objects.get_or_create(
            code=code, defaults={"libelle": libelle, "categorie": categorie,
                                 "unite": unite, "valeurs_reference": ref})
    for libelle, specialite, duree in ACTES:
        TypeIntervention.objects.get_or_create(
            libelle=libelle, defaults={"specialite": specialite, "duree_standard_min": duree})
