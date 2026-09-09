"""
Module « Hospitalisation » — services, chambres/lits, séjours (CDC 4.4).

- ``Service``          : unité d'hospitalisation (médecine, chirurgie, maternité…).
- ``Chambre`` / ``Lit`` : capacités d'accueil ; l'occupation est déduite des
  séjours en cours (pas de champ dénormalisé à resynchroniser).
- ``Hospitalisation`` : séjour d'un patient (admission → sortie).
- ``MouvementLit``    : historique des changements de lit d'un séjour.
- ``NoteSuivi``       : suivi quotidien (soins infirmiers, évolution).

Référence : docs/Kenya_So_Cahier_des_charges_enrichi.docx, section 4.4.
"""

from __future__ import annotations

from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Service(models.Model):
    """Unité d'hospitalisation de l'établissement."""

    nom = models.CharField(_("nom"), max_length=120, unique=True)
    code = models.CharField(_("code"), max_length=12, blank=True)
    description = models.CharField(_("description"), max_length=255, blank=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="services_diriges",
                                    verbose_name=_("médecin responsable"))
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("service")
        verbose_name_plural = _("services")
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom

    @property
    def lits(self):
        return Lit.objects.filter(chambre__service=self)

    @property
    def nb_lits(self) -> int:
        return self.lits.count()

    @property
    def nb_lits_occupes(self) -> int:
        return (
            Hospitalisation.objects.filter(
                lit__chambre__service=self, statut=Hospitalisation.Statut.EN_COURS
            )
            .values("lit")
            .distinct()
            .count()
        )

    @property
    def taux_occupation(self) -> int:
        total = self.nb_lits
        return round(100 * self.nb_lits_occupes / total) if total else 0


class Chambre(models.Model):
    class Type(models.TextChoices):
        INDIVIDUELLE = "INDIVIDUELLE", _("Individuelle")
        DOUBLE = "DOUBLE", _("Double")
        COMMUNE = "COMMUNE", _("Commune")

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="chambres",
                                verbose_name=_("service"))
    numero = models.CharField(_("numéro"), max_length=20)
    type = models.CharField(_("type"), max_length=12, choices=Type.choices,
                            default=Type.COMMUNE)

    class Meta:
        verbose_name = _("chambre")
        verbose_name_plural = _("chambres")
        ordering = ["service__nom", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["service", "numero"],
                                    name="chambre_unique_par_service"),
        ]

    def __str__(self) -> str:
        return f"{self.service.nom} — {_('chambre')} {self.numero}"


class Lit(models.Model):
    class Statut(models.TextChoices):
        DISPONIBLE = "DISPONIBLE", _("Disponible")
        NETTOYAGE = "NETTOYAGE", _("En nettoyage")
        HORS_SERVICE = "HORS_SERVICE", _("Hors service")

    chambre = models.ForeignKey(Chambre, on_delete=models.CASCADE, related_name="lits",
                                verbose_name=_("chambre"))
    numero = models.CharField(_("numéro / libellé"), max_length=20)
    statut = models.CharField(_("statut"), max_length=12, choices=Statut.choices,
                              default=Statut.DISPONIBLE,
                              help_text=_("Hors occupation : un lit occupé est déduit des séjours en cours."))

    class Meta:
        verbose_name = _("lit")
        verbose_name_plural = _("lits")
        ordering = ["chambre__service__nom", "chambre__numero", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["chambre", "numero"],
                                    name="lit_unique_par_chambre"),
        ]

    def __str__(self) -> str:
        return f"{self.chambre.service.nom} · {self.chambre.numero} · {_('lit')} {self.numero}"

    @property
    def service(self) -> Service:
        return self.chambre.service

    @property
    def hospitalisation_active(self):
        return self.hospitalisations.filter(
            statut=Hospitalisation.Statut.EN_COURS
        ).select_related("patient").first()

    @property
    def est_occupe(self) -> bool:
        return self.hospitalisation_active is not None

    @property
    def est_disponible(self) -> bool:
        return self.statut == self.Statut.DISPONIBLE and not self.est_occupe


class Hospitalisation(TimeStampedModel):
    """Séjour d'un patient, de l'admission à la sortie (CDC 4.4)."""

    class Statut(models.TextChoices):
        EN_COURS = "EN_COURS", _("En cours")
        SORTIE = "SORTIE", _("Terminée")
        ANNULEE = "ANNULEE", _("Annulée")

    class ModeSortie(models.TextChoices):
        DOMICILE = "DOMICILE", _("Retour à domicile")
        TRANSFERT = "TRANSFERT", _("Transfert vers un autre établissement")
        CONTRE_AVIS = "CONTRE_AVIS", _("Sortie contre avis médical")
        DECES = "DECES", _("Décès")

    reference = models.CharField(_("référence"), max_length=20, unique=True, editable=False)
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT,
                                related_name="hospitalisations", verbose_name=_("patient"))
    service = models.ForeignKey(Service, on_delete=models.PROTECT,
                                related_name="hospitalisations", verbose_name=_("service"))
    lit = models.ForeignKey(Lit, on_delete=models.SET_NULL, null=True, blank=True,
                            related_name="hospitalisations", verbose_name=_("lit"))
    consultation = models.ForeignKey("consultations.Consultation", on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="hospitalisations",
                                     verbose_name=_("consultation d'origine"))
    medecin_referent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                         null=True, blank=True,
                                         related_name="hospitalisations_referees",
                                         verbose_name=_("médecin référent"))

    motif = models.CharField(_("motif d'hospitalisation"), max_length=255)
    diagnostic_admission = models.TextField(_("diagnostic à l'admission"), blank=True)
    date_admission = models.DateTimeField(_("date d'admission"), default=timezone.now)

    statut = models.CharField(_("statut"), max_length=10, choices=Statut.choices,
                              default=Statut.EN_COURS)
    date_sortie = models.DateTimeField(_("date de sortie"), null=True, blank=True)
    mode_sortie = models.CharField(_("mode de sortie"), max_length=12,
                                   choices=ModeSortie.choices, blank=True)
    compte_rendu = models.TextField(_("compte-rendu d'hospitalisation"), blank=True)
    consignes_sortie = models.TextField(_("consignes de sortie"), blank=True)

    class Meta:
        verbose_name = _("hospitalisation")
        verbose_name_plural = _("hospitalisations")
        ordering = ["-date_admission"]
        indexes = [
            models.Index(fields=["statut", "-date_admission"]),
            models.Index(fields=["patient", "-date_admission"]),
        ]
        constraints = [
            # Un lit ne peut porter qu'un seul séjour en cours (CDC 4.4).
            models.UniqueConstraint(
                fields=["lit"], condition=models.Q(statut="EN_COURS"),
                name="un_seul_sejour_en_cours_par_lit",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.patient.nom_complet}"

    def save(self, *args, **kwargs):
        if not self.reference:
            annee = date.today().year
            base = f"HOSP-{annee}-"
            dernier = (
                Hospitalisation.objects.filter(reference__startswith=base)
                .aggregate(m=Max("reference")).get("m")
            )
            seq = int(dernier.split("-")[-1]) + 1 if dernier else 1
            self.reference = f"{base}{seq:06d}"
        super().save(*args, **kwargs)

    @property
    def est_en_cours(self) -> bool:
        return self.statut == self.Statut.EN_COURS

    @property
    def duree_jours(self) -> int:
        fin = self.date_sortie or timezone.now()
        return max((fin.date() - self.date_admission.date()).days, 0)


class MouvementLit(models.Model):
    """Trace d'un changement de lit au cours d'un séjour (CDC 7.4 — traçabilité)."""

    hospitalisation = models.ForeignKey(Hospitalisation, on_delete=models.CASCADE,
                                        related_name="mouvements_lit")
    lit_precedent = models.ForeignKey(Lit, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="+")
    lit_nouveau = models.ForeignKey(Lit, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+")
    motif = models.CharField(_("motif"), max_length=255, blank=True)
    date = models.DateTimeField(_("date"), default=timezone.now)
    par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                            blank=True, related_name="+")

    class Meta:
        verbose_name = _("mouvement de lit")
        verbose_name_plural = _("mouvements de lit")
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.hospitalisation.reference} : {self.lit_precedent} → {self.lit_nouveau}"


class NoteSuivi(models.Model):
    """Note de suivi quotidien : soin infirmier ou observation médicale (CDC 4.4)."""

    class Type(models.TextChoices):
        SOIN = "SOIN", _("Soin infirmier")
        OBSERVATION = "OBSERVATION", _("Observation médicale")
        TRAITEMENT = "TRAITEMENT", _("Administration de traitement")
        CONSTANTES = "CONSTANTES", _("Relevé de constantes")
        AUTRE = "AUTRE", _("Autre")

    hospitalisation = models.ForeignKey(Hospitalisation, on_delete=models.CASCADE,
                                        related_name="notes", verbose_name=_("séjour"))
    type = models.CharField(_("type"), max_length=12, choices=Type.choices,
                            default=Type.SOIN)
    description = models.TextField(_("description"))
    temperature_c = models.DecimalField(_("température (°C)"), max_digits=4, decimal_places=1,
                                        null=True, blank=True)
    tension_systolique = models.PositiveSmallIntegerField(_("TA systolique"), null=True,
                                                          blank=True)
    tension_diastolique = models.PositiveSmallIntegerField(_("TA diastolique"), null=True,
                                                           blank=True)
    pouls = models.PositiveSmallIntegerField(_("pouls (bpm)"), null=True, blank=True)
    date_note = models.DateTimeField(_("date"), default=timezone.now)
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                               null=True, blank=True, related_name="+",
                               verbose_name=_("auteur"))

    class Meta:
        verbose_name = _("note de suivi")
        verbose_name_plural = _("notes de suivi")
        ordering = ["-date_note"]

    def __str__(self) -> str:
        return f"{self.get_type_display()} — {self.date_note:%d/%m/%Y %H:%M}"

    @property
    def tension_arterielle(self) -> str:
        if self.tension_systolique and self.tension_diastolique:
            return f"{self.tension_systolique}/{self.tension_diastolique}"
        return "—"
