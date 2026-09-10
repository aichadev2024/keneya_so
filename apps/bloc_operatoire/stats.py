"""
Indicateurs de pilotage du bloc opératoire (CDC 5.3.7).

L'export PDF/Excel est prévu en phase 9 ; ces fonctions produisent les données.
Les durées sont calculées en Python (portable SQLite / PostgreSQL).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from .models import Intervention, SalleOperatoire


def _bornes(depuis, jusqu):
    jusqu = jusqu or timezone.now()
    depuis = depuis or (jusqu - timedelta(days=30))
    return depuis, jusqu


def _interventions_terminees(depuis, jusqu):
    return (
        Intervention.objects.filter(
            statut=Intervention.Statut.TERMINEE,
            heure_debut_intervention__isnull=False,
            heure_fin_intervention__isnull=False,
            heure_debut_intervention__gte=depuis,
            heure_fin_intervention__lte=jusqu,
        )
        .select_related("type_intervention", "chirurgien_principal", "salle")
    )


def _duree_min(i) -> float:
    return (i.heure_fin_intervention - i.heure_debut_intervention).total_seconds() / 60


def taux_occupation_salles(depuis=None, jusqu=None) -> list[dict]:
    depuis, jusqu = _bornes(depuis, jusqu)
    heures_periode = max((jusqu - depuis).total_seconds() / 3600, 1)
    minutes_par_salle = defaultdict(float)
    compte_par_salle = defaultdict(int)
    for i in _interventions_terminees(depuis, jusqu):
        if i.salle_id:
            minutes_par_salle[i.salle_id] += _duree_min(i)
            compte_par_salle[i.salle_id] += 1
    resultats = []
    for salle in SalleOperatoire.objects.filter(actif=True):
        h = minutes_par_salle[salle.id] / 60
        resultats.append({
            "salle": salle.nom,
            "interventions": compte_par_salle[salle.id],
            "heures_intervention": round(h, 1),
            "taux_occupation_pct": round(100 * h / heures_periode, 1),
        })
    return resultats


def _moyenne_par(cle, depuis, jusqu):
    total = defaultdict(float)
    compte = defaultdict(int)
    for i in _interventions_terminees(depuis, jusqu):
        k = cle(i)
        total[k] += _duree_min(i)
        compte[k] += 1
    return [
        {"cle": k, "interventions": compte[k],
         "duree_moyenne_min": round(total[k] / compte[k], 1)}
        for k in sorted(total, key=lambda x: -compte[x])
    ]


def duree_moyenne_par_type(depuis=None, jusqu=None) -> list[dict]:
    depuis, jusqu = _bornes(depuis, jusqu)
    rows = _moyenne_par(lambda i: i.type_intervention.libelle, depuis, jusqu)
    return [{"type": r["cle"], **{k: v for k, v in r.items() if k != "cle"}} for r in rows]


def duree_moyenne_par_praticien(depuis=None, jusqu=None) -> list[dict]:
    depuis, jusqu = _bornes(depuis, jusqu)
    rows = _moyenne_par(
        lambda i: (i.chirurgien_principal.get_full_name()
                   or i.chirurgien_principal.username),
        depuis, jusqu,
    )
    return [{"praticien": r["cle"], **{k: v for k, v in r.items() if k != "cle"}}
            for r in rows]


def taux_deprogrammation(depuis=None, jusqu=None) -> dict:
    depuis, jusqu = _bornes(depuis, jusqu)
    base = Intervention.objects.filter(date_demande__gte=depuis, date_demande__lte=jusqu)
    total = base.count()
    reportees = base.filter(statut__in=[Intervention.Statut.ANNULEE,
                                        Intervention.Statut.REPORTEE])
    motifs = list(reportees.exclude(motif_annulation="")
                  .values_list("reference", "motif_annulation"))
    return {
        "total": total,
        "annulees_reportees": reportees.count(),
        "taux_pct": round(100 * reportees.count() / total, 1) if total else 0.0,
        "motifs": [{"reference": r, "motif": m} for r, m in motifs],
    }


def temps_rotation_moyen(depuis=None, jusqu=None) -> dict:
    depuis, jusqu = _bornes(depuis, jusqu)
    ecarts = []
    for salle in SalleOperatoire.objects.filter(actif=True):
        interventions = list(
            salle.interventions.filter(
                statut=Intervention.Statut.TERMINEE,
                heure_sortie_salle__gte=depuis, heure_entree_salle__isnull=False,
                heure_sortie_salle__isnull=False,
            ).order_by("heure_entree_salle")
        )
        for prec, suiv in zip(interventions, interventions[1:]):
            delta = (suiv.heure_entree_salle
                     - prec.heure_sortie_salle).total_seconds() / 60
            if 0 <= delta <= 24 * 60:
                ecarts.append(delta)
    return {
        "echantillon": len(ecarts),
        "rotation_moyenne_min": round(sum(ecarts) / len(ecarts), 1) if ecarts else None,
    }


def tableau_de_bord(depuis=None, jusqu=None) -> dict:
    depuis, jusqu = _bornes(depuis, jusqu)
    return {
        "periode": {"depuis": depuis, "jusqu": jusqu},
        "occupation_salles": taux_occupation_salles(depuis, jusqu),
        "duree_par_type": duree_moyenne_par_type(depuis, jusqu),
        "duree_par_praticien": duree_moyenne_par_praticien(depuis, jusqu),
        "deprogrammation": taux_deprogrammation(depuis, jusqu),
        "rotation": temps_rotation_moyen(depuis, jusqu),
    }
