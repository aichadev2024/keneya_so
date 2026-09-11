from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Categorie, Resultat, TypeExamen

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class DemandeExamenForm(forms.Form):
    categorie = forms.ChoiceField(label=_("catégorie"), choices=Categorie.choices,
                                  widget=forms.Select(attrs=_SELECT))
    priorite = forms.ChoiceField(
        label=_("priorité"),
        choices=[("ROUTINE", _("Routine")), ("URGENT", _("Urgent"))],
        widget=forms.Select(attrs=_SELECT))
    renseignements_cliniques = forms.CharField(
        label=_("renseignements cliniques"), required=False,
        widget=forms.Textarea(attrs={**_INPUT, "rows": 2}))
    types_examens = forms.ModelMultipleChoiceField(
        label=_("examens demandés"),
        queryset=TypeExamen.objects.filter(actif=True),
        widget=forms.CheckboxSelectMultiple)

    def clean(self):
        data = super().clean()
        categorie = data.get("categorie")
        types = data.get("types_examens")
        if categorie and types:
            hors = [t.libelle for t in types if t.categorie != categorie]
            if hors:
                self.add_error("types_examens",
                               _("Ces examens ne correspondent pas à la catégorie : %(l)s")
                               % {"l": ", ".join(hors)})
        return data


class ResultatBiologieForm(forms.Form):
    valeur = forms.CharField(label=_("valeur mesurée"), max_length=120,
                             widget=forms.TextInput(attrs=_INPUT))
    interpretation = forms.ChoiceField(
        label=_("interprétation"), required=False,
        choices=[("", _("— automatique —"))] + list(Resultat.Interpretation.choices),
        widget=forms.Select(attrs=_SELECT))
    commentaire = forms.CharField(label=_("commentaire"), max_length=255, required=False,
                                  widget=forms.TextInput(attrs=_INPUT))


class ResultatImagerieForm(forms.Form):
    compte_rendu = forms.CharField(label=_("compte-rendu"),
                                   widget=forms.Textarea(attrs={**_INPUT, "rows": 4}))
    conclusion = forms.CharField(label=_("conclusion"), required=False,
                                 widget=forms.Textarea(attrs={**_INPUT, "rows": 2}))
    fichier = forms.FileField(label=_("pièce jointe (image / PDF)"), required=False,
                              widget=forms.ClearableFileInput(attrs={"class": "form-control"}))
    commentaire = forms.CharField(label=_("commentaire"), max_length=255, required=False,
                                  widget=forms.TextInput(attrs=_INPUT))


class AnnulationDemandeForm(forms.Form):
    motif = forms.CharField(label=_("motif d'annulation"), max_length=255,
                            widget=forms.TextInput(attrs=_INPUT))
