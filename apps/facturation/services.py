"""
Génération des factures à partir des actes et gestion des paiements (CDC 4.8).

- une facture agrège une ou plusieurs ``LigneFacture`` (une par acte facturé) ;
- la répartition part patient / part assurance découle de la couverture active du
  patient (taux + plafond annuel) ;
- ``enregistrer_paiement`` met à jour le statut de la facture.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction

from apps.assurances.models import PatientAssure

from .models import Facture, LigneFacture, Paiement, Tarif, TypeSource


class ErreurFacturation(Exception):
    """Erreur métier de facturation."""


def _couverture_active(patient, jour: date | None = None):
    jour = jour or date.today()
    for pa in patient.assurances.select_related("contrat__assurance").all():
        if pa.couvert_a(jour):
            return pa
    return None


def source_deja_facturee(type_source: str, source_id: int) -> bool:
    return LigneFacture.objects.filter(
        type_source=type_source, source_id=source_id,
    ).exclude(facture__statut=Facture.Statut.ANNULEE).exists()


@transaction.atomic
def _creer_facture(*, patient, lignes: list[dict], patient_assure=None, par=None,
                   notes: str = "") -> Facture:
    if not lignes:
        raise ErreurFacturation("Aucune ligne à facturer.")
    if patient_assure is None:
        patient_assure = _couverture_active(patient)

    facture = Facture.objects.create(
        patient=patient, patient_assure=patient_assure, notes=notes,
        cree_par=par, modifie_par=par,
    )
    for ligne in lignes:
        LigneFacture.objects.create(facture=facture, **ligne)
    facture.recalculer_totaux()
    return facture


# --------------------------------------------------------------------------- #
# Générateurs par type d'acte
# --------------------------------------------------------------------------- #
def facturer_consultation(consultation, *, par=None, forcer=False) -> Facture | None:
    if not forcer and source_deja_facturee(TypeSource.CONSULTATION, consultation.pk):
        return None
    montant = Tarif.montant_pour("CONSULTATION")
    if montant is None:
        raise ErreurFacturation("Aucun tarif « consultation » défini.")
    return _creer_facture(
        patient=consultation.patient, par=par,
        lignes=[{
            "type_source": TypeSource.CONSULTATION, "source_id": consultation.pk,
            "libelle": f"Consultation {consultation.reference} — {consultation.motif}"[:200],
            "quantite": 1, "prix_unitaire": montant,
        }],
    )


def facturer_hospitalisation(hospitalisation, *, par=None, forcer=False) -> Facture | None:
    if not forcer and source_deja_facturee(TypeSource.HOSPITALISATION, hospitalisation.pk):
        return None
    montant_jour = Tarif.montant_pour("HOSPIT_JOUR")
    if montant_jour is None:
        raise ErreurFacturation("Aucun tarif « hospitalisation (jour) » défini.")
    jours = max(hospitalisation.duree_jours, 1)
    return _creer_facture(
        patient=hospitalisation.patient, par=par,
        lignes=[{
            "type_source": TypeSource.HOSPITALISATION, "source_id": hospitalisation.pk,
            "libelle": f"Séjour {hospitalisation.reference} — {hospitalisation.service.nom}"[:200],
            "quantite": jours, "prix_unitaire": montant_jour,
        }],
    )


def facturer_intervention(intervention, *, par=None, forcer=False) -> Facture | None:
    if not forcer and source_deja_facturee(TypeSource.INTERVENTION, intervention.pk):
        return None
    montant = Tarif.montant_pour("ACTE_BLOC", str(intervention.type_intervention_id))
    if montant is None:
        raise ErreurFacturation(
            "Aucun tarif « acte de bloc » défini (ni spécifique ni générique)."
        )
    return _creer_facture(
        patient=intervention.patient, par=par,
        lignes=[{
            "type_source": TypeSource.INTERVENTION, "source_id": intervention.pk,
            "libelle": f"Intervention {intervention.reference} — "
                       f"{intervention.type_intervention.libelle}"[:200],
            "quantite": 1, "prix_unitaire": montant,
        }],
    )


def facturer_dispensation(dispensation, *, par=None, forcer=False) -> Facture | None:
    if not forcer and source_deja_facturee(TypeSource.DISPENSATION, dispensation.pk):
        return None
    agrege: dict[int, dict] = {}
    for ligne in dispensation.lignes.select_related("medicament"):
        med = ligne.medicament
        entree = agrege.setdefault(med.pk, {
            "libelle": f"Médicament — {med.denomination} {med.dosage}".strip()[:200],
            "prix_unitaire": med.prix_unitaire, "quantite": Decimal("0"),
        })
        entree["quantite"] += ligne.quantite_dispensee
    lignes = [
        {"type_source": TypeSource.DISPENSATION, "source_id": dispensation.pk, **v}
        for v in agrege.values() if v["prix_unitaire"] > 0
    ]
    if not lignes:
        return None
    return _creer_facture(patient=dispensation.patient, par=par, lignes=lignes)


# --------------------------------------------------------------------------- #
# Émission, paiements, annulation
# --------------------------------------------------------------------------- #
@transaction.atomic
def emettre_facture(*, facture: Facture, par=None) -> Facture:
    if facture.statut != Facture.Statut.BROUILLON:
        raise ErreurFacturation("Seule une facture en brouillon peut être émise.")
    if not facture.lignes.exists():
        raise ErreurFacturation("La facture ne comporte aucune ligne.")
    facture.recalculer_totaux(sauvegarder=False)
    facture.statut = Facture.Statut.EMISE
    facture.modifie_par = par
    facture.save()
    return facture


@transaction.atomic
def enregistrer_paiement(*, facture: Facture, montant, mode: str,
                         payeur: str = Paiement.Payeur.PATIENT,
                         est_remboursement: bool = False, reference_transaction: str = "",
                         commentaire: str = "", par=None) -> Paiement:
    montant = Decimal(str(montant))
    if montant <= 0:
        raise ErreurFacturation("Le montant doit être strictement positif.")
    if facture.statut in {Facture.Statut.BROUILLON, Facture.Statut.ANNULEE}:
        raise ErreurFacturation("La facture doit être émise pour recevoir un paiement.")
    if not est_remboursement and montant > facture.reste_a_payer:
        raise ErreurFacturation(
            f"Le paiement ({montant}) dépasse le reste à payer "
            f"({facture.reste_a_payer})."
        )
    paiement = Paiement.objects.create(
        facture=facture, montant=montant, mode=mode, payeur=payeur,
        est_remboursement=est_remboursement,
        reference_transaction=reference_transaction, commentaire=commentaire,
        encaisse_par=par,
    )
    facture.rafraichir_statut()
    return paiement


@transaction.atomic
def annuler_facture(*, facture: Facture, motif: str, par=None) -> Facture:
    if not motif or not motif.strip():
        raise ErreurFacturation("Le motif d'annulation est obligatoire.")
    if facture.paiements.exists():
        raise ErreurFacturation(
            "Impossible d'annuler une facture ayant des paiements : "
            "enregistrez d'abord les remboursements."
        )
    if facture.lignes_bordereau.exists():
        raise ErreurFacturation("Facture rattachée à un bordereau d'assurance.")
    facture.statut = Facture.Statut.ANNULEE
    facture.motif_annulation = motif.strip()
    facture.modifie_par = par
    facture.save(update_fields=["statut", "motif_annulation", "modifie_par", "modifie_le"])
    return facture


def factures_en_retard():
    return (
        Facture.objects.filter(
            statut__in=[Facture.Statut.EMISE, Facture.Statut.PARTIELLE],
            date_echeance__lt=date.today(),
        )
        .select_related("patient")
        .order_by("date_echeance")
    )
