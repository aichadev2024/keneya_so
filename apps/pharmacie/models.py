"""
Module « Pharmacie » — catalogue, stock et dispensation (CDC 4.3 / 4.5).

- ``Medicament``           : catalogue des médicaments (DCI, forme, seuil d'alerte).
- ``LotMedicament``        : lots physiques en stock, avec date de péremption (FEFO).
- ``MouvementStock``       : journal des entrées/sorties/ajustements de stock.
- ``InteractionMedicamenteuse`` : interactions connues, exploitées pour les
  alertes non bloquantes à la prescription (CDC 4.3).
- ``Dispensation`` / ``LigneDispensation`` : délivrance d'une ordonnance
  transmise par un médecin.

Référence : docs/Kenya_So_Cahier_des_charges_enrichi.docx, sections 4.3 et 4.5.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class FormeGalenique(models.TextChoices):
    COMPRIME = "COMPRIME", _("Comprimé")
    GELULE = "GELULE", _("Gélule")
    SIROP = "SIROP", _("Sirop")
    SUSPENSION = "SUSPENSION", _("Suspension buvable")
    INJECTABLE = "INJECTABLE", _("Injectable")
    PERFUSION = "PERFUSION", _("Solution pour perfusion")
    POMMADE = "POMMADE", _("Pommade / crème")
    COLLYRE = "COLLYRE", _("Collyre")
    SUPPOSITOIRE = "SUPPOSITOIRE", _("Suppositoire")
    AUTRE = "AUTRE", _("Autre")


class Medicament(TimeStampedModel):
    """Fiche catalogue d'un médicament."""

    code = models.CharField(_("code"), max_length=30, blank=True, unique=True, null=True,
                            help_text=_("Code interne ou code-barres, facultatif."))
    denomination = models.CharField(_("dénomination (DCI)"), max_length=200)
    dosage = models.CharField(_("dosage"), max_length=60, blank=True,
                              help_text=_("Ex. : 500 mg, 1 g/10 ml…"))
    forme = models.CharField(_("forme galénique"), max_length=20,
                             choices=FormeGalenique.choices, default=FormeGalenique.COMPRIME)
    unite = models.CharField(_("unité de délivrance"), max_length=30, default="unité",
                             help_text=_("Ex. : comprimé, flacon, ampoule, tube…"))
    seuil_alerte = models.PositiveIntegerField(
        _("seuil d'alerte"), default=10,
        help_text=_("En dessous de ce stock utilisable, le médicament est signalé."),
    )
    prix_unitaire = models.DecimalField(
        _("prix unitaire de vente (FCFA)"), max_digits=10, decimal_places=2,
        default=Decimal("0"),
        help_text=_("Utilisé pour la facturation des dispensations (CDC 4.8)."),
    )
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("médicament")
        verbose_name_plural = _("médicaments")
        ordering = ["denomination", "dosage"]
        indexes = [models.Index(fields=["denomination"])]

    def __str__(self) -> str:
        base = self.denomination
        if self.dosage:
            base = f"{base} {self.dosage}"
        return f"{base} ({self.get_forme_display()})"

    @property
    def quantite_en_stock(self) -> int:
        """Somme de tous les lots (périmés compris)."""
        return self.lots.aggregate(q=Sum("quantite")).get("q") or 0

    @property
    def quantite_utilisable(self) -> int:
        """Somme des lots non périmés — base des alertes et de la dispensation."""
        return (
            self.lots.filter(date_peremption__gte=date.today())
            .aggregate(q=Sum("quantite"))
            .get("q")
            or 0
        )

    @property
    def en_alerte(self) -> bool:
        return self.actif and self.quantite_utilisable <= self.seuil_alerte

    @property
    def a_des_lots_perimes(self) -> bool:
        return self.lots.filter(
            date_peremption__lt=date.today(), quantite__gt=0
        ).exists()


class LotMedicament(models.Model):
    """Lot physique d'un médicament, avec sa date de péremption."""

    medicament = models.ForeignKey(Medicament, on_delete=models.CASCADE,
                                   related_name="lots", verbose_name=_("médicament"))
    numero_lot = models.CharField(_("numéro de lot"), max_length=60)
    quantite = models.PositiveIntegerField(_("quantité restante"))
    quantite_initiale = models.PositiveIntegerField(_("quantité initiale"))
    date_peremption = models.DateField(_("date de péremption"))
    date_reception = models.DateField(_("date de réception"), default=date.today)
    fournisseur = models.CharField(_("fournisseur"), max_length=150, blank=True)

    class Meta:
        verbose_name = _("lot de médicament")
        verbose_name_plural = _("lots de médicaments")
        ordering = ["date_peremption", "date_reception"]  # FEFO : premier périmé, premier sorti
        constraints = [
            models.UniqueConstraint(fields=["medicament", "numero_lot"],
                                    name="lot_unique_par_medicament"),
        ]

    def __str__(self) -> str:
        return f"{self.medicament.denomination} — lot {self.numero_lot}"

    @property
    def est_perime(self) -> bool:
        return self.date_peremption < date.today()


class MouvementStock(models.Model):
    """Trace d'une variation de stock (CDC 4.5 — entrées, sorties, ajustements)."""

    class Type(models.TextChoices):
        ENTREE = "ENTREE", _("Entrée (réception)")
        SORTIE = "SORTIE", _("Sortie (dispensation)")
        AJUSTEMENT_POSITIF = "AJUST_POS", _("Ajustement positif (inventaire)")
        AJUSTEMENT_NEGATIF = "AJUST_NEG", _("Ajustement négatif (inventaire, casse)")
        RETRAIT_PEREMPTION = "PEREMPTION", _("Retrait pour péremption")

    ENTREES = {Type.ENTREE, Type.AJUSTEMENT_POSITIF}

    medicament = models.ForeignKey(Medicament, on_delete=models.CASCADE,
                                   related_name="mouvements", verbose_name=_("médicament"))
    lot = models.ForeignKey(LotMedicament, on_delete=models.SET_NULL, null=True, blank=True,
                            related_name="mouvements", verbose_name=_("lot"))
    type = models.CharField(_("type"), max_length=12, choices=Type.choices)
    quantite = models.PositiveIntegerField(_("quantité"))
    motif = models.CharField(_("motif"), max_length=255, blank=True)
    reference = models.CharField(_("référence"), max_length=60, blank=True,
                                 help_text=_("Ex. : n° de dispensation."))
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="+",
                                    verbose_name=_("opérateur"))
    cree_le = models.DateTimeField(_("date"), default=timezone.now, db_index=True)

    class Meta:
        verbose_name = _("mouvement de stock")
        verbose_name_plural = _("mouvements de stock")
        ordering = ["-cree_le"]

    def __str__(self) -> str:
        signe = "+" if self.type in self.ENTREES else "-"
        return f"{self.get_type_display()} {signe}{self.quantite} — {self.medicament.denomination}"

    @property
    def quantite_signee(self) -> int:
        return self.quantite if self.type in self.ENTREES else -self.quantite


class InteractionMedicamenteuse(models.Model):
    """Interaction connue entre deux médicaments (CDC 4.3 — alerte non bloquante)."""

    class Gravite(models.TextChoices):
        MINEURE = "MINEURE", _("Mineure")
        MODEREE = "MODEREE", _("Modérée")
        MAJEURE = "MAJEURE", _("Majeure")
        CONTRE_INDIQUEE = "CONTRE_INDIQUEE", _("Association contre-indiquée")

    medicament_a = models.ForeignKey(Medicament, on_delete=models.CASCADE,
                                     related_name="interactions_a")
    medicament_b = models.ForeignKey(Medicament, on_delete=models.CASCADE,
                                     related_name="interactions_b")
    gravite = models.CharField(_("gravité"), max_length=16, choices=Gravite.choices,
                               default=Gravite.MODEREE)
    description = models.TextField(_("description / conduite à tenir"), blank=True)

    class Meta:
        verbose_name = _("interaction médicamenteuse")
        verbose_name_plural = _("interactions médicamenteuses")
        constraints = [
            models.UniqueConstraint(fields=["medicament_a", "medicament_b"],
                                    name="interaction_paire_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.medicament_a.denomination} ↔ {self.medicament_b.denomination}"

    def save(self, *args, **kwargs):
        # Normalise l'ordre de la paire pour que (A,B) == (B,A).
        if self.medicament_a_id and self.medicament_b_id and \
                self.medicament_a_id > self.medicament_b_id:
            self.medicament_a_id, self.medicament_b_id = \
                self.medicament_b_id, self.medicament_a_id
        super().save(*args, **kwargs)

    @classmethod
    def pour_paire(cls, m1_id: int, m2_id: int):
        a, b = sorted((m1_id, m2_id))
        return cls.objects.filter(medicament_a_id=a, medicament_b_id=b).first()


class Dispensation(TimeStampedModel):
    """Délivrance d'une ordonnance transmise à la pharmacie (CDC 4.5)."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", _("En attente")
        EN_COURS = "EN_COURS", _("En cours")
        COMPLETE = "COMPLETE", _("Complète")
        PARTIELLE = "PARTIELLE", _("Partielle")
        ANNULEE = "ANNULEE", _("Annulée")

    ordonnance = models.OneToOneField("consultations.Ordonnance", on_delete=models.PROTECT,
                                      related_name="dispensation",
                                      verbose_name=_("ordonnance"))
    pharmacien = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="dispensations",
                                   verbose_name=_("pharmacien"))
    statut = models.CharField(_("statut"), max_length=12, choices=Statut.choices,
                              default=Statut.EN_ATTENTE)
    date_delivrance = models.DateTimeField(_("date de délivrance"), null=True, blank=True)
    commentaire = models.CharField(_("commentaire"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("dispensation")
        verbose_name_plural = _("dispensations")
        ordering = ["-cree_le"]

    def __str__(self) -> str:
        return f"Dispensation {self.ordonnance.reference} — {self.get_statut_display()}"

    @property
    def patient(self):
        return self.ordonnance.patient


class LigneDispensation(models.Model):
    """Quantité effectivement délivrée pour une ligne d'ordonnance, sur un lot donné."""

    dispensation = models.ForeignKey(Dispensation, on_delete=models.CASCADE,
                                     related_name="lignes")
    ligne_ordonnance = models.ForeignKey("consultations.LigneOrdonnance",
                                         on_delete=models.PROTECT,
                                         related_name="lignes_dispensation")
    medicament = models.ForeignKey(Medicament, on_delete=models.PROTECT, related_name="+")
    lot = models.ForeignKey(LotMedicament, on_delete=models.SET_NULL, null=True, blank=True,
                            related_name="+")
    quantite_dispensee = models.PositiveIntegerField(_("quantité délivrée"))
    cree_le = models.DateTimeField(_("date"), auto_now_add=True)

    class Meta:
        verbose_name = _("ligne de dispensation")
        verbose_name_plural = _("lignes de dispensation")
        ordering = ["cree_le"]

    def __str__(self) -> str:
        return f"{self.medicament.denomination} × {self.quantite_dispensee}"
