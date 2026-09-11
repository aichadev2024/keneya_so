from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import HistoriqueAction, Notification, ParametresSysteme


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("destinataire", "titre", "lu", "cree_le")
    list_filter = ("lu", "cree_le")
    search_fields = ("destinataire__username", "titre", "message")


@admin.register(ParametresSysteme)
class ParametresSystemeAdmin(admin.ModelAdmin):
    list_display = ("nom_etablissement", "telephone", "email", "fuseau_horaire")

    def has_add_permission(self, request):
        # Singleton : interdit d'en créer un second.
        return not ParametresSysteme.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(HistoriqueAction)
class HistoriqueActionAdmin(admin.ModelAdmin):
    list_display = ("horodatage", "utilisateur", "action", "objet_type", "objet_id",
                    "adresse_ip")
    list_filter = ("action", "objet_type", "horodatage")
    search_fields = ("description", "objet_id", "utilisateur__username",
                     "utilisateur__last_name")
    date_hierarchy = "horodatage"
    readonly_fields = ("utilisateur", "action", "objet_type", "objet_id", "description",
                       "adresse_ip", "donnees", "horodatage")

    fieldsets = ((None, {"fields": readonly_fields}),)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Le journal d'audit est en append-only (CDC 7.4 — traçabilité).
        return False

    class Meta:
        verbose_name = _("journal d'audit")
