import logging

from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from .forms import CreationHopitalForm
from .models import Etablissement, HistoriqueAction, Notification, ParametresSysteme, Plan
from .onboarding import creer_hopital_client

logger = logging.getLogger(__name__)
Utilisateur = get_user_model()


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

    # Création : formulaire dédié (hôpital + premier administrateur) ; modification : formulaire standard.
    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = CreationHopitalForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [
                (None, {"fields": ("nom", "plan", "statut", "essai_jusqu_au")}),
                (_("Premier administrateur de l'hôpital"), {
                    "fields": ("admin_prenom", "admin_nom", "admin_email", "admin_username")}),
            ]
        return super().get_fieldsets(request, obj)

    def get_prepopulated_fields(self, request, obj=None):
        return {} if obj is None else super().get_prepopulated_fields(request, obj)

    def save_model(self, request, obj, form, change):
        if change:
            return super().save_model(request, obj, form, change)
        _etab, admin_hopital, invitation_envoyee = creer_hopital_client(form, request=request)
        if invitation_envoyee:
            self.message_user(
                request, _("Invitation envoyée à %(e)s.") % {"e": admin_hopital.email},
                messages.SUCCESS)
        else:
            self.message_user(
                request,
                _("L'hôpital est créé, mais l'e-mail d'invitation n'a pas pu être envoyé. Dans Utilisateurs, utilisez l'action « Renvoyer l'invitation »."),
                messages.WARNING)

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
            etab.prolonger_essai()
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


# --------------------------------------------------------------------------- #
# Le propriétaire de la plateforme (super-utilisateur sans établissement) n'a
# besoin, dans /admin/, que du « socle commun » : établissements, plans,
# utilisateurs et journal d'audit. Le reste (patients, pharmacie, bloc
# opératoire…) appartient à un hôpital précis et n'a rien à faire ici — ça
# alourdit son écran pour rien. On filtre donc la liste des applications
# affichée, sans toucher aux permissions : un accès direct par URL reste
# possible pour dépanner, seule la navigation est simplifiée.
# --------------------------------------------------------------------------- #
_MODELES_SOCLE_COMMUN = {
    "core": {"Etablissement", "Plan", "HistoriqueAction"},
    "accounts": {"Utilisateur"},
}
_app_list_defaut = admin.site.get_app_list


def _app_list_proprietaire(request, app_label=None):
    app_list = _app_list_defaut(request, app_label)
    if not request.user.is_authenticated or not request.user.est_plateforme:
        return app_list
    filtree = []
    for app in app_list:
        autorises = _MODELES_SOCLE_COMMUN.get(app["app_label"])
        if not autorises:
            continue
        modeles = [m for m in app["models"] if m["object_name"] in autorises]
        if modeles:
            app["models"] = modeles
            filtree.append(app)
    return filtree


admin.site.get_app_list = _app_list_proprietaire
