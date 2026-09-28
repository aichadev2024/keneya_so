"""Formulaires d'authentification stylés Bootstrap (CDC 7.3 — ergonomie)."""

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
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


class InscriptionHopitalForm(forms.Form):
    """Inscription en libre-service d'un hôpital : établissement + premier administrateur."""

    nom_hopital = forms.CharField(label=_("Nom de l'hôpital"), max_length=200)
    prenom = forms.CharField(label=_("Prénom"), max_length=150)
    nom = forms.CharField(label=_("Nom"), max_length=150)
    email = forms.EmailField(label=_("Adresse e-mail"))
    username = forms.CharField(label=_("Identifiant de connexion"), max_length=150)
    password1 = forms.CharField(label=_("Mot de passe"), widget=forms.PasswordInput,
                                strip=False)
    password2 = forms.CharField(label=_("Confirmation du mot de passe"),
                                widget=forms.PasswordInput, strip=False)
    # Piège à robots : masqué aux humains par CSS, un robot le remplit.
    site_web = forms.CharField(required=False, widget=forms.TextInput(
        attrs={"tabindex": "-1", "autocomplete": "off"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nom, champ in self.fields.items():
            if nom != "site_web":
                champ.widget.attrs["class"] = "form-control"
        self.fields["nom_hopital"].widget.attrs["autofocus"] = True

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if Utilisateur.tous.filter(username__iexact=username).exists():
            raise ValidationError(_("Cet identifiant est déjà utilisé."))
        return username

    def clean_site_web(self):
        if self.cleaned_data.get("site_web"):
            raise ValidationError("")
        return ""

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2:
            if p1 != p2:
                self.add_error("password2", _("Les deux mots de passe ne correspondent pas."))
            else:
                try:
                    password_validation.validate_password(
                        p1, Utilisateur(username=data.get("username", ""),
                                        first_name=data.get("prenom", ""),
                                        last_name=data.get("nom", ""),
                                        email=data.get("email", "")))
                except ValidationError as exc:
                    self.add_error("password1", exc)
        return data
