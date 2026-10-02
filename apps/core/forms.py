"""Formulaires de la console propriétaire (super-administrateur de la plateforme)."""

from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from apps.accounts.forms import CreationPersonnelForm

from .models import Etablissement, Plan, Specialite

Utilisateur = get_user_model()

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}
_DATE = {"class": "form-control", "type": "date"}
_CHECK = {"class": "form-check-input"}


class _CasesACocher(forms.CheckboxSelectMultiple):
    """Cases à cocher : la classe Bootstrap va sur chaque case, pas sur le conteneur."""

    def create_option(self, *args, **kwargs):
        option = super().create_option(*args, **kwargs)
        option["attrs"]["class"] = "form-check-input me-2"
        return option


def _champ_specialites() -> forms.ModelMultipleChoiceField:
    return forms.ModelMultipleChoiceField(
        queryset=Specialite.objects.all(), required=False,
        widget=_CasesACocher,
        label=_("Spécialités proposées"),
        help_text=_("Cochez les spécialités que l'hôpital propose (modifiable plus tard)."))


class CreationHopitalForm(forms.ModelForm):
    """Création d'un hôpital client par le propriétaire : l'établissement + son premier administrateur.

    L'administrateur reçoit un e-mail d'invitation (identifiant + lien pour choisir son
    mot de passe) : le propriétaire ne connaît ni ne transmet jamais de mot de passe.
    """

    admin_prenom = forms.CharField(label=_("Prénom de l'administrateur"), max_length=150,
                                   widget=forms.TextInput(attrs=_INPUT))
    admin_nom = forms.CharField(label=_("Nom de l'administrateur"), max_length=150,
                                widget=forms.TextInput(attrs=_INPUT))
    admin_email = forms.EmailField(
        label=_("E-mail de l'administrateur"), widget=forms.EmailInput(attrs=_INPUT),
        help_text=_("L'invitation et le lien de connexion y seront envoyés."))
    admin_username = forms.CharField(label=_("Identifiant de connexion"), max_length=150,
                                     widget=forms.TextInput(attrs=_INPUT))
    specialites = _champ_specialites()

    class Meta:
        model = Etablissement
        fields = ("nom", "plan", "statut", "essai_jusqu_au", "specialites")
        widgets = {
            "nom": forms.TextInput(attrs=_INPUT),
            "plan": forms.Select(attrs=_SELECT),
            "statut": forms.Select(attrs=_SELECT),
            "essai_jusqu_au": forms.DateInput(attrs=_DATE, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["essai_jusqu_au"].help_text = _(
            "Vide en période d'essai = calculée automatiquement (essai de 30 jours).")

    def clean_admin_username(self):
        username = self.cleaned_data["admin_username"].strip()
        if Utilisateur.tous.filter(username__iexact=username).exists():
            raise forms.ValidationError(_("Cet identifiant est déjà utilisé."))
        return username


class EtablissementModifierForm(forms.ModelForm):
    """Modification d'un hôpital existant (nom, plan, statut, fin d'essai, spécialités)."""

    specialites = _champ_specialites()

    class Meta:
        model = Etablissement
        fields = ("nom", "plan", "statut", "essai_jusqu_au", "specialites")
        widgets = {
            "nom": forms.TextInput(attrs=_INPUT),
            "plan": forms.Select(attrs=_SELECT),
            "statut": forms.Select(attrs=_SELECT),
            "essai_jusqu_au": forms.DateInput(attrs=_DATE, format="%Y-%m-%d"),
        }


def _habiller_bootstrap(fields) -> None:
    for champ in fields.values():
        if isinstance(champ.widget, forms.CheckboxInput):
            champ.widget.attrs["class"] = "form-check-input"
        elif isinstance(champ.widget, (forms.Select, forms.SelectMultiple)):
            champ.widget.attrs["class"] = "form-select"
        else:
            champ.widget.attrs["class"] = "form-control"


class UtilisateurCreationForm(CreationPersonnelForm):
    """Création d'un membre du personnel par le propriétaire, sur l'hôpital de son choix.

    Reprend ``CreationPersonnelForm`` (aucun mot de passe saisi, invitation par e-mail) en
    rendu Bootstrap et avec l'établissement obligatoire (l'admin d'hôpital, lui, ne choisit
    pas d'établissement : le sien est déjà implicite).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _habiller_bootstrap(self.fields)
        self.fields["etablissement"].required = True
        self.fields["etablissement"].empty_label = _("— Choisir l'hôpital —")


class UtilisateurModifierForm(forms.ModelForm):
    """Modification d'un compte existant, tous hôpitaux confondus. Le mot de passe ne se
    change pas ici (la personne le choisit elle-même via un lien d'invitation ou de
    réinitialisation)."""

    class Meta:
        model = Utilisateur
        fields = ("username", "first_name", "last_name", "email", "etablissement", "role",
                  "matricule", "telephone", "specialite", "langue_preferee", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _habiller_bootstrap(self.fields)
        self.fields["etablissement"].required = True
        self.fields["etablissement"].empty_label = None

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if Utilisateur.tous.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("Cet identifiant est déjà utilisé."))
        return username


class PlanForm(forms.ModelForm):
    class Meta:
        model = Plan
        fields = ("nom", "code", "prix_mensuel", "max_utilisateurs", "actif")
        widgets = {
            "nom": forms.TextInput(attrs=_INPUT),
            "code": forms.TextInput(attrs=_INPUT),
            "prix_mensuel": forms.NumberInput(attrs={**_INPUT, "min": 0, "step": "1"}),
            "max_utilisateurs": forms.NumberInput(attrs={**_INPUT, "min": 1}),
            "actif": forms.CheckboxInput(attrs=_CHECK),
        }
