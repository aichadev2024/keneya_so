"""Vues d'authentification (gabarits) — CDC 4.10 / 7.1."""

import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import Http404
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from .forms import ConnexionForm, PremiereConfigurationForm

Utilisateur = get_user_model()


class ConnexionView(auth_views.LoginView):
    template_name = "registration/login.html"
    authentication_form = ConnexionForm
    redirect_authenticated_user = True


class DeconnexionView(auth_views.LogoutView):
    next_page = reverse_lazy("accounts:login")


class ChangementMotDePasseView(auth_views.PasswordChangeView):
    template_name = "registration/password_change.html"
    success_url = reverse_lazy("accounts:password_change_done")


class ChangementMotDePasseTermineView(auth_views.PasswordChangeDoneView):
    template_name = "registration/password_change_done.html"


class PremiereConfigurationView(FormView):
    """Création du tout premier compte administrateur (CDC 7.1).

    Verrouillée dès qu'un superutilisateur existe, et protégée en plus par un
    jeton d'installation (``DJANGO_SETUP_TOKEN``) : sur un déploiement déjà
    public, sans ce jeton n'importe qui pourrait sinon créer le premier admin
    avant le vrai propriétaire. Sans jeton configuré, la page est désactivée.
    """

    template_name = "registration/premiere_configuration.html"
    form_class = PremiereConfigurationForm
    success_url = reverse_lazy("accounts:login")

    def dispatch(self, request, *args, **kwargs):
        if not settings.SETUP_TOKEN or Utilisateur.objects.filter(is_superuser=True).exists():
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        if not secrets.compare_digest(form.cleaned_data.get("jeton", ""), settings.SETUP_TOKEN):
            form.add_error("jeton", _("Jeton d'installation incorrect."))
            return self.form_invalid(form)

        with transaction.atomic():
            if Utilisateur.objects.select_for_update().filter(is_superuser=True).exists():
                form.add_error(None, _("Un compte administrateur existe déjà."))
                return self.form_invalid(form)
            utilisateur = form.save(commit=False)
            utilisateur.is_superuser = True
            utilisateur.is_staff = True
            utilisateur.role = Utilisateur.Role.ADMIN
            utilisateur.save()

        from apps.core.models import HistoriqueAction
        HistoriqueAction.enregistrer(
            utilisateur=utilisateur, action=HistoriqueAction.Action.CREATION,
            objet=utilisateur,
            description="Premier compte administrateur créé via la configuration initiale",
        )
        messages.success(self.request,
                         _("Compte administrateur créé. Vous pouvez vous connecter."))
        return super().form_valid(form)
