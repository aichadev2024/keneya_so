"""
Logique métier du bloc opératoire (CDC section 5).

Règles clefs implémentées (CDC 5.4) :
- une salle ne porte qu'une intervention par créneau ; double réservation bloquée,
  temps de nettoyage inséré automatiquement dans le calcul de chevauchement ;
- un membre d'équipe ne peut pas être affecté à deux interventions qui se
  chevauchent ;
- une « extrême urgence » peut forcer le report des interventions programmées en
  conflit, avec traçabilité de la décision et de son auteur ;
- passage à « terminée » seulement après validation de la checklist de sortie ;
- toute annulation / déprogrammation exige un motif et est historisée.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    EtapeChecklist,
    Intervention,
    MembreEquipe,
    SalleOperatoire,
)


class ErreurBloc(Exception):
    """Erreur métier du bloc opératoire."""


# --------------------------------------------------------------------------- #
# Détection de conflits
# --------------------------------------------------------------------------- #
def _intervalle(intervention: Intervention, avec_nettoyage=True):
    debut = intervention.date_heure_debut_prevue
    if debut is None:
        return None
    fin = (intervention.fin_creneau_avec_nettoyage() if avec_nettoyage
           else intervention.fin_prevue)
    return debut, fin


def _se_chevauchent(a, b) -> bool:
    return a and b and a[0] < b[1] and b[0] < a[1]


def conflits_salle(intervention: Intervention, salle: SalleOperatoire | None = None,
                   debut=None, duree_min=None) -> list[Intervention]:
    """Interventions actives de la même salle dont le créneau (nettoyage inclus) chevauche."""
    salle = salle or intervention.salle
    debut = debut or intervention.date_heure_debut_prevue
    if salle is None or debut is None:
        return []
    duree = duree_min or intervention.duree_estimee_min
    fin_cible = debut + timedelta(minutes=duree + salle.duree_nettoyage_min)
    cible = (debut, fin_cible)

    conflits = []
    autres = (
        Intervention.objects.filter(salle=salle,
                                    statut__in=Intervention.STATUTS_ACTIFS)
        .exclude(pk=intervention.pk)
        .select_related("patient")
    )
    for autre in autres:
        if _se_chevauchent(cible, _intervalle(autre)):
            conflits.append(autre)
    return conflits


def conflits_equipe(intervention: Intervention, utilisateur, debut=None,
                    duree_min=None) -> list[Intervention]:
    """Interventions actives où ``utilisateur`` est déjà engagé sur un créneau chevauchant."""
    debut = debut or intervention.date_heure_debut_prevue
    if debut is None:
        return []
    duree = duree_min or intervention.duree_estimee_min
    cible = (debut, debut + timedelta(minutes=duree))

    conflits = []
    autres = (
        Intervention.objects.filter(
            statut__in=Intervention.STATUTS_ACTIFS,
        )
        .filter(equipe__utilisateur=utilisateur)
        .exclude(pk=intervention.pk)
        .distinct()
        .select_related("patient")
    )
    for autre in autres:
        if _se_chevauchent(cible, _intervalle(autre, avec_nettoyage=False)):
            conflits.append(autre)
    return conflits


def materiels_indisponibles(intervention: Intervention) -> list[str]:
    """Matériels requis par le type d'acte qui ne sont pas stérilisés / disponibles."""
    manquants = []
    for requis in intervention.type_intervention.materiels_requis.select_related("materiel"):
        materiel = requis.materiel
        if not materiel.disponible_pour_intervention or \
                materiel.quantite_disponible < requis.quantite:
            manquants.append(
                f"{materiel.designation} ({materiel.get_statut_sterilisation_display()},"
                f" {materiel.quantite_disponible} dispo / {requis.quantite} requis)"
            )
    return manquants


def alertes_intervention(intervention: Intervention) -> list[dict]:
    """Alertes non bloquantes affichées sur la fiche (salle, équipe, matériel)."""
    alertes = []
    for autre in conflits_salle(intervention):
        alertes.append({"niveau": "danger",
                        "message": f"Conflit de salle avec {autre.reference} "
                                   f"({autre.date_heure_debut_prevue:%d/%m %H:%M})."})
    for membre in intervention.equipe.select_related("utilisateur"):
        for autre in conflits_equipe(intervention, membre.utilisateur):
            alertes.append({
                "niveau": "warning",
                "message": f"{membre.utilisateur.get_full_name() or membre.utilisateur} "
                           f"est déjà engagé sur {autre.reference}.",
            })
    for m in materiels_indisponibles(intervention):
        alertes.append({"niveau": "warning", "message": f"Matériel non disponible : {m}."})
    return alertes


# --------------------------------------------------------------------------- #
# Planification
# --------------------------------------------------------------------------- #
@transaction.atomic
def planifier(*, intervention: Intervention, salle: SalleOperatoire, debut,
              duree_estimee_min: int, par=None, forcer=False) -> dict:
    """
    Programme l'intervention sur une salle et un créneau.

    Renvoie ``{"intervention": ..., "reports": [...]}``. Lève ``ErreurBloc`` en
    cas de conflit non résolu.
    """
    if intervention.statut in {Intervention.Statut.EN_COURS,
                               Intervention.Statut.TERMINEE}:
        raise ErreurBloc("Une intervention en cours ou terminée ne se replanifie pas.")

    salle = SalleOperatoire.objects.select_for_update().get(pk=salle.pk)
    if not salle.operationnelle:
        raise ErreurBloc(f"La salle {salle} n'est pas opérationnelle "
                         f"({salle.get_statut_display()}).")

    conflits = conflits_salle(intervention, salle=salle, debut=debut,
                              duree_min=duree_estimee_min)
    reports = []
    if conflits:
        if not (forcer
                and intervention.niveau_urgence == Intervention.Urgence.EXTREME_URGENCE):
            details = ", ".join(c.reference for c in conflits)
            raise ErreurBloc(
                f"Conflit de réservation sur {salle} avec : {details}. "
                f"Double réservation bloquée (CDC 5.4)."
            )
        # Extrême urgence : report des interventions programmées en conflit.
        for c in conflits:
            if c.niveau_urgence != Intervention.Urgence.PROGRAMMEE:
                raise ErreurBloc(
                    f"{c.reference} n'est pas « programmée » : report automatique "
                    f"impossible, arbitrage manuel requis."
                )
            annuler(intervention=c, motif=f"Reprogrammée — priorité extrême urgence "
                    f"{intervention.reference}", par=par, reporter=True)
            reports.append(c)

    # Conflits d'équipe (déjà affectée ailleurs sur le créneau)
    for membre in intervention.equipe.select_related("utilisateur"):
        ce = conflits_equipe(intervention, membre.utilisateur, debut=debut,
                             duree_min=duree_estimee_min)
        if ce and not forcer:
            raise ErreurBloc(
                f"{membre.utilisateur.get_full_name() or membre.utilisateur} est déjà "
                f"engagé sur {ce[0].reference} à ce créneau."
            )

    intervention.salle = salle
    intervention.date_heure_debut_prevue = debut
    intervention.duree_estimee_min = duree_estimee_min
    intervention.statut = Intervention.Statut.PLANIFIEE
    intervention.modifie_par = par
    intervention.save()
    _assurer_checklist(intervention)
    return {"intervention": intervention, "reports": reports}


def _assurer_checklist(intervention: Intervention) -> None:
    for temps in EtapeChecklist.ORDRE:
        EtapeChecklist.objects.get_or_create(intervention=intervention, temps=temps)


# --------------------------------------------------------------------------- #
# Équipe
# --------------------------------------------------------------------------- #
@transaction.atomic
def ajouter_membre(*, intervention: Intervention, utilisateur, role: str,
                   par=None, forcer=False) -> MembreEquipe:
    if MembreEquipe.objects.filter(intervention=intervention,
                                   utilisateur=utilisateur).exists():
        raise ErreurBloc("Ce membre est déjà dans l'équipe.")
    conflits = conflits_equipe(intervention, utilisateur)
    if conflits and not forcer:
        raise ErreurBloc(
            f"{utilisateur.get_full_name() or utilisateur} est déjà affecté à "
            f"{conflits[0].reference} sur un créneau qui se chevauche (CDC 5.4)."
        )
    return MembreEquipe.objects.create(
        intervention=intervention, utilisateur=utilisateur, role=role,
        notifie_le=timezone.now(),
    )


# --------------------------------------------------------------------------- #
# Checklist de sécurité
# --------------------------------------------------------------------------- #
@transaction.atomic
def valider_etape(*, intervention: Intervention, temps: str, utilisateur,
                  commentaire: str = "") -> EtapeChecklist:
    _assurer_checklist(intervention)
    index = EtapeChecklist.ORDRE.index(temps)
    if index > 0:
        precedent = EtapeChecklist.ORDRE[index - 1]
        if not intervention.checklist.filter(temps=precedent, valide=True).exists():
            raise ErreurBloc(
                "L'étape précédente de la checklist n'est pas validée "
                "(CDC 5.3.5 — blocage avant de passer à l'étape suivante)."
            )
    etape = intervention.checklist.get(temps=temps)
    etape.valide = True
    etape.valide_par = utilisateur
    etape.valide_le = timezone.now()
    etape.commentaire = commentaire
    etape.save()
    return etape


# --------------------------------------------------------------------------- #
# Déroulé per-opératoire (CDC 5.3.6)
# --------------------------------------------------------------------------- #
@transaction.atomic
def entree_en_salle(*, intervention: Intervention, par=None) -> Intervention:
    if intervention.statut != Intervention.Statut.PLANIFIEE:
        raise ErreurBloc("Seule une intervention planifiée peut démarrer.")
    if not intervention.faisabilite_anesthesique_validee:
        raise ErreurBloc("La faisabilité anesthésique n'est pas validée.")
    if not intervention.checklist.filter(
        temps=EtapeChecklist.Temps.AVANT_INDUCTION, valide=True
    ).exists():
        raise ErreurBloc("La checklist « avant induction » doit être validée.")
    intervention.statut = Intervention.Statut.EN_COURS
    intervention.heure_entree_salle = timezone.now()
    intervention.modifie_par = par
    intervention.save()
    return intervention


@transaction.atomic
def pointer_incision(*, intervention: Intervention, par=None) -> Intervention:
    if intervention.statut != Intervention.Statut.EN_COURS:
        raise ErreurBloc("L'intervention n'est pas en cours.")
    if not intervention.checklist.filter(
        temps=EtapeChecklist.Temps.AVANT_INCISION, valide=True
    ).exists():
        raise ErreurBloc("La checklist « avant incision » doit être validée.")
    intervention.heure_debut_intervention = timezone.now()
    intervention.modifie_par = par
    intervention.save(update_fields=["heure_debut_intervention", "modifie_par",
                                     "modifie_le"])
    return intervention


@transaction.atomic
def terminer(*, intervention: Intervention, incidents: str = "", par=None) -> Intervention:
    if intervention.statut != Intervention.Statut.EN_COURS:
        raise ErreurBloc("L'intervention n'est pas en cours.")
    if not intervention.checklist_sortie_validee:
        raise ErreurBloc(
            "La checklist « avant sortie de salle » doit être validée avant de "
            "clôturer l'intervention (CDC 5.4)."
        )
    now = timezone.now()
    intervention.statut = Intervention.Statut.TERMINEE
    intervention.heure_fin_intervention = intervention.heure_fin_intervention or now
    intervention.heure_sortie_salle = now
    if incidents:
        intervention.incidents_peroperatoires = incidents
    intervention.modifie_par = par
    intervention.save()
    return intervention


@transaction.atomic
def annuler(*, intervention: Intervention, motif: str, par=None, reporter=False):
    if not motif or not motif.strip():
        raise ErreurBloc("Le motif d'annulation / de report est obligatoire (CDC 5.4).")
    if intervention.statut in {Intervention.Statut.TERMINEE,
                               Intervention.Statut.ANNULEE}:
        raise ErreurBloc("Cette intervention ne peut plus être annulée.")
    intervention.statut = (Intervention.Statut.REPORTEE if reporter
                           else Intervention.Statut.ANNULEE)
    intervention.motif_annulation = motif.strip()
    intervention.annule_par = par
    intervention.annule_le = timezone.now()
    if reporter:
        intervention.salle = None
        intervention.date_heure_debut_prevue = None
    intervention.modifie_par = par
    intervention.save()
    return intervention
