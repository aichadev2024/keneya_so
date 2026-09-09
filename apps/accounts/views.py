"""Vues d'authentification (gabarits) — CDC 4.10 / 7.1."""

from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

from .forms import ConnexionForm


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
