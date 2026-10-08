"""Soins infirmiers et pansements, en séjour hospitalier ou en ambulatoire."""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.consultations.models import _reference_incrementee
from apps.core.models import TenantOwnedModel, TimeStampedModel


class Soin(TenantOwnedModel, TimeStampedModel):
    """Un soin dispensé à un patient (injection, pansement, perfusion…).

    Il peut être rattaché à un séjour (patient hospitalisé) ou à une intervention
    (pansement post-opératoire) ; sans rattachement, c'est un soin ambulatoire.
    """

    class Type(models.TextChoices):
        INJECTION = "INJECTION", _("Injection")
        PANSEMENT = "PANSEMENT", _("Pansement")
        PANSEMENT_POSTOP = "PANSEMENT_POSTOP", _("Pansement post-opératoire")
        PERFUSION = "PERFUSION", _("Perfusion")
        SUTURE = "SUTURE", _("Suture / retrait de fils")
        AUTRE = "AUTRE", _("Autre soin")

    reference = models.CharField(_("référence"), max_length=20, editable=False)
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT,
                                related_name="soins", verbose_name=_("patient"))
    type_soin = models.CharField(_("type de soin"), max_length=20, choices=Type.choices)
    description = models.TextField(
        _("soin réalisé"),
        help_text=_("Produit, dose, voie d'administration, site, état de la plaie…"))
    observations = models.TextField(_("observations"), blank=True)
    date_soin = models.DateTimeField(_("date du soin"), default=timezone.now)
    soignant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                 null=True, blank=True, related_name="soins_realises",
                                 verbose_name=_("soignant"))
    hospitalisation = models.ForeignKey(
        "hospitalisation.Hospitalisation", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="soins", verbose_name=_("séjour"))
    intervention = models.ForeignKey(
        "bloc_operatoire.Intervention", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="soins", verbose_name=_("intervention"))

    class Meta:
        verbose_name = _("soin")
        verbose_name_plural = _("soins")
        ordering = ["-date_soin"]
        indexes = [models.Index(fields=["patient", "-date_soin"])]
        constraints = [models.UniqueConstraint(fields=["etablissement", "reference"],
                                               name="soin_reference_par_etablissement")]

    def __str__(self) -> str:
        return f"{self.reference} — {self.get_type_soin_display()}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _reference_incrementee("SOIN", Soin)
        super().save(*args, **kwargs)
