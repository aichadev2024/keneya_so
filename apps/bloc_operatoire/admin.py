from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    CompteRenduOperatoire,
    EtapeChecklist,
    IndisponibiliteSalle,
    Intervention,
    MaterielBloc,
    MaterielRequis,
    MembreEquipe,
    SalleOperatoire,
    TypeIntervention,
)


class IndisponibiliteInline(admin.TabularInline):
    model = IndisponibiliteSalle
    extra = 0


@admin.register(SalleOperatoire)
class SalleOperatoireAdmin(admin.ModelAdmin):
    list_display = ("nom", "code", "statut", "statut_effectif_col", "duree_nettoyage_min",
                    "actif")
    list_filter = ("statut", "actif")
    search_fields = ("nom", "code")
    inlines = [IndisponibiliteInline]

    @admin.display(description=_("statut temps réel"))
    def statut_effectif_col(self, obj):
        return obj.get_statut_effectif_display()


class MaterielRequisInline(admin.TabularInline):
    model = MaterielRequis
    extra = 1
    autocomplete_fields = ("materiel",)


@admin.register(TypeIntervention)
class TypeInterventionAdmin(admin.ModelAdmin):
    list_display = ("libelle", "specialite", "duree_standard_min", "actif")
    list_filter = ("specialite", "actif")
    search_fields = ("libelle",)
    inlines = [MaterielRequisInline]


@admin.register(MaterielBloc)
class MaterielBlocAdmin(admin.ModelAdmin):
    list_display = ("designation", "reference", "quantite_disponible",
                    "statut_sterilisation", "date_sterilisation", "actif")
    list_filter = ("statut_sterilisation", "actif")
    search_fields = ("designation", "reference")


class MembreEquipeInline(admin.TabularInline):
    model = MembreEquipe
    extra = 0
    autocomplete_fields = ("utilisateur",)


class EtapeChecklistInline(admin.TabularInline):
    model = EtapeChecklist
    extra = 0
    readonly_fields = ("valide_par", "valide_le")


class CompteRenduInline(admin.StackedInline):
    model = CompteRenduOperatoire
    extra = 0
    can_delete = False


@admin.register(Intervention)
class InterventionAdmin(admin.ModelAdmin):
    list_display = ("reference", "patient", "type_intervention", "salle",
                    "date_heure_debut_prevue", "niveau_urgence", "statut")
    list_filter = ("statut", "niveau_urgence", "salle", "date_heure_debut_prevue")
    search_fields = ("reference", "patient__nom", "patient__numero_dossier")
    date_hierarchy = "date_heure_debut_prevue"
    autocomplete_fields = ("patient", "type_intervention", "chirurgien_principal")
    readonly_fields = ("reference", "cree_le", "modifie_le", "annule_par", "annule_le")
    inlines = [MembreEquipeInline, EtapeChecklistInline, CompteRenduInline]


@admin.register(IndisponibiliteSalle)
class IndisponibiliteSalleAdmin(admin.ModelAdmin):
    list_display = ("salle", "motif", "date_debut", "date_fin")
    list_filter = ("motif", "salle")
