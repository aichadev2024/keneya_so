"""
Modèle utilisateur personnalisé et rôles métier de Kènèya Sô.

Le contrôle d'accès est fondé sur les rôles (RBAC — CDC 4.10 / 7.1) : chaque
utilisateur porte un ``role`` métier, auquel correspond un groupe Django dont
les permissions sont recalculées à chaque migration (voir ``roles.py`` et
``signals.py``). Principe du moindre privilège.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class Utilisateur(AbstractUser):
    """Compte du personnel hospitalier. ``username`` reste l'identifiant de connexion."""

    class Role(models.TextChoices):
        ADMIN = "ADMIN", _("Administrateur")
        MEDECIN = "MEDECIN", _("Médecin")
        INFIRMIER = "INFIRMIER", _("Infirmier(ère)")
        PHARMACIEN = "PHARMACIEN", _("Pharmacien(ne)")
        LABORANTIN = "LABORANTIN", _("Laborantin(e)")
        RADIOLOGUE = "RADIOLOGUE", _("Radiologue / agent d'imagerie")
        AGENT_ACCUEIL = "AGENT_ACCUEIL", _("Agent d'accueil")
        COMPTABLE = "COMPTABLE", _("Comptable")
        # Personnel du bloc opératoire (CDC section 5.2)
        CHIRURGIEN = "CHIRURGIEN", _("Chirurgien(ne)")
        ANESTHESISTE = "ANESTHESISTE", _("Médecin anesthésiste-réanimateur")
        IBODE = "IBODE", _("Infirmier(ère) de bloc opératoire (IBODE)")
        AGENT_STERILISATION = "AGENT_STERILISATION", _("Agent de stérilisation")
        CADRE_BLOC = "CADRE_BLOC", _("Agent de programmation / cadre de bloc")

    class Langue(models.TextChoices):
        FR = "fr", _("Français")
        EN = "en", _("Anglais")
        AR = "ar", _("Arabe")
        BM = "bm", _("Bambara")
        FF = "ff", _("Peulh (fulfulde)")
        SNK = "snk", _("Soninké")

    role = models.CharField(
        _("rôle"), max_length=32, choices=Role.choices, blank=True,
        help_text=_("Détermine les fonctions et les données accessibles (RBAC)."),
    )
    matricule = models.CharField(_("matricule"), max_length=40, blank=True, unique=True,
                                 null=True)
    telephone = models.CharField(_("téléphone"), max_length=40, blank=True)
    specialite = models.CharField(_("spécialité"), max_length=120, blank=True)
    langue_preferee = models.CharField(_("langue préférée"), max_length=8,
                                       choices=Langue.choices, default=Langue.FR)

    # ``email`` : rendu unique (rattachement fiable, réinitialisation de mot de passe).
    email = models.EmailField(_("adresse électronique"), blank=True)

    class Meta(AbstractUser.Meta):
        verbose_name = _("utilisateur")
        verbose_name_plural = _("utilisateurs")

    def __str__(self) -> str:
        nom_complet = self.get_full_name()
        base = nom_complet or self.username
        return f"{base} — {self.get_role_display()}" if self.role else base

    @property
    def est_personnel_bloc(self) -> bool:
        return self.role in {
            self.Role.CHIRURGIEN, self.Role.ANESTHESISTE, self.Role.IBODE,
            self.Role.AGENT_STERILISATION, self.Role.CADRE_BLOC,
        }

    @property
    def nom_groupe_role(self) -> str:
        return groupe_pour_role(self.role)


def groupe_pour_role(role: str) -> str:
    """Nom canonique du groupe Django associé à un rôle métier."""
    return f"role:{role}" if role else ""
