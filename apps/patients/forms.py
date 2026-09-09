from django import forms

from .models import DossierMedical, Patient

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            "nom", "prenom", "sexe", "date_naissance", "date_naissance_estimee",
            "lieu_naissance", "nationalite", "telephone", "adresse", "ville",
            "personne_a_prevenir", "lien_personne_a_prevenir", "telephone_urgence",
            "profession", "statut_matrimonial", "groupe_sanguin", "photo", "actif",
        ]
        widgets = {
            "nom": forms.TextInput(attrs=_INPUT),
            "prenom": forms.TextInput(attrs=_INPUT),
            "sexe": forms.Select(attrs=_SELECT),
            "date_naissance": forms.DateInput(attrs={**_INPUT, "type": "date"}),
            "lieu_naissance": forms.TextInput(attrs=_INPUT),
            "nationalite": forms.TextInput(attrs=_INPUT),
            "telephone": forms.TextInput(attrs=_INPUT),
            "adresse": forms.TextInput(attrs=_INPUT),
            "ville": forms.TextInput(attrs=_INPUT),
            "personne_a_prevenir": forms.TextInput(attrs=_INPUT),
            "lien_personne_a_prevenir": forms.TextInput(attrs=_INPUT),
            "telephone_urgence": forms.TextInput(attrs=_INPUT),
            "profession": forms.TextInput(attrs=_INPUT),
            "statut_matrimonial": forms.Select(attrs=_SELECT),
            "groupe_sanguin": forms.Select(attrs=_SELECT),
        }


class DossierMedicalForm(forms.ModelForm):
    class Meta:
        model = DossierMedical
        fields = [
            "antecedents_medicaux", "antecedents_chirurgicaux", "antecedents_familiaux",
            "antecedents_gyneco_obstetricaux", "traitements_en_cours", "habitudes_vie",
            "observations",
        ]
        widgets = {
            f: forms.Textarea(attrs={**_INPUT, "rows": 3})
            for f in fields
        }
