from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("tableau-de-bord/", views.dashboard, name="dashboard"),
]
