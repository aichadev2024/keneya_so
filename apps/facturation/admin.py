from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Facture, LigneFacture, Paiement, Relance, Tarif


@admin.register(Tarif)
class TarifAdmin(admin.ModelAdmin):
    list_display = ("libelle", "categorie", "montant", "reference_externe", "actif")
    list_filter = ("categorie", "actif")
    search_fields = ("code", "libelle")


class LigneFactureInline(admin.TabularInline):
    model = LigneFacture
    extra = 0
    readonly_fields = ("montant",)


class PaiementInline(admin.TabularInline):
    model = Paiement
    extra = 0
    readonly_fields = ("reference", "date_paiement", "encaisse_par")


class RelanceInline(admin.TabularInline):
    model = Relance
    extra = 0
    readonly_fields = ("date_relance", "par")


@admin.register(Facture)
class FactureAdmin(admin.ModelAdmin):
    list_display = ("reference", "patient", "date_emission", "statut", "montant_total",
                    "part_patient", "part_assurance", "en_retard")
    list_filter = ("statut", "date_emission")
    search_fields = ("reference", "patient__nom", "patient__numero_dossier")
    date_hierarchy = "date_emission"
    autocomplete_fields = ("patient",)
    readonly_fields = ("reference", "montant_total", "part_patient", "part_assurance",
                       "taux_couverture_applique", "cree_le", "modifie_le")
    inlines = [LigneFactureInline, PaiementInline, RelanceInline]

    @admin.display(boolean=True, description=_("en retard"))
    def en_retard(self, obj):
        return obj.en_retard


@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ("reference", "facture", "montant", "mode", "payeur",
                    "est_remboursement", "date_paiement")
    list_filter = ("mode", "payeur", "est_remboursement", "date_paiement")
    search_fields = ("reference", "facture__reference")
