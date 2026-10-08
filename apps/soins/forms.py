from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Soin

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class SoinForm(forms.ModelForm):
    class Meta:
        model = Soin
        fields = ["type_soin", "description", "observations", "date_soin",
                  "hospitalisation", "intervention"]
        widgets = {
            "type_soin": forms.Select(attrs=_SELECT),
            "description": forms.Textarea(attrs={**_INPUT, "rows": 3}),
            "observations": forms.Textarea(attrs={**_INPUT, "rows": 2}),
            "date_soin": forms.DateTimeInput(attrs={**_INPUT, "type": "datetime-local"},
                                             format="%Y-%m-%dT%H:%M"),
            "hospitalisation": forms.Select(attrs=_SELECT),
            "intervention": forms.Select(attrs=_SELECT),
        }

    def __init__(self, *args, patient=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["date_soin"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]
        for nom in ("hospitalisation", "intervention"):
            self.fields[nom].required = False
        if patient is not None:
            self.fields["hospitalisation"].queryset = patient.hospitalisations.all()
            self.fields["intervention"].queryset = patient.interventions.all()
            self.fields["hospitalisation"].empty_label = _("— Soin ambulatoire —")
            self.fields["intervention"].empty_label = _("— Aucune —")
        else:
            self.fields["hospitalisation"].queryset = \
                self.fields["hospitalisation"].queryset.none()
            self.fields["intervention"].queryset = self.fields["intervention"].queryset.none()
