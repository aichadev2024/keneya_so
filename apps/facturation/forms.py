from django import forms
from django.utils.translation import gettext_lazy as _

from .models import LigneFacture, Paiement, Relance

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class PaiementForm(forms.Form):
    montant = forms.DecimalField(label=_("montant (FCFA)"), min_value=1, max_digits=12,
                                 decimal_places=2,
                                 widget=forms.NumberInput(attrs=_INPUT))
    mode = forms.ChoiceField(label=_("mode"), choices=Paiement.Mode.choices,
                             widget=forms.Select(attrs=_SELECT))
    payeur = forms.ChoiceField(label=_("payeur"), choices=Paiement.Payeur.choices,
                               initial=Paiement.Payeur.PATIENT,
                               widget=forms.Select(attrs=_SELECT))
    est_remboursement = forms.BooleanField(
        label=_("Remboursement (sortie de caisse)"), required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    reference_transaction = forms.CharField(label=_("réf. transaction"), max_length=80,
                                            required=False,
                                            widget=forms.TextInput(attrs=_INPUT))
    commentaire = forms.CharField(label=_("commentaire"), max_length=255, required=False,
                                  widget=forms.TextInput(attrs=_INPUT))


class LigneFactureForm(forms.ModelForm):
    class Meta:
        model = LigneFacture
        fields = ["type_source", "libelle", "quantite", "prix_unitaire"]
        widgets = {
            "type_source": forms.Select(attrs=_SELECT),
            "libelle": forms.TextInput(attrs=_INPUT),
            "quantite": forms.NumberInput(attrs={**_INPUT, "step": "0.01"}),
            "prix_unitaire": forms.NumberInput(attrs={**_INPUT, "step": "0.01"}),
        }


class RelanceForm(forms.ModelForm):
    class Meta:
        model = Relance
        fields = ["canal", "commentaire"]
        widgets = {
            "canal": forms.Select(attrs=_SELECT),
            "commentaire": forms.TextInput(attrs=_INPUT),
        }


class AnnulationFactureForm(forms.Form):
    motif = forms.CharField(label=_("motif d'annulation"), max_length=255,
                            widget=forms.TextInput(attrs=_INPUT))
