from django.urls import path

from . import views

app_name = "bloc_operatoire"

urlpatterns = [
    path("", views.PlanningView.as_view(), name="planning"),
    path("interventions/", views.InterventionListView.as_view(), name="liste"),
    path("interventions/<int:pk>/", views.InterventionDetailView.as_view(), name="detail"),
    path("indicateurs/", views.IndicateursView.as_view(), name="indicateurs"),
    path("patient/<int:patient_pk>/demander/", views.DemandeInterventionView.as_view(),
         name="demander"),

    path("interventions/<int:pk>/planifier/", views.planifier, name="planifier"),
    path("interventions/<int:pk>/faisabilite/", views.valider_faisabilite,
         name="faisabilite"),
    path("interventions/<int:pk>/equipe/ajouter/", views.membre_ajouter,
         name="membre_ajouter"),
    path("interventions/<int:pk>/equipe/<int:membre_pk>/retirer/", views.membre_retirer,
         name="membre_retirer"),
    path("interventions/<int:pk>/checklist/<str:temps>/", views.checklist_valider,
         name="checklist_valider"),
    path("interventions/<int:pk>/peroperatoire/<str:etape>/", views.etape_peroperatoire,
         name="peroperatoire"),
    path("interventions/<int:pk>/annuler/", views.intervention_annuler, name="annuler"),
    path("interventions/<int:pk>/compte-rendu/", views.compte_rendu_enregistrer,
         name="compte_rendu"),
]
