"""
Module « Assurances » — compagnies partenaires, contrats, adhésions, bordereaux
(CDC 4.9).

- ``Assurance``        : organisme d'assurance / mutuelle / prise en charge.
- ``ContratAssurance`` : offre d'un organisme (taux de prise en charge, plafond).
- ``PatientAssure``    : adhésion d'un patient à un contrat (surcharges possibles).
- ``BordereauAssurance`` / ``LigneBordereau`` : relevé des parts assurance sur
  une période, destiné à l'organisme.

Référence : docs/Kenya_So_Cahier_des_charges_enrichi.docx, section 4.9.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Max, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Assurance(models.Model):
    class Type(models.TextChoices):
        PRIVEE = "PRIVEE", _("Compagnie privée")
        MUTUELLE = "MUTUELLE", _("Mutuelle")
        ETAT = "ETAT", _("Prise en charge de l'État")
        ONG = "ONG", _("ONG / organisme humanitaire")
        AUTRE = "AUTRE", _("Autre")

    nom = models.CharField(_("nom"), max_length=150, unique=True)
    code = models.CharField(_("code"), max_length=20, blank=True)
    type = models.CharField(_("type"), max_length=10, choices=Type.choices,
                            default=Type.PRIVEE)
    adresse = models.CharField(_("adresse"), max_length=255, blank=True)
    contact_nom = models.CharField(_("interlocuteur"), max_length=150, blank=True)
    contact_telephone = models.CharField(_("téléphone"), max_length=40, blank=True)
    contact_email = models.EmailField(_("courriel"), blank=True)
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("assurance")
        verbose_name_plural = _("assurances")
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom


class ContratAssurance(models.Model):
    """Offre d'un organisme : taux de prise en charge et plafond annuel."""

    assurance = models.ForeignKey(Assurance, on_delete=models.CASCADE,
                                  related_name="contrats", verbose_name=_("assurance"))
    libelle = models.CharField(_("libellé du contrat"), max_length=150)
    taux_prise_en_charge = models.DecimalField(
        _("taux de prise en charge (%)"), max_digits=5, decimal_places=2,
        default=Decimal("80.00"),
        help_text=_("Part remboursée par l'assurance, de 0 à 100."),
    )
    plafond_annuel = models.DecimalField(
        _("plafond annuel (FCFA)"), max_digits=12, decimal_places=2, null=True,
        blank=True, help_text=_("Laisser vide pour un contrat sans plafond."),
    )
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("contrat d'assurance")
        verbose_name_plural = _("contrats d'assurance")
        ordering = ["assurance__nom", "libelle"]
        constraints = [
            models.UniqueConstraint(fields=["assurance", "libelle"],
                                    name="contrat_unique_par_assurance"),
        ]

    def __str__(self) -> str:
        return f"{self.assurance.nom} — {self.libelle} ({self.taux_prise_en_charge} %)"


class PatientAssure(models.Model):
    """Adhésion d'un patient à un contrat (CDC 4.9)."""

    patient = models.ForeignKey("patients.Patient", on_delete=models.CASCADE,
                                related_name="assurances", verbose_name=_("patient"))
    contrat = models.ForeignKey(ContratAssurance, on_delete=models.PROTECT,
                                related_name="adhesions", verbose_name=_("contrat"))
    numero_adherent = models.CharField(_("numéro d'adhérent"), max_length=60, blank=True)
    taux_prise_en_charge = models.DecimalField(
        _("taux spécifique (%)"), max_digits=5, decimal_places=2, null=True, blank=True,
        help_text=_("Surcharge le taux du contrat pour ce patient."),
    )
    plafond_annuel = models.DecimalField(
        _("plafond spécifique (FCFA)"), max_digits=12, decimal_places=2, null=True,
        blank=True,
    )
    date_debut = models.DateField(_("date de début"), default=date.today)
    date_fin = models.DateField(_("date de fin"), null=True, blank=True)
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("patient assuré")
        verbose_name_plural = _("patients assurés")
        ordering = ["-date_debut"]

    def __str__(self) -> str:
        return f"{self.patient.nom_complet} — {self.contrat}"

    @property
    def assurance(self) -> Assurance:
        return self.contrat.assurance

    @property
    def taux_effectif(self) -> Decimal:
        taux = (self.taux_prise_en_charge
                if self.taux_prise_en_charge is not None
                else self.contrat.taux_prise_en_charge)
        return max(Decimal("0"), min(Decimal("100"), taux))

    @property
    def plafond_effectif(self):
        if self.plafond_annuel is not None:
            return self.plafond_annuel
        return self.contrat.plafond_annuel

    def couvert_a(self, jour: date | None = None) -> bool:
        jour = jour or date.today()
        if not self.actif or jour < self.date_debut:
            return False
        return self.date_fin is None or jour <= self.date_fin

    def consommation_annee(self, annee: int | None = None) -> Decimal:
        """Somme des parts assurance déjà facturées au patient pour l'année."""
        annee = annee or date.today().year
        total = (
            self.patient.factures.filter(
                patient_assure=self, date_emission__year=annee,
            )
            .exclude(statut="ANNULEE")
            .aggregate(s=Sum("part_assurance"))
            .get("s")
        )
        return total or Decimal("0")

    def plafond_restant(self, annee: int | None = None):
        plafond = self.plafond_effectif
        if plafond is None:
            return None
        return max(Decimal("0"), plafond - self.consommation_annee(annee))


class BordereauAssurance(models.Model):
    """Relevé des parts assurance sur une période, destiné à l'organisme (CDC 4.9)."""

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", _("Brouillon")
        ENVOYE = "ENVOYE", _("Envoyé")
        SOLDE = "SOLDE", _("Soldé")

    reference = models.CharField(_("référence"), max_length=24, unique=True,
                                 editable=False)
    assurance = models.ForeignKey(Assurance, on_delete=models.PROTECT,
                                  related_name="bordereaux", verbose_name=_("assurance"))
    periode_debut = models.DateField(_("début de période"))
    periode_fin = models.DateField(_("fin de période"))
    date_generation = models.DateTimeField(_("généré le"), default=timezone.now)
    statut = models.CharField(_("statut"), max_length=10, choices=Statut.choices,
                              default=Statut.BROUILLON)
    montant_total = models.DecimalField(_("montant total"), max_digits=14,
                                        decimal_places=2, default=0)
    cree_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name="+")

    class Meta:
        verbose_name = _("bordereau d'assurance")
        verbose_name_plural = _("bordereaux d'assurance")
        ordering = ["-date_generation"]

    def __str__(self) -> str:
        return f"{self.reference} — {self.assurance.nom}"

    def save(self, *args, **kwargs):
        if not self.reference:
            annee = date.today().year
            base = f"BORD-{annee}-"
            dernier = (BordereauAssurance.objects
                       .filter(reference__startswith=base)
                       .aggregate(m=Max("reference")).get("m"))
            seq = int(dernier.split("-")[-1]) + 1 if dernier else 1
            self.reference = f"{base}{seq:05d}"
        super().save(*args, **kwargs)

    def recalculer_total(self):
        self.montant_total = (self.lignes.aggregate(s=Sum("montant_assurance"))
                              .get("s") or Decimal("0"))
        self.save(update_fields=["montant_total"])


class LigneBordereau(models.Model):
    bordereau = models.ForeignKey(BordereauAssurance, on_delete=models.CASCADE,
                                  related_name="lignes")
    facture = models.ForeignKey("facturation.Facture", on_delete=models.PROTECT,
                                related_name="lignes_bordereau")
    montant_assurance = models.DecimalField(_("part assurance"), max_digits=12,
                                            decimal_places=2)

    class Meta:
        verbose_name = _("ligne de bordereau")
        verbose_name_plural = _("lignes de bordereau")
        constraints = [
            models.UniqueConstraint(fields=["bordereau", "facture"],
                                    name="ligne_bordereau_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.facture.reference} — {self.montant_assurance}"
