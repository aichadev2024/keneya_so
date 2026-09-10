from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import (
    CompteRenduOperatoire,
    Intervention,
    MembreEquipe,
    SalleOperatoire,
    TypeIntervention,
)

Utilisateur = get_user_model()
_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}

_ROLES_SOIGNANTS = ["MEDECIN", "CHIRURGIEN", "ANESTHESISTE", "IBODE",
                    "AGENT_STERILISATION", "INFIRMIER"]


class DemandeInterventionForm(forms.ModelForm):
    class Meta:
        model = Intervention
        fields = ["type_intervention", "chirurgien_principal", "niveau_urgence",
                  "duree_estimee_min", "motif_operation", "diagnostic_preop",
                  "materiel_specifique", "hospitalisation"]
        widgets = {
            "type_intervention": forms.Select(attrs=_SELECT),
            "chirurgien_principal": forms.Select(attrs=_SELECT),
            "niveau_urgence": forms.Select(attrs=_SELECT),
            "duree_estimee_min": forms.NumberInput(attrs={**_INPUT, "min": 15, "step": 5}),
            "motif_operation": forms.Textarea(attrs={**_INPUT, "rows": 2}),
            "diagnostic_preop": forms.Textarea(attrs={**_INPUT, "rows": 2}),
            "materiel_specifique": forms.Textarea(attrs={**_INPUT, "rows": 2}),
            "hospitalisation": forms.Select(attrs=_SELECT),
        }

    def __init__(self, *args, patient=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["type_intervention"].queryset = TypeIntervention.objects.filter(
            actif=True)
        self.fields["chirurgien_principal"].queryset = Utilisateur.objects.filter(
            is_active=True, role__in=["CHIRURGIEN", "MEDECIN"])
        self.fields["hospitalisation"].required = False
        if patient is not None:
            self.fields["hospitalisation"].queryset = patient.hospitalisations.all()
        else:
            self.fields["hospitalisation"].queryset = \
                self.fields["hospitalisation"].queryset.none()

    def clean(self):
        data = super().clean()
        type_i = data.get("type_intervention")
        if type_i and not data.get("duree_estimee_min"):
            data["duree_estimee_min"] = type_i.duree_standard_min
        return data


class PlanificationForm(forms.Form):
    salle = forms.ModelChoiceField(
        queryset=SalleOperatoire.objects.filter(actif=True, statut="DISPONIBLE"),
        label=_("salle"), widget=forms.Select(attrs=_SELECT))
    date = forms.DateField(label=_("date"),
                           widget=forms.DateInput(attrs={**_INPUT, "type": "date"}))
    heure = forms.TimeField(label=_("heure de début"),
                            widget=forms.TimeInput(attrs={**_INPUT, "type": "time"}))
    duree_estimee_min = forms.IntegerField(
        label=_("durée estimée (minutes)"), min_value=15,
        widget=forms.NumberInput(attrs={**_INPUT, "step": 5}))
    forcer = forms.BooleanField(
        label=_("Forcer (extrême urgence) : reporte les interventions programmées en conflit"),
        required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def debut(self):
        naive = timezone.datetime.combine(self.cleaned_data["date"],
                                          self.cleaned_data["heure"])
        return timezone.make_aware(naive)


class FaisabiliteAnesthesieForm(forms.Form):
    protocole_anesthesie = forms.CharField(
        label=_("protocole d'anesthésie et surveillance peropératoire"),
        widget=forms.Textarea(attrs={**_INPUT, "rows": 3}))
    valide = forms.BooleanField(label=_("Je valide la faisabilité anesthésique"),
                                required=True,
                                widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))


class MembreEquipeForm(forms.Form):
    utilisateur = forms.ModelChoiceField(
        queryset=Utilisateur.objects.none(), label=_("membre"),
        widget=forms.Select(attrs=_SELECT))
    role = forms.ChoiceField(choices=MembreEquipe.Role.choices, label=_("rôle"),
                             widget=forms.Select(attrs=_SELECT))
    forcer = forms.BooleanField(label=_("Ignorer le conflit de planning"), required=False,
                                widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["utilisateur"].queryset = Utilisateur.objects.filter(
            is_active=True, role__in=_ROLES_SOIGNANTS).order_by("last_name", "first_name")


class AnnulationForm(forms.Form):
    motif = forms.CharField(label=_("motif (obligatoire)"),
                            widget=forms.Textarea(attrs={**_INPUT, "rows": 2}))
    reporter = forms.BooleanField(
        label=_("Reporter (déprogrammer) plutôt qu'annuler définitivement"),
        required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))


class IncidentsForm(forms.Form):
    incidents = forms.CharField(
        label=_("incidents / complications peropératoires"), required=False,
        widget=forms.Textarea(attrs={**_INPUT, "rows": 2}))


class CompteRenduForm(forms.ModelForm):
    class Meta:
        model = CompteRenduOperatoire
        fields = ["technique_operatoire", "constatations", "complications",
                  "suites_a_prevoir", "prescription_postoperatoire"]
        widgets = {f: forms.Textarea(attrs={**_INPUT, "rows": 3})
                   for f in ["technique_operatoire", "constatations", "complications",
                             "suites_a_prevoir", "prescription_postoperatoire"]}


class ChecklistValidationForm(forms.Form):
    commentaire = forms.CharField(label=_("réserves éventuelles"), required=False,
                                  widget=forms.TextInput(attrs=_INPUT))
