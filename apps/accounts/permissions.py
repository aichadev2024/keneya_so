"""
Utilitaires de contrôle d'accès par rôle, pour les vues gabarit (mixins) et
l'API DRF (classes de permission). CDC 4.10 / 7.1.
"""

from __future__ import annotations

from django.contrib.auth.mixins import AccessMixin
from rest_framework.permissions import BasePermission, DjangoModelPermissions


class DjangoModelPermissionsStrict(DjangoModelPermissions):
    """
    Comme ``DjangoModelPermissions`` mais exige aussi ``view_<modele>`` en lecture.
    Applique le principe du moindre privilège aux endpoints d'API (CDC 7.1).
    """

    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": [],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PUT": ["%(app_label)s.change_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }


class RoleRequisMixin(AccessMixin):
    """
    Mixin pour vues basées sur classe : restreint l'accès à une liste de rôles.

    Usage :
        class MaVue(RoleRequisMixin, ListView):
            roles_autorises = ["MEDECIN", "CHIRURGIEN"]
    """

    roles_autorises: list[str] = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        if self.roles_autorises and request.user.role not in self.roles_autorises:
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)


def roles_autorises(*roles: str) -> type[BasePermission]:
    """
    Fabrique une classe de permission DRF n'autorisant que les rôles donnés.

    Usage :
        permission_classes = [IsAuthenticated, roles_autorises("ADMIN")]
    """

    class _RolesAutorises(BasePermission):
        message = "Votre rôle ne vous autorise pas à effectuer cette action."

        def has_permission(self, request, view):
            u = request.user
            return bool(
                u and u.is_authenticated and (u.is_superuser or u.role in roles)
            )

    _RolesAutorises.__name__ = "RolesAutorises_" + "_".join(roles)
    return _RolesAutorises


class EstAdministrateur(BasePermission):
    """Réservé au rôle ADMIN (ou superutilisateur)."""

    message = "Action réservée à l'administrateur."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_superuser or u.role == "ADMIN"))
