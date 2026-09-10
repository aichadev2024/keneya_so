from django.urls import path

from . import views

app_name = "facturation"

urlpatterns = [
    path("", views.FactureListView.as_view(), name="liste"),
    path("impayes/", views.ImpayesView.as_view(), name="impayes"),
    path("tarifs/", views.TarifListView.as_view(), name="tarifs"),
    path("<int:pk>/", views.FactureDetailView.as_view(), name="detail"),
    path("generer/<str:type_acte>/<int:acte_id>/", views.generer_facture, name="generer"),
    path("<int:pk>/emettre/", views.facture_emettre, name="emettre"),
    path("<int:pk>/annuler/", views.facture_annuler, name="annuler"),
    path("<int:pk>/ligne/ajouter/", views.ligne_ajouter, name="ligne_ajouter"),
    path("<int:pk>/ligne/<int:ligne_pk>/supprimer/", views.ligne_supprimer,
         name="ligne_supprimer"),
    path("<int:pk>/paiement/", views.paiement_ajouter, name="paiement_ajouter"),
    path("<int:pk>/relance/", views.relance_ajouter, name="relance_ajouter"),
]
