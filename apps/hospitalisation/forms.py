from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Hospitalisation, Lit, NoteSuivi, Service

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


def _lits_disponibles_qs():
    """Lits libres : statut disponible ET aucun séjour en cours."""
    return (
        Lit.objects.filter(statut=Lit.Statut.DISPONIBLE)
        .exclude(hospitalisations__statut=Hospitalisation.Statut.EN_COURS)
        .select_related("chambre__service")
    )


class AdmissionForm(forms.Form):
    service = forms.ModelChoiceField(
        queryset=Service.objects.filter(actif=True), label=_("service"),
        widget=forms.Select(attrs=_SELECT))
    lit = forms.ModelChoiceField(
        queryset=_lits_disponibles_qs(), label=_("lit"), required=False,
        widget=forms.Select(attrs=_SELECT),
        help_text=_("Laisser vide pour une admission sans lit assigné."))
    motif = forms.CharField(label=_("motif d'hospitalisation"), max_length=255,
                            widget=forms.TextInput(attrs=_INPUT))
    diagnostic_admission = forms.CharField(
        label=_("diagnostic à l'admission"), required=False,
        widget=forms.Textarea(attrs={**_INPUT, "rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lit"].queryset = _lits_disponibles_qs()
        self.fields["lit"].label_from_instance = lambda o: str(o)

    def clean(self):
        data = super().clean()
        service, lit = data.get("service"), data.get("lit")
        if lit and service and lit.chambre.service_id != service.pk:
            self.add_error("lit", _("Ce lit n'appartient pas au service choisi."))
        if lit and lit.est_occupe:
            self.add_error("lit", _("Ce lit est déjà occupé."))
        return data


class TransfertForm(forms.Form):
    nouveau_lit = forms.ModelChoiceField(
        queryset=_lits_disponibles_qs(), label=_("nouveau lit"),
        widget=forms.Select(attrs=_SELECT))
    motif = forms.CharField(label=_("motif"), max_length=255, required=False,
                            widget=forms.TextInput(attrs=_INPUT))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nouveau_lit"].queryset = _lits_disponibles_qs()


class SortieForm(forms.Form):
    mode_sortie = forms.ChoiceField(
        choices=Hospitalisation.ModeSortie.choices, label=_("mode de sortie"),
        widget=forms.Select(attrs=_SELECT))
    compte_rendu = forms.CharField(
        label=_("compte-rendu d'hospitalisation"),
        widget=forms.Textarea(attrs={**_INPUT, "rows": 4}))
    consignes_sortie = forms.CharField(
        label=_("consignes de sortie"), required=False,
        widget=forms.Textarea(attrs={**_INPUT, "rows": 3}))


class NoteSuiviForm(forms.ModelForm):
    class Meta:
        model = NoteSuivi
        fields = ["type", "description", "temperature_c", "tension_systolique",
                  "tension_diastolique", "pouls"]
        widgets = {
            "type": forms.Select(attrs=_SELECT),
            "description": forms.Textarea(attrs={**_INPUT, "rows": 2}),
            "temperature_c": forms.NumberInput(attrs={**_INPUT, "step": "0.1"}),
            "tension_systolique": forms.NumberInput(attrs=_INPUT),
            "tension_diastolique": forms.NumberInput(attrs=_INPUT),
            "pouls": forms.NumberInput(attrs=_INPUT),
        }
