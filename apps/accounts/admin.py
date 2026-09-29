import logging

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .forms import CreationPersonnelForm
from .invitations import envoyer_invitation
from .models import Utilisateur

logger = logging.getLogger(__name__)


def _est_plateforme(request) -> bool:
    """Super-administrateur de la plateforme (n'appartient à aucun hôpital)."""
    return request.user.est_plateforme


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
    add_form = CreationPersonnelForm
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("username", "first_name", "last_name", "email")}),
        (_("Profil métier Kènèya Sô"), {
            "fields": ("etablissement", "role", "matricule", "telephone", "specialite",
                       "langue_preferee"),
        }),
    )
    actions = ["renvoyer_invitation"]

    def _inviter(self, request, utilisateur) -> bool:
        try:
            envoyer_invitation(utilisateur, request)
        except Exception:  # SMTP indisponible, adresse refusée…
            logger.exception("Échec d'envoi de l'invitation à %s", utilisateur.pk)
            self.message_user(
                request,
                _("Le compte « %(u)s » est créé, mais l'e-mail d'invitation n'a pas pu être envoyé. Utilisez l'action « Renvoyer l'invitation » plus tard.")
                % {"u": utilisateur.username}, messages.WARNING)
            return False
        self.message_user(
            request, _("Invitation envoyée à %(e)s.") % {"e": utilisateur.email}, messages.SUCCESS)
        return True

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            self._inviter(request, obj)

    @admin.action(description=_("Renvoyer l'invitation (identifiant + lien de connexion)"))
    def renvoyer_invitation(self, request, queryset):
        for utilisateur in queryset:
            if not utilisateur.email:
                self.message_user(
                    request, _("« %(u)s » n'a pas d'adresse e-mail.") % {"u": utilisateur.username},
                    messages.ERROR)
            elif not utilisateur.is_active:
                self.message_user(
                    request, _("« %(u)s » est désactivé.") % {"u": utilisateur.username},
                    messages.ERROR)
            else:
                self._inviter(request, utilisateur)

    @admin.display(description=_("nom complet"))
    def get_full_name(self, obj):
        return obj.get_full_name()
