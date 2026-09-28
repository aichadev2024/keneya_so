import logging
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Etablissement, HistoriqueAction, Notification, ParametresSysteme, Plan
from .onboarding import initialiser_etablissement, slug_unique

logger = logging.getLogger(__name__)
Utilisateur = get_user_model()


class CreationHopitalForm(forms.ModelForm):
    """Création d'un hôpital client par le propriétaire : l'établissement + son premier administrateur.

    L'administrateur reçoit un e-mail d'invitation (identifiant + lien pour choisir son
    mot de passe) : le propriétaire ne connaît ni ne transmet jamais de mot de passe.
    """

    admin_prenom = forms.CharField(label=_("Prénom de l'administrateur"), max_length=150)
    admin_nom = forms.CharField(label=_("Nom de l'administrateur"), max_length=150)
    admin_email = forms.EmailField(label=_("E-mail de l'administrateur"),
                                   help_text=_("L'invitation et le lien de connexion y seront envoyés."))
    admin_username = forms.CharField(label=_("Identifiant de connexion"), max_length=150)

    class Meta:
        model = Etablissement
        fields = ("nom", "plan", "statut", "essai_jusqu_au")

    def clean_admin_username(self):
        username = self.cleaned_data["admin_username"].strip()
        if Utilisateur.tous.filter(username__iexact=username).exists():
            raise forms.ValidationError(_("Cet identifiant est déjà utilisé."))
        return username


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
        obj.slug = slug_unique(obj.nom)
        if obj.statut == Etablissement.Statut.ESSAI and not obj.essai_jusqu_au:
            obj.essai_jusqu_au = timezone.localdate() + timedelta(days=settings.ESSAI_DUREE_JOURS)
        super().save_model(request, obj, form, change)
        d = form.cleaned_data
        admin_hopital = initialiser_etablissement(
            obj, prenom=d["admin_prenom"], nom=d["admin_nom"], email=d["admin_email"],
            username=d["admin_username"], utilisateur_journal=request.user,
            description=f"Hôpital « {obj.nom} » créé par le propriétaire de la plateforme",
        )
        from apps.accounts.invitations import envoyer_invitation
        try:
            envoyer_invitation(admin_hopital, request)
        except Exception:  # SMTP indisponible, adresse refusée…
            logger.exception("Échec d'envoi de l'invitation à l'administrateur de %s", obj.pk)
            self.message_user(
                request,
                _("L'hôpital est créé, mais l'e-mail d'invitation n'a pas pu être envoyé. Dans Utilisateurs, utilisez l'action « Renvoyer l'invitation »."),
                messages.WARNING)
        else:
            self.message_user(
                request, _("Invitation envoyée à %(e)s.") % {"e": admin_hopital.email},
                messages.SUCCESS)

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
