from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Constantes, Consultation, LigneOrdonnance, Ordonnance


class ConstantesInline(admin.StackedInline):
    model = Constantes
    extra = 0
    can_delete = False


class LigneOrdonnanceInline(admin.TabularInline):
    model = LigneOrdonnance
    extra = 1
    autocomplete_fields = ("medicament",)
    fields = ("medicament", "posologie", "duree_jours", "quantite_prescrite",
              "instructions")


@admin.register(Consultation)
class ConsultationAdmin(admin.ModelAdmin):
    list_display = ("reference", "patient", "praticien", "date_consultation", "statut")
    list_filter = ("statut", "date_consultation")
    search_fields = ("reference", "patient__nom", "patient__prenom",
                     "patient__numero_dossier", "motif")
    date_hierarchy = "date_consultation"
    autocomplete_fields = ("patient",)
    readonly_fields = ("reference", "cree_le", "modifie_le")
    inlines = [ConstantesInline]

    def save_model(self, request, obj, form, change):
        if not change and not obj.praticien_id:
            obj.praticien = request.user
        super().save_model(request, obj, form, change)


@admin.register(Ordonnance)
class OrdonnanceAdmin(admin.ModelAdmin):
    list_display = ("reference", "patient", "prescripteur", "statut",
                    "date_prescription", "date_transmission")
    list_filter = ("statut", "date_prescription")
    search_fields = ("reference", "consultation__patient__nom",
                     "consultation__patient__numero_dossier")
    readonly_fields = ("reference", "date_transmission", "cree_le", "modifie_le")
    inlines = [LigneOrdonnanceInline]

    @admin.display(description=_("patient"))
    def patient(self, obj):
        return obj.patient
