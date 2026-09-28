from django.contrib import admin

from .models import ConsultationPrenatale, DossierGrossesse


class ConsultationPrenataleInline(admin.TabularInline):
    model = ConsultationPrenatale
    extra = 0
    can_delete = False
    fields = ("numero", "terme_sa", "consultation", "prochain_rdv")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DossierGrossesse)
class DossierGrossesseAdmin(admin.ModelAdmin):
    list_display = ("reference", "patient", "date_dernieres_regles", "statut", "prochain_rdv",
                    "sage_femme")
    list_filter = ("statut",)
    search_fields = ("reference", "patient__nom", "patient__prenom", "patient__numero_dossier")
    autocomplete_fields = ("patient",)
    readonly_fields = ("reference", "prochain_rdv", "cree_le", "modifie_le")
    inlines = [ConsultationPrenataleInline]
