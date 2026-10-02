import os

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Categorie, Resultat, TypeExamen

_INPUT = {"class": "form-control"}
_SELECT = {"class": "form-select"}


class ImportTypeExamenForm(forms.Form):
    fichier = forms.FileField(
        label=_("fichier Excel (.xlsx)"),
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".xlsx"}),
    )

    def clean_fichier(self):
        f = self.cleaned_data["fichier"]
        if not f.name.lower().endswith(".xlsx"):
            raise forms.ValidationError(_("Le fichier doit être au format Excel (.xlsx)."))
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError(_("Fichier trop volumineux (5 Mo maximum)."))
        return f

# Pièces jointes de résultats (CDC 4.6) : whitelist d'extensions, taille plafonnée
# et vérification de la signature binaire réelle du fichier (pas seulement son nom),
# pour empêcher l'upload d'un fichier exécutable/HTML déguisé en PDF ou image.
_TAILLE_MAX_FICHIER = 10 * 1024 * 1024  # 10 Mo
_SIGNATURES_AUTORISEES = {
    ".pdf": (b"%PDF-",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}


def _valider_piece_jointe(fichier):
    ext = os.path.splitext(fichier.name)[1].lower()
    signatures = _SIGNATURES_AUTORISEES.get(ext)
    if signatures is None:
        raise forms.ValidationError(
            _("Format de fichier non autorisé (formats acceptés : PDF, JPG, PNG)."))
    if fichier.size > _TAILLE_MAX_FICHIER:
        raise forms.ValidationError(
            _("Le fichier dépasse la taille maximale autorisée (10 Mo)."))
    entete = fichier.read(8)
    fichier.seek(0)
    if not any(entete.startswith(sig) for sig in signatures):
        raise forms.ValidationError(
            _("Le contenu du fichier ne correspond pas à son extension."))
    return fichier


class TypeExamenForm(forms.ModelForm):
    """Ajout d'une analyse / d'un examen au référentiel de l'établissement."""

    class Meta:
        model = TypeExamen
        fields = ["code", "libelle", "categorie", "unite", "valeurs_reference",
                  "delai_rendu_heures"]
        widgets = {
            "code": forms.TextInput(attrs=_INPUT),
            "libelle": forms.TextInput(attrs=_INPUT),
            "categorie": forms.Select(attrs=_SELECT),
            "unite": forms.TextInput(attrs=_INPUT),
            "valeurs_reference": forms.TextInput(attrs=_INPUT),
            "delai_rendu_heures": forms.NumberInput(attrs={**_INPUT, "min": 1}),
        }

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        # L'établissement n'est pas un champ du formulaire : l'unicité du code est
        # donc vérifiée ici (le TypeExamen.objects est déjà filtré par établissement).
        if TypeExamen.objects.filter(code=code).exists():
            raise forms.ValidationError(_("Ce code existe déjà."))
        return code


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
    valeur = forms.CharField(label=_("valeur mesurée"), max_length=120, required=False,
                             widget=forms.TextInput(attrs=_INPUT))
    interpretation = forms.ChoiceField(
        label=_("interprétation"), required=False,
        choices=[("", _("— automatique —"))] + list(Resultat.Interpretation.choices),
        widget=forms.Select(attrs=_SELECT))
    commentaire = forms.CharField(label=_("commentaire"), max_length=255, required=False,
                                  widget=forms.TextInput(attrs=_INPUT))
    fichier = forms.FileField(label=_("pièce jointe (image / PDF)"), required=False,
                              widget=forms.ClearableFileInput(attrs={"class": "form-control"}))

    def clean_fichier(self):
        fichier = self.cleaned_data.get("fichier")
        if fichier:
            _valider_piece_jointe(fichier)
        return fichier

    def clean(self):
        data = super().clean()
        if not data.get("valeur") and not data.get("fichier"):
            self.add_error("valeur", _("Saisissez une valeur ou joignez un fichier."))
        return data


class ResultatImagerieForm(forms.Form):
    compte_rendu = forms.CharField(label=_("compte-rendu"),
                                   widget=forms.Textarea(attrs={**_INPUT, "rows": 4}))
    conclusion = forms.CharField(label=_("conclusion"), required=False,
                                 widget=forms.Textarea(attrs={**_INPUT, "rows": 2}))
    fichier = forms.FileField(label=_("pièce jointe (image / PDF)"), required=False,
                              widget=forms.ClearableFileInput(attrs={"class": "form-control"}))
    commentaire = forms.CharField(label=_("commentaire"), max_length=255, required=False,
                                  widget=forms.TextInput(attrs=_INPUT))

    def clean_fichier(self):
        fichier = self.cleaned_data.get("fichier")
        if fichier:
            _valider_piece_jointe(fichier)
        return fichier


class AnnulationDemandeForm(forms.Form):
    motif = forms.CharField(label=_("motif d'annulation"), max_length=255,
                            widget=forms.TextInput(attrs=_INPUT))
