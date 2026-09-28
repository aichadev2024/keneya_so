"""
Module « Maternité » — suivi prénatal par la sage-femme.

- ``DossierGrossesse``      : une grossesse suivie (date des dernières règles, terme, date
  prévue d'accouchement, antécédents obstétricaux).
- ``ConsultationPrenatale`` : une visite (CPN) ; elle est adossée à une ``Consultation``
  ordinaire, ce qui donne gratuitement constantes, ordonnance, demande d'examens et
  facturation, sans les dupliquer.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TenantOwnedModel, TimeStampedModel

# Durée moyenne d'une grossesse à partir du 1er jour des dernières règles (règle de Naegele).
DUREE_GROSSESSE_JOURS = 280


def _reference_grossesse() -> str:
    annee = date.today().year
    base = f"GRO-{annee}-"
    dernier = (DossierGrossesse.objects.filter(reference__startswith=base)
               .aggregate(m=models.Max("reference")).get("m"))
    sequence = int(dernier.split("-")[-1]) + 1 if dernier else 1
    return f"{base}{sequence:06d}"


class DossierGrossesse(TenantOwnedModel, TimeStampedModel):
    """Suivi d'une grossesse, de la première consultation à l'issue."""

    class Statut(models.TextChoices):
        EN_COURS = "EN_COURS", _("En cours")
        TERMINEE = "TERMINEE", _("Terminée (accouchement)")
        INTERROMPUE = "INTERROMPUE", _("Interrompue (fausse couche, IVG médicale…)")

    reference = models.CharField(_("référence"), max_length=20, editable=False)
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT,
                                related_name="grossesses", verbose_name=_("patiente"))
    date_dernieres_regles = models.DateField(_("date des dernières règles (1er jour)"))
    gestite = models.PositiveSmallIntegerField(
        _("gestité"), default=1,
        help_text=_("Nombre total de grossesses, celle-ci comprise."))
    parite = models.PositiveSmallIntegerField(
        _("parité"), default=0,
        help_text=_("Nombre d'accouchements antérieurs (au-delà de 22 semaines)."))
    antecedents = models.TextField(
        _("antécédents obstétricaux et médicaux"), blank=True,
        help_text=_("Césarienne, hémorragie, pré-éclampsie, diabète, drépanocytose, VIH…"))
    facteurs_risque = models.TextField(_("facteurs de risque identifiés"), blank=True)
    statut = models.CharField(_("statut"), max_length=12, choices=Statut.choices,
                              default=Statut.EN_COURS)
    date_fin = models.DateField(_("date de fin de grossesse"), null=True, blank=True)
    issue = models.TextField(_("issue de la grossesse"), blank=True)
    prochain_rdv = models.DateField(_("prochain rendez-vous"), null=True, blank=True,
                                    editable=False)
    sage_femme = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="grossesses_suivies", verbose_name=_("suivi par"))

    class Meta:
        verbose_name = _("dossier de grossesse")
        verbose_name_plural = _("dossiers de grossesse")
        ordering = ["-date_dernieres_regles"]
        constraints = [
            models.UniqueConstraint(fields=["etablissement", "reference"],
                                    name="grossesse_reference_par_etablissement"),
            # Une patiente n'a qu'une grossesse en cours à la fois.
            models.UniqueConstraint(fields=["patient"], condition=Q(statut="EN_COURS"),
                                    name="une_grossesse_en_cours_par_patiente"),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.patient.nom_complet}"

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = _reference_grossesse()
        super().save(*args, **kwargs)

    # --- Terme ------------------------------------------------------------
    @property
    def date_prevue_accouchement(self) -> date:
        return self.date_dernieres_regles + timedelta(days=DUREE_GROSSESSE_JOURS)

    def jours_amenorrhee(self, au: date | None = None) -> int:
        au = au or (self.date_fin if self.statut != self.Statut.EN_COURS and self.date_fin
                    else timezone.localdate())
        return max((au - self.date_dernieres_regles).days, 0)

    def terme(self, au: date | None = None) -> tuple[int, int]:
        """Terme en (semaines d'aménorrhée, jours)."""
        return divmod(self.jours_amenorrhee(au), 7)

    @property
    def terme_texte(self) -> str:
        sa, jours = self.terme()
        return f"{sa} SA" + (f" + {jours} j" if jours else "")

    @property
    def dpa_depassee(self) -> bool:
        return (self.statut == self.Statut.EN_COURS
                and timezone.localdate() > self.date_prevue_accouchement)

    @property
    def rdv_manque(self) -> bool:
        return (self.statut == self.Statut.EN_COURS and self.prochain_rdv is not None
                and self.prochain_rdv < timezone.localdate())

    @property
    def derniere_visite(self):
        return self.visites.select_related("consultation").order_by("-numero").first()

    def actualiser_prochain_rdv(self) -> None:
        derniere = self.visites.order_by("-numero").first()
        self.prochain_rdv = derniere.prochain_rdv if derniere else None
        self.save(update_fields=["prochain_rdv"])


class ConsultationPrenatale(TenantOwnedModel):
    """Une visite prénatale (CPN). Poids, tension et température sont dans les
    ``Constantes`` de la consultation associée."""

    class BruitsCoeur(models.TextChoices):
        NON_RECHERCHES = "NON_RECHERCHES", _("Non recherchés")
        PRESENTS = "PRESENTS", _("Présents")
        ABSENTS = "ABSENTS", _("Absents")

    class Presentation(models.TextChoices):
        NON_DETERMINEE = "NON_DETERMINEE", _("Non déterminée")
        CEPHALIQUE = "CEPHALIQUE", _("Céphalique")
        SIEGE = "SIEGE", _("Siège")
        TRANSVERSE = "TRANSVERSE", _("Transverse")

    class Bandelette(models.TextChoices):
        NON_FAIT = "NON_FAIT", _("Non fait")
        NEGATIF = "NEGATIF", _("Négatif")
        TRACES = "TRACES", _("Traces")
        PLUS1 = "PLUS1", "+"
        PLUS2 = "PLUS2", "++"
        PLUS3 = "PLUS3", "+++"

    class Depistage(models.TextChoices):
        NON_FAIT = "NON_FAIT", _("Non fait")
        NEGATIF = "NEGATIF", _("Négatif")
        POSITIF = "POSITIF", _("Positif")

    dossier = models.ForeignKey(DossierGrossesse, on_delete=models.CASCADE,
                                related_name="visites", verbose_name=_("dossier de grossesse"))
    consultation = models.OneToOneField("consultations.Consultation", on_delete=models.PROTECT,
                                        related_name="prenatale", verbose_name=_("consultation"))
    numero = models.PositiveSmallIntegerField(_("n° de visite"), editable=False)
    terme_sa = models.PositiveSmallIntegerField(_("terme (SA)"), editable=False)

    hauteur_uterine_cm = models.DecimalField(_("hauteur utérine (cm)"), max_digits=4,
                                             decimal_places=1, null=True, blank=True)
    bruits_coeur_foetal = models.CharField(
        _("bruits du cœur fœtal"), max_length=16, choices=BruitsCoeur.choices,
        default=BruitsCoeur.NON_RECHERCHES)
    frequence_bcf = models.PositiveSmallIntegerField(_("fréquence cardiaque fœtale (bpm)"),
                                                     null=True, blank=True)
    presentation = models.CharField(_("présentation"), max_length=16,
                                    choices=Presentation.choices,
                                    default=Presentation.NON_DETERMINEE)
    oedemes = models.BooleanField(_("œdèmes (visage ou mains)"), default=False)
    albuminurie = models.CharField(_("albuminurie"), max_length=8, choices=Bandelette.choices,
                                   default=Bandelette.NON_FAIT)
    glycosurie = models.CharField(_("glycosurie"), max_length=8, choices=Bandelette.choices,
                                  default=Bandelette.NON_FAIT)
    hemoglobine_g_dl = models.DecimalField(_("hémoglobine (g/dL)"), max_digits=4,
                                           decimal_places=1, null=True, blank=True)
    depistage_vih = models.CharField(_("dépistage VIH"), max_length=8,
                                     choices=Depistage.choices, default=Depistage.NON_FAIT)
    depistage_syphilis = models.CharField(_("dépistage syphilis"), max_length=8,
                                          choices=Depistage.choices, default=Depistage.NON_FAIT)

    tpi_sp_donne = models.BooleanField(_("SP donnée (prévention du paludisme)"), default=False)
    fer_acide_folique_donne = models.BooleanField(_("fer / acide folique donné"), default=False)
    vat_donne = models.BooleanField(_("vaccin antitétanique administré"), default=False)
    moustiquaire_remise = models.BooleanField(_("moustiquaire imprégnée remise"), default=False)

    observations = models.TextField(_("observations et conseils donnés"), blank=True)
    prochain_rdv = models.DateField(_("prochain rendez-vous"), null=True, blank=True)

    class Meta:
        verbose_name = _("consultation prénatale")
        verbose_name_plural = _("consultations prénatales")
        ordering = ["dossier", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["dossier", "numero"], name="visite_numero_par_dossier"),
        ]

    def __str__(self) -> str:
        return f"CPN {self.numero} — {self.dossier}"

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.numero:
                dernier = self.dossier.visites.aggregate(m=models.Max("numero"))["m"] or 0
                self.numero = dernier + 1
            jour = timezone.localtime(self.consultation.date_consultation).date()
            self.terme_sa = self.dossier.terme(jour)[0]
        super().save(*args, **kwargs)
        self.dossier.actualiser_prochain_rdv()

    @property
    def constantes(self):
        return getattr(self.consultation, "constantes", None)
