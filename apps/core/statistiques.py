"""
Statistiques générales de pilotage (CDC 4.10 — « activité, fréquentation,
chiffre d'affaires »).

Agrège les compteurs des différents modules déjà pourvus de leur propre
logique (ex. ``apps.bloc_operatoire.stats``) plutôt que de dupliquer les
requêtes ici.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone


def _bornes(depuis, jusqu):
    jusqu = jusqu or timezone.localdate()
    depuis = depuis or (jusqu - timedelta(days=30))
    return depuis, jusqu


def frequentation(depuis=None, jusqu=None) -> dict:
    from apps.consultations.models import Consultation
    from apps.hospitalisation.models import Hospitalisation, Service
    from apps.laboratoire.models import DemandeExamen
    from apps.patients.models import Patient

    depuis, jusqu = _bornes(depuis, jusqu)
    periode = {"date_consultation__date__range": (depuis, jusqu)}

    total_lits = sum(s.nb_lits for s in Service.objects.filter(actif=True))
    lits_occupes = sum(s.nb_lits_occupes for s in Service.objects.filter(actif=True))

    return {
        "patients_total": Patient.objects.actifs().count(),
        "nouveaux_patients": Patient.objects.filter(
            cree_le__date__range=(depuis, jusqu)).count(),
        "consultations": Consultation.objects.filter(**periode).count(),
        "admissions": Hospitalisation.objects.filter(
            date_admission__date__range=(depuis, jusqu)).count(),
        "sorties": Hospitalisation.objects.filter(
            date_sortie__date__range=(depuis, jusqu)).count(),
        "taux_occupation_lits": (round(100 * lits_occupes / total_lits)
                                 if total_lits else 0),
        "examens_demandes": DemandeExamen.objects.filter(
            date_demande__date__range=(depuis, jusqu)).count(),
        "examens_valides": DemandeExamen.objects.filter(
            date_demande__date__range=(depuis, jusqu), statut="VALIDEE").count(),
    }


def chiffre_affaires(depuis=None, jusqu=None) -> dict:
    from apps.facturation.models import Facture, Paiement

    depuis, jusqu = _bornes(depuis, jusqu)
    factures = Facture.objects.filter(
        date_emission__range=(depuis, jusqu)).exclude(statut=Facture.Statut.ANNULEE)
    encaisse = Decimal("0")
    for p in Paiement.objects.filter(date_paiement__date__range=(depuis, jusqu)):
        encaisse += -p.montant if p.est_remboursement else p.montant

    return {
        "nb_factures": factures.count(),
        "montant_facture": sum((f.montant_total for f in factures), Decimal("0")),
        "part_assurance": sum((f.part_assurance for f in factures), Decimal("0")),
        "part_patient": sum((f.part_patient for f in factures), Decimal("0")),
        "encaisse_periode": encaisse,
        "impayes_total": sum(
            (f.reste_a_payer for f in Facture.objects.filter(
                statut__in=[Facture.Statut.EMISE, Facture.Statut.PARTIELLE])),
            Decimal("0"),
        ),
    }


def activite_par_module(depuis=None, jusqu=None) -> dict:
    from apps.bloc_operatoire.models import Intervention
    from apps.pharmacie.models import Dispensation, Medicament

    depuis, jusqu = _bornes(depuis, jusqu)
    return {
        "interventions": Intervention.objects.filter(
            date_demande__date__range=(depuis, jusqu)).count(),
        "interventions_terminees": Intervention.objects.filter(
            date_demande__date__range=(depuis, jusqu),
            statut=Intervention.Statut.TERMINEE).count(),
        "dispensations": Dispensation.objects.filter(
            cree_le__date__range=(depuis, jusqu)).count(),
        "medicaments_en_alerte": sum(1 for m in Medicament.objects.filter(actif=True)
                                     if m.en_alerte),
    }


def tableau_de_bord_general(depuis=None, jusqu=None) -> dict:
    depuis, jusqu = _bornes(depuis, jusqu)
    return {
        "periode": {"depuis": depuis, "jusqu": jusqu},
        "frequentation": frequentation(depuis, jusqu),
        "chiffre_affaires": chiffre_affaires(depuis, jusqu),
        "activite": activite_par_module(depuis, jusqu),
    }
