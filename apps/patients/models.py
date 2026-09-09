"""
Patients et dossiers médicaux (CDC 4.1 et 4.2).

- ``Patient`` : identité, coordonnées, identifiant de dossier unique.
- ``DossierMedical`` : antécédents et informations médicales de fond (1-1 patient).
- ``Allergie`` : allergies déclarées, exploitées plus tard pour les alertes de
  prescription (CDC 4.3).
"""

from __future__ import annotations

from datetime import date

from django.db import models
from django.db.models import Max
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel

PREFIXE_DOSSIER = "KS"


class GroupeSanguin(models.TextChoices):
    A_POS = "A+", "A+"
    A_NEG = "A-", "A-"
    B_POS = "B+", "B+"
    B_NEG = "B-", "B-"
    AB_POS = "AB+", "AB+"
    AB_NEG = "AB-", "AB-"
    O_POS = "O+", "O+"
    O_NEG = "O-", "O-"
    INCONNU = "INCONNU", _("Inconnu")


class PatientQuerySet(models.QuerySet):
    def actifs(self):
        return self.filter(actif=True)

    def recherche(self, terme: str):
        """Recherche multicritère : nom, prénom, n° de dossier, téléphone (CDC 4.1)."""
        terme = (terme or "").strip()
        if not terme:
            return self
        return self.filter(
            models.Q(nom__icontains=terme)
            | models.Q(prenom__icontains=terme)
            | models.Q(numero_dossier__icontains=terme)
            | models.Q(telephone__icontains=terme)
        )


class Patient(TimeStampedModel):
    class Sexe(models.TextChoices):
        MASCULIN = "M", _("Masculin")
        FEMININ = "F", _("Féminin")

    class StatutMatrimonial(models.TextChoices):
        CELIBATAIRE = "CELIBATAIRE", _("Célibataire")
        MARIE = "MARIE", _("Marié(e)")
        DIVORCE = "DIVORCE", _("Divorcé(e)")
        VEUF = "VEUF", _("Veuf/Veuve")
        AUTRE = "AUTRE", _("Autre")

    numero_dossier = models.CharField(
        _("numéro de dossier"), max_length=20, unique=True, editable=False,
        help_text=_("Identifiant unique du patient, attribué automatiquement."),
    )
    nom = models.CharField(_("nom"), max_length=100)
    prenom = models.CharField(_("prénom"), max_length=100)
    sexe = models.CharField(_("sexe"), max_length=1, choices=Sexe.choices)
    date_naissance = models.DateField(_("date de naissance"), null=True, blank=True)
    date_naissance_estimee = models.BooleanField(
        _("date de naissance estimée"), default=False,
        help_text=_("Cochez si seule l'année ou l'âge approximatif est connu."),
    )
    lieu_naissance = models.CharField(_("lieu de naissance"), max_length=120, blank=True)
    nationalite = models.CharField(_("nationalité"), max_length=60, blank=True,
                                   default="Malienne")

    telephone = models.CharField(_("téléphone"), max_length=40, blank=True)
    adresse = models.CharField(_("adresse"), max_length=255, blank=True)
    ville = models.CharField(_("ville / commune"), max_length=120, blank=True)

    personne_a_prevenir = models.CharField(_("personne à prévenir"), max_length=150,
                                           blank=True)
    lien_personne_a_prevenir = models.CharField(_("lien de parenté"), max_length=60,
                                                blank=True)
    telephone_urgence = models.CharField(_("téléphone d'urgence"), max_length=40,
                                         blank=True)

    profession = models.CharField(_("profession"), max_length=120, blank=True)
    statut_matrimonial = models.CharField(
        _("statut matrimonial"), max_length=20, choices=StatutMatrimonial.choices,
        blank=True,
    )
    groupe_sanguin = models.CharField(
        _("groupe sanguin"), max_length=8, choices=GroupeSanguin.choices,
        default=GroupeSanguin.INCONNU,
    )
    photo = models.ImageField(_("photo"), upload_to="patients/photos/", blank=True,
                              null=True)

    actif = models.BooleanField(
        _("actif"), default=True,
        help_text=_("Décochez pour archiver le dossier sans le supprimer."),
    )

    objects = PatientQuerySet.as_manager()

    class Meta:
        verbose_name = _("patient")
        verbose_name_plural = _("patients")
        ordering = ["nom", "prenom"]
        indexes = [
            models.Index(fields=["nom", "prenom"]),
            models.Index(fields=["telephone"]),
        ]

    def __str__(self) -> str:
        return f"{self.numero_dossier} — {self.nom.upper()} {self.prenom}"

    def save(self, *args, **kwargs):
        if not self.numero_dossier:
            self.numero_dossier = self._generer_numero_dossier()
        super().save(*args, **kwargs)

    @staticmethod
    def _generer_numero_dossier() -> str:
        annee = date.today().year
        prefixe = f"{PREFIXE_DOSSIER}-{annee}-"
        dernier = (
            Patient.objects.filter(numero_dossier__startswith=prefixe)
            .aggregate(m=Max("numero_dossier"))
            .get("m")
        )
        sequence = int(dernier.split("-")[-1]) + 1 if dernier else 1
        return f"{prefixe}{sequence:06d}"

    @property
    def nom_complet(self) -> str:
        return f"{self.nom.upper()} {self.prenom}".strip()

    @property
    def age(self) -> int | None:
        if not self.date_naissance:
            return None
        aujourd_hui = date.today()
        return (
            aujourd_hui.year
            - self.date_naissance.year
            - ((aujourd_hui.month, aujourd_hui.day)
               < (self.date_naissance.month, self.date_naissance.day))
        )


class DossierMedical(TimeStampedModel):
    """Informations médicales de fond du patient (CDC 4.2)."""

    patient = models.OneToOneField(
        Patient, on_delete=models.CASCADE, related_name="dossier_medical",
        verbose_name=_("patient"),
    )
    antecedents_medicaux = models.TextField(_("antécédents médicaux"), blank=True)
    antecedents_chirurgicaux = models.TextField(_("antécédents chirurgicaux"), blank=True)
    antecedents_familiaux = models.TextField(_("antécédents familiaux"), blank=True)
    antecedents_gyneco_obstetricaux = models.TextField(
        _("antécédents gynéco-obstétricaux"), blank=True,
    )
    traitements_en_cours = models.TextField(_("traitements en cours"), blank=True)
    habitudes_vie = models.TextField(
        _("habitudes de vie"), blank=True,
        help_text=_("Tabac, alcool, activité physique, régime particulier…"),
    )
    observations = models.TextField(_("observations générales"), blank=True)

    class Meta:
        verbose_name = _("dossier médical")
        verbose_name_plural = _("dossiers médicaux")

    def __str__(self) -> str:
        return _("Dossier médical de %(p)s") % {"p": self.patient.nom_complet}


class Allergie(models.Model):
    class Type(models.TextChoices):
        MEDICAMENTEUSE = "MEDICAMENTEUSE", _("Médicamenteuse")
        ALIMENTAIRE = "ALIMENTAIRE", _("Alimentaire")
        ENVIRONNEMENTALE = "ENVIRONNEMENTALE", _("Environnementale")
        AUTRE = "AUTRE", _("Autre")

    class Severite(models.TextChoices):
        LEGERE = "LEGERE", _("Légère")
        MODEREE = "MODEREE", _("Modérée")
        SEVERE = "SEVERE", _("Sévère")

    dossier = models.ForeignKey(
        DossierMedical, on_delete=models.CASCADE, related_name="allergies",
        verbose_name=_("dossier médical"),
    )
    libelle = models.CharField(_("allergène"), max_length=150)
    type = models.CharField(_("type"), max_length=20, choices=Type.choices,
                            default=Type.MEDICAMENTEUSE)
    severite = models.CharField(_("sévérité"), max_length=10, choices=Severite.choices,
                                default=Severite.MODEREE)
    remarque = models.CharField(_("remarque"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("allergie")
        verbose_name_plural = _("allergies")
        constraints = [
            models.UniqueConstraint(
                fields=["dossier", "libelle"], name="allergie_unique_par_dossier",
            ),
        ]
        ordering = ["libelle"]

    def __str__(self) -> str:
        return f"{self.libelle} ({self.get_severite_display()})"
