from datetime import date

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Medicament

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class MedicamentForm(forms.ModelForm):
    class Meta:
        model = Medicament
        fields = ["denomination", "dosage", "forme", "unite", "seuil_alerte", "code",
                  "actif"]
        widgets = {
            "denomination": forms.TextInput(attrs=_INPUT),
            "dosage": forms.TextInput(attrs=_INPUT),
            "forme": forms.Select(attrs=_SELECT),
            "unite": forms.TextInput(attrs=_INPUT),
            "seuil_alerte": forms.NumberInput(attrs={**_INPUT, "min": 0}),
            "code": forms.TextInput(attrs=_INPUT),
        }


class EntreeStockForm(forms.Form):
    """Réception d'un lot de médicament (CDC 4.5 — entrées de stock)."""

    medicament = forms.ModelChoiceField(
        queryset=Medicament.objects.filter(actif=True), label=_("médicament"),
        widget=forms.Select(attrs=_SELECT),
    )
    numero_lot = forms.CharField(label=_("numéro de lot"), max_length=60,
                                 widget=forms.TextInput(attrs=_INPUT))
    quantite = forms.IntegerField(label=_("quantité reçue"), min_value=1,
                                  widget=forms.NumberInput(attrs=_INPUT))
    date_peremption = forms.DateField(
        label=_("date de péremption"),
        widget=forms.DateInput(attrs={**_INPUT, "type": "date"}),
    )
    date_reception = forms.DateField(
        label=_("date de réception"), initial=date.today, required=False,
        widget=forms.DateInput(attrs={**_INPUT, "type": "date"}),
    )
    fournisseur = forms.CharField(label=_("fournisseur"), max_length=150, required=False,
                                  widget=forms.TextInput(attrs=_INPUT))

    def clean_date_peremption(self):
        d = self.cleaned_data["date_peremption"]
        if d <= date.today():
            raise forms.ValidationError(_("La date de péremption doit être future."))
        return d
