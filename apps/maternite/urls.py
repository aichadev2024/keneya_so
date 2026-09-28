from django.urls import path

from . import views

app_name = "maternite"

urlpatterns = [
    path("", views.AccueilMaterniteView.as_view(), name="accueil"),
    path("dossiers/", views.DossierListView.as_view(), name="dossiers"),
    path("patiente/<int:patient_pk>/nouveau/", views.DossierCreateView.as_view(),
         name="dossier_nouveau"),
    path("dossiers/<int:pk>/", views.DossierDetailView.as_view(), name="dossier"),
    path("dossiers/<int:pk>/modifier/", views.DossierUpdateView.as_view(),
         name="dossier_modifier"),
    path("dossiers/<int:pk>/cloturer/", views.DossierTerminerView.as_view(),
         name="dossier_terminer"),
    path("dossiers/<int:dossier_pk>/visite/nouvelle/", views.VisiteCreateView.as_view(),
         name="visite_nouvelle"),
    path("visites/<int:pk>/", views.VisiteDetailView.as_view(), name="visite"),
    path("visites/<int:pk>/modifier/", views.VisiteUpdateView.as_view(),
         name="visite_modifier"),
]
