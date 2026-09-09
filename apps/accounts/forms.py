"""Formulaires d'authentification stylés Bootstrap (CDC 7.3 — ergonomie)."""

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _


class ConnexionForm(AuthenticationForm):
    """Formulaire de connexion : mêmes champs que Django, habillage Bootstrap."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "autofocus": True,
             "placeholder": _("Identifiant")}
        )
        self.fields["password"].widget.attrs.update(
            {"class": "form-control", "placeholder": _("Mot de passe")}
        )

    error_messages = {
        "invalid_login": _("Identifiant ou mot de passe incorrect."),
        "inactive": _("Ce compte est désactivé. Contactez l'administrateur."),
    }
