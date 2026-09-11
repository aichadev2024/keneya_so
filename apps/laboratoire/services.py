"""
Logique métier du laboratoire / imagerie (CDC 4.6).

- ``creer_demande``       : crée la demande et ses lignes depuis une consultation.
- ``saisir_resultat``     : enregistre un résultat (non validé).
- ``valider_demande``     : valide tous les résultats et **notifie le prescripteur**.
- ``annuler_demande``     : annule une demande non validée (motif obligatoire).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.core.models import Notification

from .models import DemandeExamen, LigneExamen, Resultat


class ErreurLaboratoire(Exception):
    """Erreur métier du module laboratoire."""


_PLAGE = re.compile(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*[-–]\s*([0-9]+(?:[.,][0-9]+)?)\s*$")


def interpreter_valeur(valeur: str, valeurs_reference: str) -> str:
    """Déduit NORMAL / BAS / HAUT quand la référence est une plage numérique."""
    m = _PLAGE.match(valeurs_reference or "")
    if not m:
        return ""
    try:
        v = Decimal(str(valeur).replace(",", "."))
        bas = Decimal(m.group(1).replace(",", "."))
        haut = Decimal(m.group(2).replace(",", "."))
    except (InvalidOperation, AttributeError):
        return ""
    if v < bas:
        return Resultat.Interpretation.BAS
    if v > haut:
        return Resultat.Interpretation.HAUT
    return Resultat.Interpretation.NORMAL


@transaction.atomic
def creer_demande(*, patient, prescripteur, categorie: str, types_examens: list,
                  consultation=None, hospitalisation=None, priorite="ROUTINE",
                  renseignements_cliniques: str = "", par=None) -> DemandeExamen:
    if not types_examens:
        raise ErreurLaboratoire("Sélectionnez au moins un examen.")
    demande = DemandeExamen.objects.create(
        patient=patient, prescripteur=prescripteur, categorie=categorie,
        consultation=consultation, hospitalisation=hospitalisation, priorite=priorite,
        renseignements_cliniques=renseignements_cliniques,
        cree_par=par or prescripteur, modifie_par=par or prescripteur,
    )
    for type_examen in types_examens:
        if type_examen.categorie != categorie:
            raise ErreurLaboratoire(
                f"« {type_examen.libelle} » n'est pas de la catégorie demandée."
            )
        LigneExamen.objects.get_or_create(demande=demande, type_examen=type_examen)
    return demande


@transaction.atomic
def saisir_resultat(*, ligne: LigneExamen, par, valeur: str = "", interpretation: str = "",
                    compte_rendu: str = "", conclusion: str = "", fichier=None,
                    commentaire: str = "") -> Resultat:
    demande = ligne.demande
    if demande.statut in {DemandeExamen.Statut.VALIDEE, DemandeExamen.Statut.ANNULEE}:
        raise ErreurLaboratoire("La demande est clôturée : saisie impossible.")

    resultat, _cree = Resultat.objects.get_or_create(ligne=ligne)
    if resultat.valide:
        raise ErreurLaboratoire("Ce résultat est déjà validé.")

    resultat.valeur = valeur
    resultat.compte_rendu = compte_rendu
    resultat.conclusion = conclusion
    resultat.commentaire = commentaire
    if fichier is not None:
        resultat.fichier = fichier
    resultat.interpretation = (
        interpretation
        or interpreter_valeur(valeur, ligne.valeurs_reference)
    )
    resultat.saisi_par = par
    resultat.saisi_le = timezone.now()
    resultat.save()

    if demande.statut == DemandeExamen.Statut.DEMANDEE:
        demande.statut = DemandeExamen.Statut.EN_COURS
    if demande.tous_resultats_saisis:
        demande.statut = DemandeExamen.Statut.RESULTATS_DISPONIBLES
    demande.modifie_par = par
    demande.save(update_fields=["statut", "modifie_par", "modifie_le"])
    return resultat


@transaction.atomic
def valider_demande(*, demande: DemandeExamen, par) -> DemandeExamen:
    if not demande.tous_resultats_saisis:
        raise ErreurLaboratoire(
            "Tous les résultats doivent être saisis avant validation."
        )
    if demande.statut == DemandeExamen.Statut.VALIDEE:
        return demande
    now = timezone.now()
    for ligne in demande.lignes.select_related("resultat"):
        resultat = ligne.resultat
        if not resultat.valide:
            resultat.valide = True
            resultat.valide_par = par
            resultat.valide_le = now
            resultat.save(update_fields=["valide", "valide_par", "valide_le"])
    demande.statut = DemandeExamen.Statut.VALIDEE
    demande.modifie_par = par
    demande.save(update_fields=["statut", "modifie_par", "modifie_le"])

    Notification.notifier(
        destinataire=demande.prescripteur,
        titre="Résultats d'examen disponibles",
        message=f"{demande.reference} — {demande.patient.nom_complet} "
                f"({demande.get_categorie_display()})",
        url=f"/fr/laboratoire/{demande.pk}/",
    )
    return demande


@transaction.atomic
def annuler_demande(*, demande: DemandeExamen, motif: str, par=None) -> DemandeExamen:
    if not motif or not motif.strip():
        raise ErreurLaboratoire("Le motif d'annulation est obligatoire.")
    if demande.statut == DemandeExamen.Statut.VALIDEE:
        raise ErreurLaboratoire("Une demande validée ne peut pas être annulée.")
    demande.statut = DemandeExamen.Statut.ANNULEE
    demande.motif_annulation = motif.strip()
    demande.modifie_par = par
    demande.save(update_fields=["statut", "motif_annulation", "modifie_par", "modifie_le"])
    return demande
