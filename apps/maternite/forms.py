from datetime import timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import ConsultationPrenatale, DossierGrossesse

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}
_DATE = {"class": "form-control", "type": "date"}
_CHECK = {"class": "form-check-input"}

# Au-delà, la date des dernières règles saisie n'est plus plausible pour une grossesse en cours.
MAX_JOURS_GROSSESSE_EN_COURS = 300


class DossierGrossesseForm(forms.ModelForm):
    class Meta:
        model = DossierGrossesse
        fields = ["date_dernieres_regles", "gestite", "parite", "antecedents", "facteurs_risque"]
        widgets = {
            "date_dernieres_regles": forms.DateInput(attrs=_DATE, format="%Y-%m-%d"),
            "gestite": forms.NumberInput(attrs={**_INPUT, "min": 1}),
            "parite": forms.NumberInput(attrs={**_INPUT, "min": 0}),
            "antecedents": forms.Textarea(attrs={**_INPUT, "rows": 3}),
            "facteurs_risque": forms.Textarea(attrs={**_INPUT, "rows": 2}),
        }

    def clean_date_dernieres_regles(self):
        ddr = self.cleaned_data["date_dernieres_regles"]
        aujourdhui = timezone.localdate()
        if ddr > aujourdhui:
            raise ValidationError(_("La date des dernières règles ne peut pas être dans le futur."))
        if (aujourdhui - ddr).days > MAX_JOURS_GROSSESSE_EN_COURS and (
                not self.instance.pk or self.instance.statut == DossierGrossesse.Statut.EN_COURS):
            raise ValidationError(_("Cette date est trop ancienne pour une grossesse en cours (plus de 43 semaines)."))
        return ddr

    def clean(self):
        data = super().clean()
        gestite, parite = data.get("gestite"), data.get("parite")
        if gestite is not None and parite is not None and parite >= gestite:
            self.add_error("parite", _("La parité doit être inférieure à la gestité (la grossesse actuelle compte dans la gestité)."))
        return data


class TerminerGrossesseForm(forms.ModelForm):
    class Meta:
        model = DossierGrossesse
        fields = ["statut", "date_fin", "issue"]
        widgets = {
            "statut": forms.Select(attrs=_SELECT),
            "date_fin": forms.DateInput(attrs=_DATE, format="%Y-%m-%d"),
            "issue": forms.Textarea(attrs={**_INPUT, "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["statut"].choices = [
            (v, l) for v, l in DossierGrossesse.Statut.choices
            if v != DossierGrossesse.Statut.EN_COURS]
        self.fields["date_fin"].required = True
        self.fields["date_fin"].initial = timezone.localdate()

    def clean_date_fin(self):
        fin = self.cleaned_data["date_fin"]
        if fin > timezone.localdate():
            raise ValidationError(_("La date de fin ne peut pas être dans le futur."))
        if fin < self.instance.date_dernieres_regles:
            raise ValidationError(_("La date de fin ne peut pas précéder les dernières règles."))
        return fin


class VisitePrenataleForm(forms.ModelForm):
    """Une visite prénatale ; poids, tension et température alimentent les constantes de la consultation."""

    poids_kg = forms.DecimalField(label=_("poids (kg)"), required=False, min_value=20,
                                  max_value=250, decimal_places=2, max_digits=5,
                                  widget=forms.NumberInput(attrs={**_INPUT, "step": "0.1"}))
    tension_systolique = forms.IntegerField(label=_("TA systolique (mmHg)"), required=False,
                                            min_value=50, max_value=300,
                                            widget=forms.NumberInput(attrs=_INPUT))
    tension_diastolique = forms.IntegerField(label=_("TA diastolique (mmHg)"), required=False,
                                             min_value=30, max_value=200,
                                             widget=forms.NumberInput(attrs=_INPUT))
    temperature_c = forms.DecimalField(label=_("température (°C)"), required=False,
                                       min_value=30, max_value=45, decimal_places=1,
                                       max_digits=4,
                                       widget=forms.NumberInput(attrs={**_INPUT, "step": "0.1"}))

    class Meta:
        model = ConsultationPrenatale
        fields = ["hauteur_uterine_cm", "bruits_coeur_foetal", "frequence_bcf", "presentation",
                  "oedemes", "albuminurie", "glycosurie", "hemoglobine_g_dl", "depistage_vih",
                  "depistage_syphilis", "tpi_sp_donne", "fer_acide_folique_donne", "vat_donne",
                  "moustiquaire_remise", "observations", "prochain_rdv"]
        widgets = {
            "hauteur_uterine_cm": forms.NumberInput(attrs={**_INPUT, "step": "0.5", "min": 0}),
            "bruits_coeur_foetal": forms.Select(attrs=_SELECT),
            "frequence_bcf": forms.NumberInput(attrs={**_INPUT, "min": 0, "max": 300}),
            "presentation": forms.Select(attrs=_SELECT),
            "oedemes": forms.CheckboxInput(attrs=_CHECK),
            "albuminurie": forms.Select(attrs=_SELECT),
            "glycosurie": forms.Select(attrs=_SELECT),
            "hemoglobine_g_dl": forms.NumberInput(attrs={**_INPUT, "step": "0.1", "min": 0}),
            "depistage_vih": forms.Select(attrs=_SELECT),
            "depistage_syphilis": forms.Select(attrs=_SELECT),
            "tpi_sp_donne": forms.CheckboxInput(attrs=_CHECK),
            "fer_acide_folique_donne": forms.CheckboxInput(attrs=_CHECK),
            "vat_donne": forms.CheckboxInput(attrs=_CHECK),
            "moustiquaire_remise": forms.CheckboxInput(attrs=_CHECK),
            "observations": forms.Textarea(attrs={**_INPUT, "rows": 3}),
            "prochain_rdv": forms.DateInput(attrs=_DATE, format="%Y-%m-%d"),
        }

    CHAMPS_CONSTANTES = ("poids_kg", "tension_systolique", "tension_diastolique", "temperature_c")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        constantes = self.instance.constantes if self.instance.pk else None
        if constantes:
            for champ in self.CHAMPS_CONSTANTES:
                self.fields[champ].initial = getattr(constantes, champ)

    def clean_prochain_rdv(self):
        rdv = self.cleaned_data.get("prochain_rdv")
        if rdv and rdv < timezone.localdate():
            raise ValidationError(_("Le prochain rendez-vous ne peut pas être dans le passé."))
        if rdv and rdv > timezone.localdate() + timedelta(days=120):
            raise ValidationError(_("Le prochain rendez-vous est trop éloigné (plus de 4 mois)."))
        return rdv

    def clean(self):
        data = super().clean()
        s, d = data.get("tension_systolique"), data.get("tension_diastolique")
        if s and d and d >= s:
            self.add_error("tension_diastolique", _("La tension diastolique doit être inférieure à la systolique."))
        return data
