from django import forms
from django.utils.translation import gettext_lazy as _

from .models import ContratAssurance, PatientAssure

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class PatientAssureForm(forms.ModelForm):
    class Meta:
        model = PatientAssure
        fields = ["contrat", "numero_adherent", "taux_prise_en_charge", "plafond_annuel",
                  "date_debut", "date_fin", "actif"]
        widgets = {
            "contrat": forms.Select(attrs=_SELECT),
            "numero_adherent": forms.TextInput(attrs=_INPUT),
            "taux_prise_en_charge": forms.NumberInput(attrs={**_INPUT, "step": "0.01"}),
            "plafond_annuel": forms.NumberInput(attrs={**_INPUT, "step": "0.01"}),
            "date_debut": forms.DateInput(attrs={**_INPUT, "type": "date"}),
            "date_fin": forms.DateInput(attrs={**_INPUT, "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contrat"].queryset = ContratAssurance.objects.filter(
            actif=True).select_related("assurance")


class GenererBordereauForm(forms.Form):
    periode_debut = forms.DateField(label=_("début de période"),
                                    widget=forms.DateInput(attrs={**_INPUT, "type": "date"}))
    periode_fin = forms.DateField(label=_("fin de période"),
                                  widget=forms.DateInput(attrs={**_INPUT, "type": "date"}))
