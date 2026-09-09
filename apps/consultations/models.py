"""
Module « Consultations » — consultation, constantes, ordonnances (CDC 4.2 / 4.3).

- ``Consultation``     : acte de consultation (motif, examen, diagnostic, CAT).
- ``Constantes``       : constantes vitales relevées lors de la consultation.
- ``Ordonnance`` / ``LigneOrdonnance`` : prescription rattachée à la consultation,
  transmise à la pharmacie pour dispensation (CDC 4.5).

Référence : docs/Kenya_So_Cahier_des_charges_enrichi.docx, sections 4.2 et 4.3.
"""

from __future__ import annotations

from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


def _reference_incrementee(prefixe: str, modele, champ: str = "reference") -> str:
    annee = date.today().year
    base = f"{prefixe}-{annee}-"
    dernier = (
        modele.objects.filter(**{f"{champ}__startswith": base})
        .aggregate(m=Max(champ))
        .get("m")
    )
    sequence = int(dernier.split("-")[-1]) + 1 if dernier else 1
    return f"{base}{sequence:06d}"


class Consultation(TimeStampedModel):
    """Un acte de consultation médicale pour un patient (CDC 4.2)."""

    class Statut(models.TextChoices):
        EN_COURS = "EN_COURS", _("En cours")
        CLOTUREE = "CLOTUREE", _("Clôturée")
        ANNULEE = "ANNULEE", _("Annulée")

    reference = models.CharField(_("référence"), max_length=20, unique=True, editable=False)
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT,
                                related_name="consultations", verbose_name=_("patient"))
    praticien = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name="consultations_effectuees",
                                  verbose_name=_("praticien"))
    date_consultation = models.DateTimeField(_("date de la consultation"), default=timezone.now)

    motif = models.CharField(_("motif de consultation"), max_length=255)
    histoire_maladie = models.TextField(_("histoire de la maladie / symptômes"), blank=True)
    examen_clinique = models.TextField(_("examen clinique"), blank=True)
    diagnostic = models.TextField(_("diagnostic"), blank=True)
    conduite_a_tenir = models.TextField(_("conduite à tenir / traitement"), blank=True)

    statut = models.CharField(_("statut"), max_length=10, choices=Statut.choices,
                              default=Statut.EN_COURS)

    class Meta:
        verbose_name = _("consultation")
        verbose_name_plural = _("consultations")
        ordering = ["-date_consultation"]
        indexes = [models.Index(fields=["patient", "-date_consultation"])]

    def __str__(self) -> str:
        return f"{self.reference} — {self.patient.nom_complet}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _reference_incrementee("CONS", Consultation)
        super().save(*args, **kwargs)


class Constantes(models.Model):
    """Constantes vitales relevées pour une consultation (CDC 4.2)."""

    consultation = models.OneToOneField(Consultation, on_delete=models.CASCADE,
                                        related_name="constantes",
                                        verbose_name=_("consultation"))
    poids_kg = models.DecimalField(_("poids (kg)"), max_digits=5, decimal_places=2,
                                   null=True, blank=True)
    taille_cm = models.DecimalField(_("taille (cm)"), max_digits=5, decimal_places=1,
                                    null=True, blank=True)
    temperature_c = models.DecimalField(_("température (°C)"), max_digits=4, decimal_places=1,
                                        null=True, blank=True)
    tension_systolique = models.PositiveSmallIntegerField(_("TA systolique (mmHg)"),
                                                          null=True, blank=True)
    tension_diastolique = models.PositiveSmallIntegerField(_("TA diastolique (mmHg)"),
                                                           null=True, blank=True)
    frequence_cardiaque = models.PositiveSmallIntegerField(_("fréquence cardiaque (bpm)"),
                                                           null=True, blank=True)
    frequence_respiratoire = models.PositiveSmallIntegerField(
        _("fréquence respiratoire (cycles/min)"), null=True, blank=True)
    saturation_o2 = models.PositiveSmallIntegerField(_("SpO₂ (%)"), null=True, blank=True)
    glycemie_g_l = models.DecimalField(_("glycémie (g/L)"), max_digits=4, decimal_places=2,
                                       null=True, blank=True)
    releve_le = models.DateTimeField(_("relevé le"), default=timezone.now)
    releve_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="+",
                                   verbose_name=_("relevé par"))

    class Meta:
        verbose_name = _("constantes")
        verbose_name_plural = _("constantes")

    def __str__(self) -> str:
        return _("Constantes de %(ref)s") % {"ref": self.consultation.reference}

    @property
    def imc(self):
        """Indice de masse corporelle, arrondi à une décimale."""
        if not self.poids_kg or not self.taille_cm:
            return None
        taille_m = float(self.taille_cm) / 100
        if taille_m <= 0:
            return None
        return round(float(self.poids_kg) / (taille_m * taille_m), 1)

    @property
    def tension_arterielle(self) -> str:
        if self.tension_systolique and self.tension_diastolique:
            return f"{self.tension_systolique}/{self.tension_diastolique}"
        return "—"


class Ordonnance(TimeStampedModel):
    """Prescription médicamenteuse issue d'une consultation (CDC 4.3)."""

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", _("Brouillon")
        TRANSMISE = "TRANSMISE", _("Transmise à la pharmacie")
        DISPENSEE_PARTIELLE = "DISP_PARTIELLE", _("Dispensée partiellement")
        DISPENSEE = "DISPENSEE", _("Dispensée")
        ANNULEE = "ANNULEE", _("Annulée")

    reference = models.CharField(_("référence"), max_length=20, unique=True, editable=False)
    consultation = models.OneToOneField(Consultation, on_delete=models.CASCADE,
                                        related_name="ordonnance",
                                        verbose_name=_("consultation"))
    prescripteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="ordonnances",
                                     verbose_name=_("prescripteur"))
    date_prescription = models.DateTimeField(_("date de prescription"), default=timezone.now)
    statut = models.CharField(_("statut"), max_length=16, choices=Statut.choices,
                              default=Statut.BROUILLON)
    date_transmission = models.DateTimeField(_("date de transmission"), null=True, blank=True)
    notes = models.TextField(_("notes au pharmacien"), blank=True)

    class Meta:
        verbose_name = _("ordonnance")
        verbose_name_plural = _("ordonnances")
        ordering = ["-date_prescription"]

    def __str__(self) -> str:
        return f"{self.reference} — {self.patient.nom_complet}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _reference_incrementee("ORD", Ordonnance)
        super().save(*args, **kwargs)

    @property
    def patient(self):
        return self.consultation.patient

    @property
    def modifiable(self) -> bool:
        return self.statut == self.Statut.BROUILLON

    def transmettre(self):
        """Transmet l'ordonnance à la pharmacie (CDC 4.3). Idempotent."""
        if self.statut != self.Statut.BROUILLON:
            return
        self.statut = self.Statut.TRANSMISE
        self.date_transmission = timezone.now()
        self.save(update_fields=["statut", "date_transmission", "modifie_le"])


class LigneOrdonnance(models.Model):
    """Un médicament prescrit sur une ordonnance."""

    ordonnance = models.ForeignKey(Ordonnance, on_delete=models.CASCADE,
                                   related_name="lignes", verbose_name=_("ordonnance"))
    medicament = models.ForeignKey("pharmacie.Medicament", on_delete=models.PROTECT,
                                   related_name="lignes_ordonnance",
                                   verbose_name=_("médicament"))
    medicament_libelle = models.CharField(_("libellé prescrit"), max_length=255, blank=True,
                                          help_text=_("Copie du libellé au moment de la prescription."))
    posologie = models.CharField(_("posologie"), max_length=255,
                                 help_text=_("Ex. : 1 comprimé matin et soir."))
    duree_jours = models.PositiveSmallIntegerField(_("durée (jours)"), null=True, blank=True)
    quantite_prescrite = models.PositiveIntegerField(
        _("quantité à délivrer"), null=True, blank=True,
        help_text=_("Nombre total d'unités à dispenser."),
    )
    instructions = models.CharField(_("instructions complémentaires"), max_length=255,
                                    blank=True)

    class Meta:
        verbose_name = _("ligne d'ordonnance")
        verbose_name_plural = _("lignes d'ordonnance")
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.medicament_libelle or self.medicament} — {self.posologie}"

    def save(self, *args, **kwargs):
        if not self.medicament_libelle and self.medicament_id:
            self.medicament_libelle = str(self.medicament)
        super().save(*args, **kwargs)

    @property
    def quantite_dispensee(self) -> int:
        return (
            self.lignes_dispensation.aggregate(
                q=models.Sum("quantite_dispensee")
            ).get("q")
            or 0
        )

    @property
    def reliquat(self):
        if self.quantite_prescrite is None:
            return None
        return max(self.quantite_prescrite - self.quantite_dispensee, 0)
