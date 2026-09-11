"""
Module « Analyses biologiques et imagerie » (CDC 4.6).

- ``TypeExamen``    : référentiel des analyses / examens (unité, valeurs de réf.).
- ``DemandeExamen`` : demande émise depuis une consultation (ou un séjour).
- ``LigneExamen``   : un examen demandé au sein d'une demande.
- ``Resultat``      : résultat saisi puis validé par le laborantin / radiologue,
  avec archivage texte et pièce jointe (image / PDF) pour l'imagerie.

Sans interfaçage avec les automates (CDC 3.1) : saisie manuelle des résultats.
Référence : docs/Kenya_So_Cahier_des_charges_enrichi.docx, section 4.6.
"""

from __future__ import annotations

from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Categorie(models.TextChoices):
    BIOLOGIE = "BIOLOGIE", _("Analyse biologique")
    IMAGERIE = "IMAGERIE", _("Imagerie médicale")


class TypeExamen(models.Model):
    code = models.CharField(_("code"), max_length=30, unique=True)
    libelle = models.CharField(_("libellé"), max_length=150)
    categorie = models.CharField(_("catégorie"), max_length=10,
                                 choices=Categorie.choices)
    unite = models.CharField(_("unité"), max_length=30, blank=True,
                             help_text=_("Ex. : g/L, /mm³ (biologie)."))
    valeurs_reference = models.CharField(_("valeurs de référence"), max_length=120,
                                         blank=True,
                                         help_text=_("Ex. : 3.5 - 5.0"))
    delai_rendu_heures = models.PositiveSmallIntegerField(_("délai de rendu (heures)"),
                                                          default=24)
    actif = models.BooleanField(_("actif"), default=True)

    class Meta:
        verbose_name = _("type d'examen")
        verbose_name_plural = _("types d'examen")
        ordering = ["categorie", "libelle"]

    def __str__(self) -> str:
        return f"{self.libelle} ({self.get_categorie_display()})"


class DemandeExamen(TimeStampedModel):
    class Priorite(models.TextChoices):
        ROUTINE = "ROUTINE", _("Routine")
        URGENT = "URGENT", _("Urgent")

    class Statut(models.TextChoices):
        DEMANDEE = "DEMANDEE", _("Demandée")
        EN_COURS = "EN_COURS", _("En cours")
        RESULTATS_DISPONIBLES = "RESULTATS", _("Résultats disponibles")
        VALIDEE = "VALIDEE", _("Validée")
        ANNULEE = "ANNULEE", _("Annulée")

    reference = models.CharField(_("référence"), max_length=20, unique=True,
                                 editable=False)
    patient = models.ForeignKey("patients.Patient", on_delete=models.PROTECT,
                                related_name="demandes_examen", verbose_name=_("patient"))
    categorie = models.CharField(_("catégorie"), max_length=10,
                                 choices=Categorie.choices)
    consultation = models.ForeignKey("consultations.Consultation",
                                     on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="demandes_examen")
    hospitalisation = models.ForeignKey("hospitalisation.Hospitalisation",
                                        on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name="demandes_examen")
    prescripteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     related_name="demandes_examen_prescrites",
                                     verbose_name=_("prescripteur"))
    priorite = models.CharField(_("priorité"), max_length=8, choices=Priorite.choices,
                                default=Priorite.ROUTINE)
    renseignements_cliniques = models.TextField(_("renseignements cliniques"), blank=True)
    date_demande = models.DateTimeField(_("date de la demande"), default=timezone.now)
    date_prelevement = models.DateTimeField(_("date de prélèvement"), null=True,
                                            blank=True)
    statut = models.CharField(_("statut"), max_length=10, choices=Statut.choices,
                              default=Statut.DEMANDEE)
    motif_annulation = models.CharField(_("motif d'annulation"), max_length=255,
                                        blank=True)

    class Meta:
        verbose_name = _("demande d'examen")
        verbose_name_plural = _("demandes d'examen")
        ordering = ["-date_demande"]
        indexes = [
            models.Index(fields=["categorie", "statut", "-date_demande"]),
            models.Index(fields=["patient", "-date_demande"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} — {self.patient.nom_complet}"

    def save(self, *args, **kwargs):
        if not self.reference:
            annee = date.today().year
            base = f"EXAM-{annee}-"
            dernier = (DemandeExamen.objects.filter(reference__startswith=base)
                       .aggregate(m=Max("reference")).get("m"))
            seq = int(dernier.split("-")[-1]) + 1 if dernier else 1
            self.reference = f"{base}{seq:06d}"
        super().save(*args, **kwargs)

    @property
    def tous_resultats_saisis(self) -> bool:
        lignes = list(self.lignes.all())
        return bool(lignes) and all(hasattr(ligne, "resultat") for ligne in lignes)

    @property
    def tous_resultats_valides(self) -> bool:
        lignes = list(self.lignes.all())
        return bool(lignes) and all(
            hasattr(ligne, "resultat") and ligne.resultat.valide for ligne in lignes
        )


class LigneExamen(models.Model):
    demande = models.ForeignKey(DemandeExamen, on_delete=models.CASCADE,
                                related_name="lignes", verbose_name=_("demande"))
    type_examen = models.ForeignKey(TypeExamen, on_delete=models.PROTECT,
                                    related_name="lignes", verbose_name=_("examen"))
    # Instantané des références au moment de la demande.
    unite = models.CharField(_("unité"), max_length=30, blank=True)
    valeurs_reference = models.CharField(_("valeurs de référence"), max_length=120,
                                         blank=True)

    class Meta:
        verbose_name = _("ligne d'examen")
        verbose_name_plural = _("lignes d'examen")
        constraints = [
            models.UniqueConstraint(fields=["demande", "type_examen"],
                                    name="ligne_examen_unique"),
        ]

    def __str__(self) -> str:
        return self.type_examen.libelle

    def save(self, *args, **kwargs):
        if not self.unite and self.type_examen_id:
            self.unite = self.type_examen.unite
            self.valeurs_reference = self.type_examen.valeurs_reference
        super().save(*args, **kwargs)


class Resultat(models.Model):
    class Interpretation(models.TextChoices):
        NORMAL = "NORMAL", _("Normal")
        BAS = "BAS", _("Anormal — bas")
        HAUT = "HAUT", _("Anormal — haut")
        ANORMAL = "ANORMAL", _("Anormal")
        NON_INTERPRETABLE = "NON_INTERPRETABLE", _("Non interprétable")

    ligne = models.OneToOneField(LigneExamen, on_delete=models.CASCADE,
                                 related_name="resultat", verbose_name=_("ligne"))
    # Biologie
    valeur = models.CharField(_("valeur mesurée"), max_length=120, blank=True)
    interpretation = models.CharField(_("interprétation"), max_length=20,
                                      choices=Interpretation.choices, blank=True)
    # Imagerie / texte libre
    compte_rendu = models.TextField(_("compte-rendu"), blank=True)
    conclusion = models.TextField(_("conclusion"), blank=True)
    fichier = models.FileField(_("pièce jointe (image / PDF)"),
                               upload_to="laboratoire/resultats/%Y/%m/",
                               null=True, blank=True)
    commentaire = models.CharField(_("commentaire"), max_length=255, blank=True)

    saisi_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name="+")
    saisi_le = models.DateTimeField(_("saisi le"), default=timezone.now)
    valide = models.BooleanField(_("validé"), default=False)
    valide_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="+")
    valide_le = models.DateTimeField(_("validé le"), null=True, blank=True)

    class Meta:
        verbose_name = _("résultat")
        verbose_name_plural = _("résultats")

    def __str__(self) -> str:
        return f"{self.ligne.type_examen.libelle} — {self.valeur or _('CR imagerie')}"

    @property
    def est_anormal(self) -> bool:
        return self.interpretation in {self.Interpretation.BAS, self.Interpretation.HAUT,
                                       self.Interpretation.ANORMAL}
