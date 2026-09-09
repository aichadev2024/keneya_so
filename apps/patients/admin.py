from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Allergie, DossierMedical, Patient


class AllergieInline(admin.TabularInline):
    model = Allergie
    extra = 0
    verbose_name = "allergie"
    verbose_name_plural = "allergies"


class DossierMedicalInline(admin.StackedInline):
    model = DossierMedical
    can_delete = False
    extra = 0
    fields = (
        "antecedents_medicaux", "antecedents_chirurgicaux", "antecedents_familiaux",
        "antecedents_gyneco_obstetricaux", "traitements_en_cours", "habitudes_vie",
        "observations",
    )


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("numero_dossier", "nom", "prenom", "sexe", "age", "telephone",
                    "ville", "actif")
    list_filter = ("actif", "sexe", "groupe_sanguin", "ville")
    search_fields = ("numero_dossier", "nom", "prenom", "telephone")
    readonly_fields = ("numero_dossier", "cree_le", "modifie_le", "cree_par", "modifie_par")
    inlines = [DossierMedicalInline]
    list_per_page = 30

    fieldsets = (
        (_("Identité"), {
            "fields": ("numero_dossier", ("nom", "prenom"), "sexe",
                       ("date_naissance", "date_naissance_estimee"),
                       "lieu_naissance", "nationalite", "photo"),
        }),
        (_("Coordonnées"), {
            "fields": ("telephone", "adresse", "ville"),
        }),
        (_("Personne à prévenir"), {
            "fields": ("personne_a_prevenir", "lien_personne_a_prevenir",
                       "telephone_urgence"),
        }),
        (_("Informations complémentaires"), {
            "fields": ("profession", "statut_matrimonial", "groupe_sanguin", "actif"),
        }),
        (_("Traçabilité"), {
            "classes": ("collapse",),
            "fields": ("cree_le", "cree_par", "modifie_le", "modifie_par"),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.cree_par = request.user
        obj.modifie_par = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description=_("âge"))
    def age(self, obj):
        return obj.age if obj.age is not None else "—"


@admin.register(DossierMedical)
class DossierMedicalAdmin(admin.ModelAdmin):
    list_display = ("patient", "modifie_le")
    search_fields = ("patient__nom", "patient__prenom", "patient__numero_dossier")
    inlines = [AllergieInline]
    autocomplete_fields = ()

    def has_add_permission(self, request):
        # Créé automatiquement avec le patient.
        return False


@admin.register(Allergie)
class AllergieAdmin(admin.ModelAdmin):
    list_display = ("libelle", "dossier", "type", "severite")
    list_filter = ("type", "severite")
    search_fields = ("libelle", "dossier__patient__nom", "dossier__patient__numero_dossier")
