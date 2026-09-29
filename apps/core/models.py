"""
Modèles transverses du socle Kènèya Sô.

- ``TimeStampedModel`` : base abstraite horodatée + traçabilité auteur.
- ``ParametresSysteme`` : paramétrage général de l'établissement (CDC 4.10).
- ``HistoriqueAction`` : journal d'audit applicatif (CDC 4.10, 7.1, 7.4).
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .tenancy import TenantManager, etablissement_pour_creation


class Plan(models.Model):
    """Formule d'abonnement proposée aux hôpitaux (limites et tarif)."""

    code = models.SlugField(_("code"), max_length=30, unique=True)
    nom = models.CharField(_("nom"), max_length=80)
    prix_mensuel = models.DecimalField(
        _("prix mensuel (FCFA)"), max_digits=10, decimal_places=0, null=True, blank=True,
        help_text=_("Vide = à définir."))
    max_utilisateurs = models.PositiveIntegerField(
        _("utilisateurs maximum"), null=True, blank=True,
        help_text=_("Vide = illimité."))
    actif = models.BooleanField(_("proposé à l'inscription"), default=True)

    class Meta:
        verbose_name = _("plan d'abonnement")
        verbose_name_plural = _("plans d'abonnement")
        ordering = ["prix_mensuel", "nom"]

    def __str__(self) -> str:
        return self.nom


class Etablissement(models.Model):
    """Un hôpital / établissement client de la plateforme (le « locataire » du SaaS)."""

    class Statut(models.TextChoices):
        ESSAI = "ESSAI", _("Période d'essai")
        ACTIF = "ACTIF", _("Actif")
        SUSPENDU = "SUSPENDU", _("Suspendu")

    nom = models.CharField(_("nom"), max_length=200)
    slug = models.SlugField(_("identifiant court"), max_length=60, unique=True)
    statut = models.CharField(_("statut"), max_length=10, choices=Statut.choices,
                              default=Statut.ESSAI)
    essai_jusqu_au = models.DateField(_("fin de la période d'essai"), null=True, blank=True)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, null=True, blank=True,
                             related_name="etablissements", verbose_name=_("plan"),
                             help_text=_("Vide = aucune limite."))
    cree_le = models.DateTimeField(_("créé le"), auto_now_add=True)

    class Meta:
        verbose_name = _("établissement")
        verbose_name_plural = _("établissements")
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom

    @property
    def limite_utilisateurs(self):
        return self.plan.max_utilisateurs if self.plan_id else None

    def places_utilisateurs_restantes(self):
        """Nombre de comptes actifs encore créables (None = illimité)."""
        limite = self.limite_utilisateurs
        if limite is None:
            return None
        from django.contrib.auth import get_user_model
        utilises = get_user_model().tous.filter(etablissement=self, is_active=True).count()
        return max(limite - utilises, 0)

    @property
    def essai_termine(self) -> bool:
        return (self.statut == self.Statut.ESSAI and self.essai_jusqu_au is not None
                and self.essai_jusqu_au < timezone.localdate())

    @property
    def acces_autorise(self) -> bool:
        """Les utilisateurs de cet établissement peuvent-ils utiliser la plateforme ?"""
        if self.statut == self.Statut.SUSPENDU:
            return False
        return not self.essai_termine

    @property
    def jours_essai_restants(self):
        if self.statut != self.Statut.ESSAI or self.essai_jusqu_au is None:
            return None
        return max((self.essai_jusqu_au - timezone.localdate()).days, 0)

    def prolonger_essai(self, jours: int = 30) -> None:
        """Repousse la fin d'essai de ``jours`` à partir d'aujourd'hui ou de la fin actuelle
        si elle est plus tardive, et repasse l'établissement en essai (utile après une
        suspension)."""
        depart = max(self.essai_jusqu_au or timezone.localdate(), timezone.localdate())
        self.essai_jusqu_au = depart + timedelta(days=jours)
        self.statut = self.Statut.ESSAI
        self.save(update_fields=["essai_jusqu_au", "statut"])

    @classmethod
    def defaut(cls) -> "Etablissement":
        """Établissement historique/par défaut (code exécuté hors requête : commandes, tests)."""
        etab = cls.objects.order_by("pk").first()
        if etab is None:
            etab = cls.objects.create(nom="Établissement principal", slug="principal",
                                      statut=cls.Statut.ACTIF)
        return etab


class TenantOwnedModel(models.Model):
    """Base abstraite : donnée appartenant à un établissement, filtrée automatiquement."""

    etablissement = models.ForeignKey(
        "core.Etablissement", on_delete=models.PROTECT, related_name="+",
        editable=False, verbose_name=_("établissement"),
    )

    objects = TenantManager()

    class Meta:
        abstract = True

    def _etablissement_du_parent(self):
        """Un objet créé sous un parent déjà rattaché (patient, consultation…) hérite
        de son établissement, quel que soit le contexte courant (signaux, tâches)."""
        for champ in self._meta.concrete_fields:
            if not (champ.many_to_one and champ.name != "etablissement"):
                continue
            if getattr(self, champ.attname) is None:
                continue
            etab = getattr(getattr(self, champ.name, None), "etablissement_id", None)
            if etab:
                return etab
        return None

    def save(self, *args, **kwargs):
        if self.etablissement_id is None:
            self.etablissement_id = (self._etablissement_du_parent()
                                     or etablissement_pour_creation())
        super().save(*args, **kwargs)


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


class ParametresSysteme(TenantOwnedModel):
    """Paramètres généraux d'un établissement — un seul enregistrement par établissement."""

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
        constraints = [
            models.UniqueConstraint(fields=["etablissement"], name="parametres_un_par_etablissement"),
        ]

    def __str__(self) -> str:
        return self.nom_etablissement

    @classmethod
    def charger(cls) -> "ParametresSysteme":
        """Paramètres de l'établissement courant (créés au besoin)."""
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
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

    etablissement = models.ForeignKey(
        "core.Etablissement", on_delete=models.PROTECT, related_name="+",
        null=True, blank=True, editable=False, verbose_name=_("établissement"),
    )
    objects = TenantManager()

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
        etab_id = getattr(utilisateur, "etablissement_id", None)
        if etab_id is None:
            from .tenancy import contexte_courant
            ctx = contexte_courant()
            etab_id = ctx if isinstance(ctx, int) else None
        return cls.objects.create(
            etablissement_id=etab_id,
            utilisateur=utilisateur,
            action=action,
            objet_type=objet_type,
            objet_id=objet_id,
            description=description,
            adresse_ip=adresse_ip,
            donnees=donnees or {},
        )


class Notification(TenantOwnedModel):
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
        return cls.objects.create(etablissement_id=destinataire.etablissement_id,
                                  destinataire=destinataire, titre=titre,
                                  message=message, url=url)
