"""
Synchronisation RBAC (CDC 4.10 / 7.1).

- ``post_migrate`` : (re)crée un groupe Django par rôle métier et y applique les
  permissions déclarées dans ``roles.py``.
- ``post_save`` sur ``Utilisateur`` : aligne l'appartenance aux groupes et le
  drapeau ``is_staff`` sur le rôle courant.
- connexion / déconnexion : alimentent le journal d'audit (``core.HistoriqueAction``).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import Utilisateur, groupe_pour_role

logger = logging.getLogger("keneya.accounts")


def _permissions_des_apps_gerees():
    from .roles import APPS_GEREES

    return Permission.objects.filter(content_type__app_label__in=APPS_GEREES)


@receiver(post_migrate)
def synchroniser_groupes_de_roles(sender, **kwargs):
    """Recalcule les groupes de rôles après chaque migration."""
    # N'exécuter qu'une fois, quand l'app accounts a fini de migrer.
    if getattr(sender, "label", None) != "accounts":
        return

    # accounts est déclarée avant les modules métier dans INSTALLED_APPS : leurs
    # permissions ne sont pas encore créées à ce stade du post_migrate. On les
    # matérialise explicitement avant de constituer les groupes.
    from django.apps import apps as django_apps
    from django.contrib.auth.management import create_permissions

    for app_config in django_apps.get_app_configs():
        if app_config.models_module is not None:
            create_permissions(app_config, verbosity=0)

    from .roles import PERMISSIONS_PAR_ROLE

    toutes = {f"{p.content_type.app_label}.{p.codename}": p
              for p in _permissions_des_apps_gerees().select_related("content_type")}

    for role, codenames in PERMISSIONS_PAR_ROLE.items():
        groupe, _created = Group.objects.get_or_create(name=groupe_pour_role(role))
        if "*" in codenames:
            perms = list(toutes.values())
        else:
            perms = [toutes[c] for c in codenames if c in toutes]
            manquantes = [c for c in codenames if c not in toutes]
            if manquantes:
                logger.warning("Rôle %s : permissions inconnues ignorées : %s",
                               role, ", ".join(manquantes))
        groupe.permissions.set(perms)

    logger.info("Groupes de rôles synchronisés (%d rôles).", len(PERMISSIONS_PAR_ROLE))


@receiver(post_save, sender=Utilisateur)
def aligner_groupe_utilisateur(sender, instance: Utilisateur, **kwargs):
    """Un utilisateur n'appartient qu'au groupe de son rôle courant."""
    groupes_de_roles = list(
        instance.groups.filter(name__startswith="role:").values_list("name", flat=True)
    )
    cible = groupe_pour_role(instance.role)

    if groupes_de_roles == ([cible] if cible else []):
        return  # déjà cohérent, on évite une écriture inutile

    instance.groups.remove(*Group.objects.filter(name__startswith="role:"))
    if cible:
        groupe, _created = Group.objects.get_or_create(name=cible)
        instance.groups.add(groupe)

    # L'administrateur métier accède à l'interface d'administration Django
    # (CDC 9 — « Interface d'administration complète via Django admin »).
    doit_etre_staff = instance.role == Utilisateur.Role.ADMIN or instance.is_superuser
    if instance.is_staff != doit_etre_staff and not instance.is_superuser:
        sender.objects.filter(pk=instance.pk).update(is_staff=doit_etre_staff)


@receiver(user_logged_in)
def journaliser_connexion(sender, request, user, **kwargs):
    from apps.core.models import HistoriqueAction

    HistoriqueAction.enregistrer(
        utilisateur=user,
        action=HistoriqueAction.Action.CONNEXION,
        adresse_ip=_ip(request),
    )


@receiver(user_logged_out)
def journaliser_deconnexion(sender, request, user, **kwargs):
    from apps.core.models import HistoriqueAction

    if user is None:
        return
    HistoriqueAction.enregistrer(
        utilisateur=user,
        action=HistoriqueAction.Action.DECONNEXION,
        adresse_ip=_ip(request),
    )


def _ip(request):
    """Adresse IP consignée dans le journal d'audit.

    ``X-Forwarded-For`` est un en-tête HTTP ordinaire : sans reverse-proxy de
    confiance connu, n'importe quel client peut y écrire ce qu'il veut, ce qui
    rendrait l'IP du journal d'audit falsifiable. Par défaut on ne fait donc
    confiance qu'à ``REMOTE_ADDR`` (jamais falsifiable, c'est l'adresse TCP
    réelle). En production derrière un reverse-proxy connu (Render/Railway),
    ``DJANGO_PROXIES_DE_CONFIANCE=1`` indique qu'un seul maillon de confiance
    précède l'application : on prend alors l'IP à N positions du bout de la
    chaîne ``X-Forwarded-For`` (en ignorant tout ce qu'un client aurait pu
    préfixer lui-même avant d'atteindre ce proxy), jamais aveuglément la
    première valeur.
    """
    if request is None:
        return None
    proxies_de_confiance = getattr(settings, "IP_PROXIES_DE_CONFIANCE", 0)
    if proxies_de_confiance > 0:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            chaine = [ip.strip() for ip in xff.split(",") if ip.strip()]
            index = len(chaine) - proxies_de_confiance
            if 0 <= index < len(chaine):
                return chaine[index]
    return request.META.get("REMOTE_ADDR")
