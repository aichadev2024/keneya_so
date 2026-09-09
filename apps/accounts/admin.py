from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import Utilisateur


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    """Administration des comptes du personnel (CDC 4.10)."""

    list_display = ("username", "get_full_name", "role", "matricule", "is_active",
                    "is_staff", "last_login")
    list_filter = ("role", "is_active", "is_staff", "langue_preferee")
    search_fields = ("username", "first_name", "last_name", "email", "matricule")
    ordering = ("last_name", "first_name")

    fieldsets = UserAdmin.fieldsets + (
        (_("Profil métier Kènèya Sô"), {
            "fields": ("role", "matricule", "telephone", "specialite", "langue_preferee"),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (_("Profil métier Kènèya Sô"), {
            "fields": ("role", "matricule", "telephone", "specialite", "langue_preferee"),
        }),
    )

    @admin.display(description=_("nom complet"))
    def get_full_name(self, obj):
        return obj.get_full_name()
