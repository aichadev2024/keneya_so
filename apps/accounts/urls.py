from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("connexion/", views.ConnexionView.as_view(), name="login"),
    path("deconnexion/", views.DeconnexionView.as_view(), name="logout"),
    path("mot-de-passe/", views.ChangementMotDePasseView.as_view(), name="password_change"),
    path("mot-de-passe/termine/", views.ChangementMotDePasseTermineView.as_view(),
         name="password_change_done"),
    path("mot-de-passe-oublie/", views.MotDePasseOublieView.as_view(), name="password_reset"),
    path("mot-de-passe-oublie/envoye/", views.MotDePasseOublieEnvoyeView.as_view(),
         name="password_reset_done"),
    path("reinitialisation/<uidb64>/<token>/", views.NouveauMotDePasseView.as_view(),
         name="password_reset_confirm"),
    path("reinitialisation/termine/", views.NouveauMotDePasseTermineView.as_view(),
         name="password_reset_complete"),
    path("inscription/", views.InscriptionHopitalView.as_view(), name="inscription_hopital"),
    path("premiere-configuration/", views.PremiereConfigurationView.as_view(),
         name="premiere_configuration"),
]
