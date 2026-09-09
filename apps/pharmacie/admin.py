from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    Dispensation,
    InteractionMedicamenteuse,
    LigneDispensation,
    LotMedicament,
    Medicament,
    MouvementStock,
)


class LotInline(admin.TabularInline):
    model = LotMedicament
    extra = 0
    fields = ("numero_lot", "quantite", "quantite_initiale", "date_peremption",
              "date_reception", "fournisseur")


@admin.register(Medicament)
class MedicamentAdmin(admin.ModelAdmin):
    list_display = ("denomination", "dosage", "forme", "quantite_utilisable",
                    "seuil_alerte", "en_alerte", "actif")
    list_filter = ("forme", "actif")
    search_fields = ("denomination", "code", "dosage")
    inlines = [LotInline]

    @admin.display(boolean=True, description=_("sous le seuil"))
    def en_alerte(self, obj):
        return obj.en_alerte


@admin.register(LotMedicament)
class LotMedicamentAdmin(admin.ModelAdmin):
    list_display = ("medicament", "numero_lot", "quantite", "date_peremption",
                    "est_perime", "fournisseur")
    list_filter = ("date_peremption", "fournisseur")
    search_fields = ("medicament__denomination", "numero_lot")

    @admin.display(boolean=True, description=_("périmé"))
    def est_perime(self, obj):
        return obj.est_perime


@admin.register(MouvementStock)
class MouvementStockAdmin(admin.ModelAdmin):
    list_display = ("cree_le", "medicament", "type", "quantite_signee", "utilisateur",
                    "motif")
    list_filter = ("type", "cree_le")
    search_fields = ("medicament__denomination", "motif", "reference")
    date_hierarchy = "cree_le"
    readonly_fields = ("medicament", "lot", "type", "quantite", "motif", "reference",
                       "utilisateur", "cree_le")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description=_("quantité"))
    def quantite_signee(self, obj):
        return obj.quantite_signee


@admin.register(InteractionMedicamenteuse)
class InteractionMedicamenteuseAdmin(admin.ModelAdmin):
    list_display = ("medicament_a", "medicament_b", "gravite")
    list_filter = ("gravite",)
    search_fields = ("medicament_a__denomination", "medicament_b__denomination")
    autocomplete_fields = ("medicament_a", "medicament_b")


class LigneDispensationInline(admin.TabularInline):
    model = LigneDispensation
    extra = 0
    readonly_fields = ("ligne_ordonnance", "medicament", "lot", "quantite_dispensee",
                       "cree_le")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Dispensation)
class DispensationAdmin(admin.ModelAdmin):
    list_display = ("ordonnance", "statut", "pharmacien", "date_delivrance")
    list_filter = ("statut",)
    search_fields = ("ordonnance__reference",)
    readonly_fields = ("ordonnance", "cree_le", "modifie_le")
    inlines = [LigneDispensationInline]
