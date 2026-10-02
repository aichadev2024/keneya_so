from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.models import Specialite

from .models import Constantes, Consultation, LigneOrdonnance, Ordonnance

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class ConsultationForm(forms.ModelForm):
    class Meta:
        model = Consultation
        fields = ["specialite", "motif", "histoire_maladie", "examen_clinique", "diagnostic",
                  "conduite_a_tenir", "statut"]
        widgets = {
            "motif": forms.TextInput(attrs=_INPUT),
            "histoire_maladie": forms.Textarea(attrs={**_INPUT, "rows": 3}),
            "examen_clinique": forms.Textarea(attrs={**_INPUT, "rows": 3}),
            "diagnostic": forms.Textarea(attrs={**_INPUT, "rows": 2}),
            "conduite_a_tenir": forms.Textarea(attrs={**_INPUT, "rows": 2}),
            "statut": forms.Select(attrs=_SELECT),
            "specialite": forms.Select(attrs=_SELECT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Seules les spécialités de l'hôpital sont proposées ; le champ disparaît si
        # l'hôpital n'en a déclaré aucune.
        disponibles = Specialite.de_l_etablissement_courant()
        if disponibles.exists():
            self.fields["specialite"].queryset = disponibles
            self.fields["specialite"].empty_label = _("— Médecine générale —")
        else:
            del self.fields["specialite"]


class ConstantesForm(forms.ModelForm):
    class Meta:
        model = Constantes
        fields = ["poids_kg", "taille_cm", "temperature_c", "tension_systolique",
                  "tension_diastolique", "frequence_cardiaque", "frequence_respiratoire",
                  "saturation_o2", "glycemie_g_l"]
        widgets = {f: forms.NumberInput(attrs={**_INPUT, "step": "any"}) for f in fields}


class OrdonnanceForm(forms.ModelForm):
    class Meta:
        model = Ordonnance
        fields = ["notes"]
        widgets = {"notes": forms.Textarea(attrs={**_INPUT, "rows": 2})}


class LigneOrdonnanceForm(forms.ModelForm):
    class Meta:
        model = LigneOrdonnance
        fields = ["medicament", "posologie", "duree_jours", "quantite_prescrite",
                  "instructions"]
        widgets = {
            "medicament": forms.Select(attrs=_SELECT),
            "posologie": forms.TextInput(attrs={**_INPUT,
                                                "placeholder": "1 comprimé matin et soir"}),
            "duree_jours": forms.NumberInput(attrs={**_INPUT, "min": 1}),
            "quantite_prescrite": forms.NumberInput(attrs={**_INPUT, "min": 1}),
            "instructions": forms.TextInput(attrs=_INPUT),
        }

    def __init__(self, *args, utilisateur=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.pharmacie.models import Medicament

        from .services import medicaments_prescriptibles
        self.fields["medicament"].queryset = medicaments_prescriptibles(
            utilisateur, Medicament.objects.filter(actif=True))
