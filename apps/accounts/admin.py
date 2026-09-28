from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import Utilisateur


def _est_plateforme(request) -> bool:
    """Super-administrateur de la plateforme (n'appartient à aucun hôpital)."""
    u = request.user
    return u.is_superuser and u.etablissement_id is None


# Champs qu'un administrateur d'hôpital ne doit jamais pouvoir modifier : ils
# permettraient de s'attribuer des droits de plateforme ou de changer d'hôpital.
_CHAMPS_PLATEFORME = {"is_superuser", "groups", "user_permissions", "etablissement", "is_staff"}


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    """Administration des comptes du personnel (CDC 4.10)."""

    def get_queryset(self, request):
        # Gestionnaire filtré (établissement courant) plutôt que le défaut non filtré.
        qs = Utilisateur.objects.all()
        ordering = self.get_ordering(request)
        return qs.order_by(*ordering) if ordering else qs

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if _est_plateforme(request):
            return fieldsets
        return [
            (titre, {**opts, "fields": tuple(f for f in opts["fields"]
                                             if f not in _CHAMPS_PLATEFORME)})
            for titre, opts in fieldsets
        ]

    list_display = ("username", "get_full_name", "etablissement", "role", "matricule", "is_active",
                    "is_staff", "last_login")
    list_filter = ("role", "is_active", "is_staff", "langue_preferee")
    search_fields = ("username", "first_name", "last_name", "email", "matricule")
    ordering = ("last_name", "first_name")

    fieldsets = UserAdmin.fieldsets + (
        (_("Profil métier Kènèya Sô"), {
            "fields": ("etablissement", "role", "matricule", "telephone", "specialite",
                       "langue_preferee"),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (_("Profil métier Kènèya Sô"), {
            "fields": ("etablissement", "role", "matricule", "telephone", "specialite",
                       "langue_preferee"),
        }),
    )

    @admin.display(description=_("nom complet"))
    def get_full_name(self, obj):
        return obj.get_full_name()
