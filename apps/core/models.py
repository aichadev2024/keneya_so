"""
Modèles transverses du socle Kènèya Sô.

- ``TimeStampedModel`` : base abstraite horodatée + traçabilité auteur.
- ``ParametresSysteme`` : paramétrage général de l'établissement (CDC 4.10).
- ``HistoriqueAction`` : journal d'audit applicatif (CDC 4.10, 7.1, 7.4).
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStampedModel(models.Model):
    """Base abstraite : dates de création/modification et auteurs associés."""

    cree_le = models.DateTimeField(_("créé le"), auto_now_add=True)
    modifie_le = models.DateTimeField(_("modifié le"), auto_now=True)
    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("créé par"),
    )
    modifie_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("modifié par"),
    )

    class Meta:
        abstract = True
        ordering = ["-cree_le"]


class ParametresSysteme(models.Model):
    """Paramètres généraux de l'établissement — enregistrement unique (singleton)."""

    nom_etablissement = models.CharField(_("nom de l'établissement"), max_length=200,
                                         default="Kènèya Sô")
    logo = models.ImageField(_("logo"), upload_to="etablissement/", blank=True, null=True)
    adresse = models.TextField(_("adresse"), blank=True)
    telephone = models.CharField(_("téléphone"), max_length=40, blank=True)
    email = models.EmailField(_("courriel"), blank=True)
    fuseau_horaire = models.CharField(_("fuseau horaire"), max_length=64,
                                      default="Africa/Bamako")
    langues_actives = models.JSONField(
        _("langues actives"),
        default=list,
        help_text=_("Codes des langues proposées dans l'interface, ex. [\"fr\", \"bm\"]."),
    )

    class Meta:
        verbose_name = _("paramètres système")
        verbose_name_plural = _("paramètres système")

    def __str__(self) -> str:
        return self.nom_etablissement

    def save(self, *args, **kwargs):
        self.pk = 1  # force le singleton
        super().save(*args, **kwargs)

    @classmethod
    def charger(cls) -> "ParametresSysteme":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class HistoriqueAction(models.Model):
    """
    Journal d'audit : trace nominative et horodatée des actions sensibles
    (qui a fait quoi, quand, sur quel dossier) — CDC 4.10 / 7.1 / 7.4.
    """

    class Action(models.TextChoices):
        CREATION = "CREATION", _("Création")
        MODIFICATION = "MODIFICATION", _("Modification")
        CONSULTATION = "CONSULTATION", _("Consultation")
        SUPPRESSION = "SUPPRESSION", _("Suppression")
        CONNEXION = "CONNEXION", _("Connexion")
        DECONNEXION = "DECONNEXION", _("Déconnexion")
        AUTRE = "AUTRE", _("Autre")

    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="actions",
        verbose_name=_("utilisateur"),
    )
    action = models.CharField(_("action"), max_length=20, choices=Action.choices)
    objet_type = models.CharField(_("type d'objet"), max_length=100, blank=True)
    objet_id = models.CharField(_("identifiant de l'objet"), max_length=64, blank=True)
    description = models.TextField(_("description"), blank=True)
    adresse_ip = models.GenericIPAddressField(_("adresse IP"), null=True, blank=True)
    donnees = models.JSONField(_("données complémentaires"), default=dict, blank=True)
    horodatage = models.DateTimeField(_("horodatage"), default=timezone.now, db_index=True)

    class Meta:
        verbose_name = _("entrée du journal d'audit")
        verbose_name_plural = _("journal d'audit")
        ordering = ["-horodatage"]
        indexes = [
            models.Index(fields=["objet_type", "objet_id"]),
            models.Index(fields=["utilisateur", "-horodatage"]),
        ]

    def __str__(self) -> str:
        qui = self.utilisateur or _("système")
        return f"{self.horodatage:%Y-%m-%d %H:%M} — {qui} — {self.get_action_display()}"

    @classmethod
    def enregistrer(cls, *, utilisateur=None, action, objet=None, description="",
                    adresse_ip=None, donnees=None):
        """Raccourci pour créer une entrée d'audit depuis les vues/services."""
        objet_type = ""
        objet_id = ""
        if objet is not None:
            objet_type = objet.__class__.__name__
            objet_id = str(getattr(objet, "pk", ""))
        return cls.objects.create(
            utilisateur=utilisateur,
            action=action,
            objet_type=objet_type,
            objet_id=objet_id,
            description=description,
            adresse_ip=adresse_ip,
            donnees=donnees or {},
        )


class Notification(models.Model):
    """Notification interne à un utilisateur (résultats disponibles, affectations…)."""

    destinataire = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notifications", verbose_name=_("destinataire"),
    )
    titre = models.CharField(_("titre"), max_length=150)
    message = models.CharField(_("message"), max_length=500, blank=True)
    url = models.CharField(_("lien"), max_length=300, blank=True)
    lu = models.BooleanField(_("lu"), default=False)
    cree_le = models.DateTimeField(_("créée le"), default=timezone.now, db_index=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-cree_le"]
        indexes = [models.Index(fields=["destinataire", "lu", "-cree_le"])]

    def __str__(self) -> str:
        return f"{self.destinataire} — {self.titre}"

    @classmethod
    def notifier(cls, *, destinataire, titre, message="", url=""):
        if destinataire is None:
            return None
        return cls.objects.create(destinataire=destinataire, titre=titre,
                                  message=message, url=url)
