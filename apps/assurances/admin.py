from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Assurance,
    BordereauAssurance,
    ContratAssurance,
    LigneBordereau,
    PatientAssure,
)


class ContratInline(admin.TabularInline):
    model = ContratAssurance
    extra = 0


@admin.register(Assurance)
class AssuranceAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "type", "contact_telephone", "actif")
    list_filter = ("type", "actif")
    search_fields = ("nom", "code")
    inlines = [ContratInline]


@admin.register(ContratAssurance)
class ContratAssuranceAdmin(admin.ModelAdmin):
    list_display = ("assurance", "libelle", "taux_prise_en_charge", "plafond_annuel",
                    "actif")
    list_filter = ("assurance", "actif")
    search_fields = ("libelle", "assurance__nom")


@admin.register(PatientAssure)
class PatientAssureAdmin(admin.ModelAdmin):
    list_display = ("patient", "contrat", "numero_adherent", "taux_effectif",
                    "date_debut", "date_fin", "actif")
    list_filter = ("actif", "contrat__assurance")
    search_fields = ("patient__nom", "patient__numero_dossier", "numero_adherent")
    autocomplete_fields = ("patient",)

    @admin.display(description=_("taux effectif"))
    def taux_effectif(self, obj):
        return f"{obj.taux_effectif} %"


class LigneBordereauInline(admin.TabularInline):
    model = LigneBordereau
    extra = 0
    readonly_fields = ("facture", "montant_assurance")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(BordereauAssurance)
class BordereauAssuranceAdmin(admin.ModelAdmin):
    list_display = ("reference", "assurance", "periode_debut", "periode_fin", "statut",
                    "montant_total")
    list_filter = ("statut", "assurance")
    search_fields = ("reference",)
    readonly_fields = ("reference", "montant_total", "date_generation")
    inlines = [LigneBordereauInline]
