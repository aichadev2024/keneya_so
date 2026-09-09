"""
Logique métier de l'hospitalisation : admission, transfert de lit, sortie (CDC 4.4).
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from .models import Hospitalisation, Lit, MouvementLit


class ErreurHospitalisation(Exception):
    """Erreur métier d'hospitalisation (lit indisponible, séjour déjà clôturé…)."""


def _verifier_lit_disponible(lit: Lit) -> None:
    if lit.statut != Lit.Statut.DISPONIBLE:
        raise ErreurHospitalisation(
            f"Le lit {lit} n'est pas disponible ({lit.get_statut_display()})."
        )
    if lit.est_occupe:
        raise ErreurHospitalisation(f"Le lit {lit} est déjà occupé.")


@transaction.atomic
def admettre(*, patient, service, lit, motif, medecin_referent=None, consultation=None,
            diagnostic_admission="", date_admission=None, par=None) -> Hospitalisation:
    """Admet un patient dans un lit disponible."""
    if lit is not None:
        lit = Lit.objects.select_for_update().get(pk=lit.pk)
        _verifier_lit_disponible(lit)
        if lit.chambre.service_id != service.pk:
            raise ErreurHospitalisation("Le lit choisi n'appartient pas à ce service.")

    hospitalisation = Hospitalisation.objects.create(
        patient=patient, service=service, lit=lit, motif=motif,
        medecin_referent=medecin_referent, consultation=consultation,
        diagnostic_admission=diagnostic_admission,
        date_admission=date_admission or timezone.now(),
        cree_par=par, modifie_par=par,
    )
    if lit is not None:
        MouvementLit.objects.create(
            hospitalisation=hospitalisation, lit_precedent=None, lit_nouveau=lit,
            motif="Admission", par=par,
        )
    return hospitalisation


@transaction.atomic
def transferer(*, hospitalisation: Hospitalisation, nouveau_lit: Lit, motif="", par=None):
    """Change le lit (et éventuellement le service) d'un séjour en cours."""
    if not hospitalisation.est_en_cours:
        raise ErreurHospitalisation("Le séjour n'est pas en cours.")

    nouveau_lit = Lit.objects.select_for_update().get(pk=nouveau_lit.pk)
    if nouveau_lit.pk == hospitalisation.lit_id:
        raise ErreurHospitalisation("Le patient est déjà dans ce lit.")
    _verifier_lit_disponible(nouveau_lit)

    ancien = hospitalisation.lit
    hospitalisation.lit = nouveau_lit
    hospitalisation.service = nouveau_lit.chambre.service
    hospitalisation.modifie_par = par
    hospitalisation.save(update_fields=["lit", "service", "modifie_par", "modifie_le"])

    MouvementLit.objects.create(
        hospitalisation=hospitalisation, lit_precedent=ancien, lit_nouveau=nouveau_lit,
        motif=motif or "Transfert", par=par,
    )
    return hospitalisation


@transaction.atomic
def prononcer_sortie(*, hospitalisation: Hospitalisation, mode_sortie, compte_rendu="",
                     consignes_sortie="", date_sortie=None, par=None) -> Hospitalisation:
    """Clôture le séjour ; le lit redevient disponible (occupation déduite)."""
    if not hospitalisation.est_en_cours:
        raise ErreurHospitalisation("Ce séjour est déjà clôturé.")
    if mode_sortie not in Hospitalisation.ModeSortie.values:
        raise ErreurHospitalisation("Mode de sortie invalide.")

    hospitalisation.statut = Hospitalisation.Statut.SORTIE
    hospitalisation.mode_sortie = mode_sortie
    hospitalisation.date_sortie = date_sortie or timezone.now()
    hospitalisation.compte_rendu = compte_rendu
    hospitalisation.consignes_sortie = consignes_sortie
    hospitalisation.modifie_par = par
    hospitalisation.save()
    return hospitalisation
