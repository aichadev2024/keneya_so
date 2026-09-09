from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("connexion/", views.ConnexionView.as_view(), name="login"),
    path("deconnexion/", views.DeconnexionView.as_view(), name="logout"),
    path("mot-de-passe/", views.ChangementMotDePasseView.as_view(), name="password_change"),
    path("mot-de-passe/termine/", views.ChangementMotDePasseTermineView.as_view(),
         name="password_change_done"),
]
