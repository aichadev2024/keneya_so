from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Chambre, Hospitalisation, Lit, MouvementLit, NoteSuivi, Service


class ChambreInline(admin.TabularInline):
    model = Chambre
    extra = 0


class LitInline(admin.TabularInline):
    model = Lit
    extra = 0


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "nb_lits", "nb_lits_occupes", "taux_occupation", "actif")
    search_fields = ("nom", "code")
    inlines = [ChambreInline]

    @admin.display(description=_("taux d'occupation"))
    def taux_occupation(self, obj):
        return f"{obj.taux_occupation} %"


@admin.register(Chambre)
class ChambreAdmin(admin.ModelAdmin):
    list_display = ("service", "numero", "type")
    list_filter = ("service", "type")
    search_fields = ("numero",)
    inlines = [LitInline]


@admin.register(Lit)
class LitAdmin(admin.ModelAdmin):
    list_display = ("__str__", "statut", "est_occupe")
    list_filter = ("statut", "chambre__service")
    search_fields = ("numero", "chambre__numero")

    @admin.display(boolean=True, description=_("occupé"))
    def est_occupe(self, obj):
        return obj.est_occupe


class NoteSuiviInline(admin.TabularInline):
    model = NoteSuivi
    extra = 0
    fields = ("date_note", "type", "description", "auteur")
    readonly_fields = ("date_note", "auteur")


class MouvementLitInline(admin.TabularInline):
    model = MouvementLit
    extra = 0
    readonly_fields = ("lit_precedent", "lit_nouveau", "motif", "date", "par")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Hospitalisation)
class HospitalisationAdmin(admin.ModelAdmin):
    list_display = ("reference", "patient", "service", "lit", "statut", "date_admission",
                    "date_sortie")
    list_filter = ("statut", "service", "mode_sortie")
    search_fields = ("reference", "patient__nom", "patient__numero_dossier")
    date_hierarchy = "date_admission"
    autocomplete_fields = ("patient",)
    readonly_fields = ("reference", "cree_le", "modifie_le")
    inlines = [NoteSuiviInline, MouvementLitInline]


@admin.register(NoteSuivi)
class NoteSuiviAdmin(admin.ModelAdmin):
    list_display = ("hospitalisation", "type", "date_note", "auteur")
    list_filter = ("type", "date_note")
    search_fields = ("hospitalisation__reference", "description")
