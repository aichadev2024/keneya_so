"""Formulaires d'authentification stylés Bootstrap (CDC 7.3 — ergonomie)."""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

Utilisateur = get_user_model()


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


class PremiereConfigurationForm(UserCreationForm):
    """Création du tout premier compte administrateur.

    Hérite de ``UserCreationForm`` : mêmes règles de robustesse de mot de
    passe que partout ailleurs dans l'application (``AUTH_PASSWORD_VALIDATORS``).
    Le champ ``jeton`` est vérifié séparément dans la vue, contre
    ``settings.SETUP_TOKEN`` — cette page reste accessible tant qu'aucun
    superutilisateur n'existe, y compris sur un déploiement déjà public.
    """

    jeton = forms.CharField(
        label=_("Jeton d'installation"),
        widget=forms.PasswordInput(attrs={"placeholder": _("Jeton d'installation")}),
    )

    class Meta(UserCreationForm.Meta):
        model = Utilisateur
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nom in ("username", "first_name", "last_name", "email",
                    "password1", "password2", "jeton"):
            self.fields[nom].widget.attrs["class"] = "form-control"
        self.fields["username"].widget.attrs["autofocus"] = True
        self.fields["email"].required = True
