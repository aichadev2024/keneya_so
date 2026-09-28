from datetime import timedelta

from django.contrib import admin, messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Etablissement, HistoriqueAction, Notification, ParametresSysteme, Plan


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "prix_mensuel", "max_utilisateurs", "actif")


@admin.register(Etablissement)
class EtablissementAdmin(admin.ModelAdmin):
    """Console propriétaire : gestion des hôpitaux clients (super-administrateur seulement)."""

    list_display = ("nom", "slug", "statut", "plan", "essai_jusqu_au", "nb_utilisateurs", "cree_le")
    list_filter = ("statut", "plan")
    search_fields = ("nom", "slug")
    prepopulated_fields = {"slug": ("nom",)}
    actions = ["activer", "suspendre", "prolonger_essai"]

    @admin.display(description="utilisateurs")
    def nb_utilisateurs(self, obj):
        return obj.utilisateurs.filter(is_active=True).count()

    @admin.action(description="Activer l'abonnement (accès sans limite de date)")
    def activer(self, request, queryset):
        n = queryset.update(statut=Etablissement.Statut.ACTIF, essai_jusqu_au=None)
        self.message_user(request, f"{n} établissement(s) activé(s).", messages.SUCCESS)

    @admin.action(description="Suspendre l'accès")
    def suspendre(self, request, queryset):
        n = queryset.update(statut=Etablissement.Statut.SUSPENDU)
        self.message_user(request, f"{n} établissement(s) suspendu(s).", messages.WARNING)

    @admin.action(description="Prolonger l'essai de 30 jours")
    def prolonger_essai(self, request, queryset):
        n = 0
        for etab in queryset:
            depart = max(etab.essai_jusqu_au or timezone.localdate(), timezone.localdate())
            etab.essai_jusqu_au = depart + timedelta(days=30)
            etab.statut = Etablissement.Statut.ESSAI
            etab.save(update_fields=["essai_jusqu_au", "statut"])
            n += 1
        self.message_user(request, f"Essai prolongé pour {n} établissement(s).", messages.SUCCESS)


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
