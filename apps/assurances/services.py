"""Génération des bordereaux de facturation destinés aux assureurs (CDC 4.9)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from .models import BordereauAssurance, LigneBordereau


class ErreurBordereau(Exception):
    pass


@transaction.atomic
def generer_bordereau(*, assurance, periode_debut: date, periode_fin: date, par=None
                      ) -> BordereauAssurance:
    if periode_fin < periode_debut:
        raise ErreurBordereau("La fin de période précède le début.")

    from apps.facturation.models import Facture

    factures = (
        Facture.objects.filter(
            patient_assure__contrat__assurance=assurance,
            date_emission__range=(periode_debut, periode_fin),
            part_assurance__gt=0,
        )
        .exclude(statut=Facture.Statut.ANNULEE)
        .exclude(lignes_bordereau__isnull=False)  # pas déjà sur un bordereau
    )
    if not factures.exists():
        raise ErreurBordereau(
            "Aucune facture à porter au bordereau pour cette assurance et cette période."
        )

    bordereau = BordereauAssurance.objects.create(
        assurance=assurance, periode_debut=periode_debut, periode_fin=periode_fin,
        cree_par=par,
    )
    total = Decimal("0")
    for facture in factures:
        LigneBordereau.objects.create(bordereau=bordereau, facture=facture,
                                      montant_assurance=facture.part_assurance)
        total += facture.part_assurance
    bordereau.montant_total = total
    bordereau.save(update_fields=["montant_total"])
    return bordereau
