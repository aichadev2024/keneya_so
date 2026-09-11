from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("tableau-de-bord/", views.dashboard, name="dashboard"),
    path("statistiques/", views.StatistiquesView.as_view(), name="statistiques"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/lire/", views.notification_lire, name="notification_lire"),
    path("notifications/tout-lire/", views.notifications_tout_lire,
         name="notifications_tout_lire"),
]
