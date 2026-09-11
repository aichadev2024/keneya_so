from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import DemandeExamen, LigneExamen, Resultat, TypeExamen


@admin.register(TypeExamen)
class TypeExamenAdmin(admin.ModelAdmin):
    list_display = ("libelle", "code", "categorie", "unite", "valeurs_reference",
                    "delai_rendu_heures", "actif")
    list_filter = ("categorie", "actif")
    search_fields = ("code", "libelle")


class ResultatInline(admin.StackedInline):
    model = Resultat
    extra = 0
    can_delete = False
    readonly_fields = ("saisi_par", "saisi_le", "valide_par", "valide_le")


class LigneExamenInline(admin.TabularInline):
    model = LigneExamen
    extra = 1
    autocomplete_fields = ("type_examen",)


@admin.register(DemandeExamen)
class DemandeExamenAdmin(admin.ModelAdmin):
    list_display = ("reference", "patient", "categorie", "priorite", "statut",
                    "prescripteur", "date_demande")
    list_filter = ("categorie", "statut", "priorite", "date_demande")
    search_fields = ("reference", "patient__nom", "patient__numero_dossier")
    date_hierarchy = "date_demande"
    autocomplete_fields = ("patient",)
    readonly_fields = ("reference", "cree_le", "modifie_le")
    inlines = [LigneExamenInline]


@admin.register(Resultat)
class ResultatAdmin(admin.ModelAdmin):
    list_display = ("ligne", "valeur", "interpretation", "valide", "saisi_par",
                    "valide_le")
    list_filter = ("valide", "interpretation")
    search_fields = ("ligne__demande__reference",)
