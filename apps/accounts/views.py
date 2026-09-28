"""Vues d'authentification (gabarits) — CDC 4.10 / 7.1."""

import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth import get_user_model, login
from django.core.cache import cache
from django.shortcuts import redirect
from django.db import transaction
from django.http import Http404
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView

from .forms import (
    ConnexionForm, DemandeReinitialisationForm, InscriptionHopitalForm,
    NouveauMotDePasseForm, PremiereConfigurationForm,
)

Utilisateur = get_user_model()
journal = logging.getLogger(__name__)


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


class MotDePasseOublieView(auth_views.PasswordResetView):
    """Envoi d'un lien de réinitialisation par e-mail.

    La réponse est identique que l'adresse existe ou non (pas d'énumération de
    comptes), et l'envoi est limité par adresse IP et par adresse e-mail pour
    qu'on ne puisse pas s'en servir pour inonder la boîte de quelqu'un.
    """

    template_name = "registration/mot_de_passe_oublie.html"
    form_class = DemandeReinitialisationForm
    email_template_name = "registration/mot_de_passe_email.txt"
    subject_template_name = "registration/mot_de_passe_objet.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    MAX_PAR_IP = 5
    MAX_PAR_EMAIL = 3

    def _autorise(self, email):
        from .signals import _ip
        cles = ((f"reinit-ip:{_ip(self.request) or 'inconnue'}", self.MAX_PAR_IP),
                (f"reinit-email:{email.strip().lower()}", self.MAX_PAR_EMAIL))
        if any(cache.get(cle, 0) >= maxi for cle, maxi in cles):
            return False
        for cle, _maxi in cles:
            cache.set(cle, cache.get(cle, 0) + 1, 3600)
        return True

    def form_valid(self, form):
        if self._autorise(form.cleaned_data["email"]):
            try:
                form.save(
                    request=self.request, use_https=self.request.is_secure(),
                    from_email=self.from_email, email_template_name=self.email_template_name,
                    subject_template_name=self.subject_template_name,
                    extra_email_context=self.extra_email_context,
                )
            except Exception:  # SMTP indisponible : ne rien révéler à l'utilisateur
                journal.exception("Échec d'envoi de l'e-mail de réinitialisation")
        return redirect(self.get_success_url())


class MotDePasseOublieEnvoyeView(auth_views.PasswordResetDoneView):
    template_name = "registration/mot_de_passe_envoye.html"


class NouveauMotDePasseView(auth_views.PasswordResetConfirmView):
    template_name = "registration/mot_de_passe_nouveau.html"
    form_class = NouveauMotDePasseForm
    success_url = reverse_lazy("accounts:password_reset_complete")
    post_reset_login = False

    def form_valid(self, form):
        reponse = super().form_valid(form)
        utilisateur = form.user
        # Un compte verrouillé pour échecs répétés (django-axes) redevient utilisable.
        from axes.utils import reset
        reset(username=utilisateur.username)
        from apps.core.models import HistoriqueAction
        from .signals import _ip
        HistoriqueAction.enregistrer(
            utilisateur=utilisateur, action=HistoriqueAction.Action.MODIFICATION,
            objet=utilisateur, description="Mot de passe réinitialisé par lien e-mail",
            adresse_ip=_ip(self.request),
        )
        return reponse


class NouveauMotDePasseTermineView(auth_views.PasswordResetCompleteView):
    template_name = "registration/mot_de_passe_termine.html"


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
        if not settings.SETUP_TOKEN or Utilisateur.tous.filter(is_superuser=True).exists():
            raise Http404
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        if not secrets.compare_digest(form.cleaned_data.get("jeton", ""), settings.SETUP_TOKEN):
            form.add_error("jeton", _("Jeton d'installation incorrect."))
            return self.form_invalid(form)

        with transaction.atomic():
            if Utilisateur.tous.select_for_update().filter(is_superuser=True).exists():
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


class InscriptionHopitalView(FormView):
    """Inscription en libre-service d'un hôpital (SaaS) : essai gratuit, sans carte bancaire."""

    template_name = "registration/inscription_hopital.html"
    form_class = InscriptionHopitalForm

    # Limite anti-abus : au plus N inscriptions par adresse IP et par heure.
    MAX_PAR_HEURE = 5

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def _cle(self):
        from .signals import _ip
        return f"inscription:{_ip(self.request) or 'inconnue'}"

    def form_valid(self, form):
        cle = self._cle()
        if cache.get(cle, 0) >= self.MAX_PAR_HEURE:
            form.add_error(None, _("Trop d'inscriptions depuis cette adresse. Réessayez plus tard."))
            return self.form_invalid(form)
        cache.set(cle, cache.get(cle, 0) + 1, 3600)

        from apps.core.onboarding import inscrire_hopital
        d = form.cleaned_data
        _etab, admin = inscrire_hopital(
            nom_hopital=d["nom_hopital"], prenom=d["prenom"], nom=d["nom"],
            email=d["email"], username=d["username"], password=d["password1"],
            adresse_ip=self.request.META.get("REMOTE_ADDR"),
        )
        login(self.request, admin, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, _("Bienvenue ! Votre hôpital est créé, votre période d'essai commence."))
        return redirect("core:dashboard")
