"""
Logique métier de la pharmacie : entrées de stock, ajustements, retrait des
périmés et dispensation FEFO (CDC 4.5).
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import (
    Dispensation,
    LigneDispensation,
    LotMedicament,
    Medicament,
    MouvementStock,
)


class ErreurStock(Exception):
    """Erreur métier liée au stock (ex. stock insuffisant)."""


@transaction.atomic
def enregistrer_entree(*, medicament: Medicament, numero_lot: str, quantite: int,
                       date_peremption: date, utilisateur=None, fournisseur: str = "",
                       date_reception: date | None = None) -> LotMedicament:
    """Réceptionne un lot (création ou complément) et journalise l'entrée."""
    if quantite <= 0:
        raise ErreurStock("La quantité reçue doit être strictement positive.")

    lot, cree = LotMedicament.objects.select_for_update().get_or_create(
        medicament=medicament,
        numero_lot=numero_lot,
        defaults={
            "quantite": quantite,
            "quantite_initiale": quantite,
            "date_peremption": date_peremption,
            "date_reception": date_reception or date.today(),
            "fournisseur": fournisseur,
        },
    )
    if cree:
        # Le mouvement d'entrée initial est créé par le signal post_save du lot.
        return lot

    lot.quantite += quantite
    lot.quantite_initiale += quantite
    lot.save(update_fields=["quantite", "quantite_initiale"])
    MouvementStock.objects.create(
        medicament=medicament, lot=lot, type=MouvementStock.Type.ENTREE,
        quantite=quantite, utilisateur=utilisateur,
        motif=f"Complément lot {numero_lot}",
    )
    return lot


@transaction.atomic
def ajuster_lot(*, lot: LotMedicament, nouvelle_quantite: int, utilisateur=None,
                motif: str = "Inventaire") -> MouvementStock:
    """Ajuste la quantité d'un lot et trace l'écart."""
    if nouvelle_quantite < 0:
        raise ErreurStock("La quantité ajustée ne peut pas être négative.")

    lot = LotMedicament.objects.select_for_update().get(pk=lot.pk)
    ecart = nouvelle_quantite - lot.quantite
    if ecart == 0:
        raise ErreurStock("La quantité est inchangée.")

    lot.quantite = nouvelle_quantite
    lot.save(update_fields=["quantite"])

    type_mvt = (MouvementStock.Type.AJUSTEMENT_POSITIF if ecart > 0
                else MouvementStock.Type.AJUSTEMENT_NEGATIF)
    return MouvementStock.objects.create(
        medicament=lot.medicament, lot=lot, type=type_mvt, quantite=abs(ecart),
        utilisateur=utilisateur, motif=motif,
    )


@transaction.atomic
def retirer_perimes(*, medicament: Medicament | None = None, utilisateur=None) -> int:
    """Met à zéro les lots périmés (quantité > 0) et journalise. Renvoie le total retiré."""
    lots = LotMedicament.objects.select_for_update().filter(
        date_peremption__lt=date.today(), quantite__gt=0,
    )
    if medicament is not None:
        lots = lots.filter(medicament=medicament)

    total = 0
    for lot in lots:
        total += lot.quantite
        MouvementStock.objects.create(
            medicament=lot.medicament, lot=lot,
            type=MouvementStock.Type.RETRAIT_PEREMPTION, quantite=lot.quantite,
            utilisateur=utilisateur,
            motif=f"Péremption {lot.date_peremption:%d/%m/%Y} — lot {lot.numero_lot}",
        )
        lot.quantite = 0
        lot.save(update_fields=["quantite"])
    return total


@transaction.atomic
def dispenser_ordonnance(*, ordonnance, pharmacien, quantites: dict[int, int],
                         commentaire: str = "") -> Dispensation:
    """
    Délivre une ordonnance transmise.

    ``quantites`` associe l'id d'une ``LigneOrdonnance`` à la quantité à délivrer.
    L'allocation se fait en FEFO (premier périmé, premier sorti) sur les lots non
    périmés. Lève ``ErreurStock`` si le stock utilisable est insuffisant.
    """
    from apps.consultations.models import LigneOrdonnance, Ordonnance

    if ordonnance.statut not in {Ordonnance.Statut.TRANSMISE,
                                 Ordonnance.Statut.DISPENSEE_PARTIELLE}:
        raise ErreurStock("Seule une ordonnance transmise peut être dispensée.")

    dispensation, _cree = Dispensation.objects.select_for_update().get_or_create(
        ordonnance=ordonnance,
        defaults={"pharmacien": pharmacien},
    )
    if dispensation.statut in {Dispensation.Statut.COMPLETE, Dispensation.Statut.ANNULEE}:
        raise ErreurStock("Cette dispensation est déjà clôturée.")
    dispensation.pharmacien = pharmacien

    lignes = {
        ligne.id: ligne
        for ligne in LigneOrdonnance.objects.filter(ordonnance=ordonnance)
        .select_related("medicament")
    }

    for ligne_id, quantite in quantites.items():
        if quantite <= 0:
            continue
        ligne = lignes.get(int(ligne_id))
        if ligne is None:
            raise ErreurStock(f"Ligne d'ordonnance {ligne_id} introuvable.")

        restant = quantite
        lots = list(
            LotMedicament.objects.select_for_update()
            .filter(medicament=ligne.medicament, quantite__gt=0,
                    date_peremption__gte=date.today())
            .order_by("date_peremption", "date_reception")
        )
        disponible = sum(lot.quantite for lot in lots)
        if disponible < restant:
            raise ErreurStock(
                f"Stock insuffisant pour {ligne.medicament} : "
                f"{disponible} disponible(s), {restant} demandé(s)."
            )

        for lot in lots:
            if restant <= 0:
                break
            pris = min(lot.quantite, restant)
            lot.quantite -= pris
            lot.save(update_fields=["quantite"])
            restant -= pris

            LigneDispensation.objects.create(
                dispensation=dispensation, ligne_ordonnance=ligne,
                medicament=ligne.medicament, lot=lot, quantite_dispensee=pris,
            )
            MouvementStock.objects.create(
                medicament=ligne.medicament, lot=lot,
                type=MouvementStock.Type.SORTIE, quantite=pris, utilisateur=pharmacien,
                motif=f"Dispensation {ordonnance.reference}",
                reference=ordonnance.reference,
            )

    _finaliser_statuts(dispensation, commentaire)
    return dispensation


def _finaliser_statuts(dispensation: Dispensation, commentaire: str) -> None:
    from apps.consultations.models import Ordonnance

    ordonnance = dispensation.ordonnance
    lignes = list(ordonnance.lignes.all())
    total_prescrit = sum(l.quantite_prescrite or 0 for l in lignes)
    total_delivre = sum(l.quantite_dispensee for l in lignes)

    if total_prescrit and total_delivre >= total_prescrit:
        dispensation.statut = Dispensation.Statut.COMPLETE
        ordonnance.statut = Ordonnance.Statut.DISPENSEE
    elif total_delivre > 0:
        dispensation.statut = Dispensation.Statut.PARTIELLE
        ordonnance.statut = Ordonnance.Statut.DISPENSEE_PARTIELLE
    else:
        dispensation.statut = Dispensation.Statut.EN_COURS

    if dispensation.statut == Dispensation.Statut.COMPLETE:
        dispensation.date_delivrance = timezone.now()
    if commentaire:
        dispensation.commentaire = commentaire

    dispensation.save()
    ordonnance.save(update_fields=["statut", "modifie_le"])
