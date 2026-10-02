from django.urls import path

from . import views

app_name = "laboratoire"

urlpatterns = [
    path("", views.DemandeListView.as_view(), name="liste"),
    path("types-examen/ajouter/", views.TypeExamenCreateView.as_view(),
         name="typeexamen_ajouter"),
    path("types-examen/importer/", views.TypeExamenImportView.as_view(),
         name="typeexamen_importer"),
    path("types-examen/importer/modele.xlsx", views.modele_import_types_examen,
         name="typeexamen_import_modele"),
    path("mes-resultats/", views.MesResultatsView.as_view(), name="mes_resultats"),
    path("<int:pk>/", views.DemandeDetailView.as_view(), name="detail"),
    path("patient/<int:patient_pk>/demander/", views.DemandeCreateView.as_view(),
         name="demander"),
    path("<int:pk>/ligne/<int:ligne_pk>/resultat/", views.saisir_resultat,
         name="saisir_resultat"),
    path("<int:pk>/ligne/<int:ligne_pk>/fichier/", views.telecharger_resultat,
         name="telecharger_resultat"),
    path("<int:pk>/valider/", views.demande_valider, name="valider"),
    path("<int:pk>/annuler/", views.demande_annuler, name="annuler"),
]
