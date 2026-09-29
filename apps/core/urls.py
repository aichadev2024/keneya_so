from django.urls import path

from . import views, views_proprietaire as vp

app_name = "core"

urlpatterns = [
    path("", views.accueil, name="accueil"),
    path("tableau-de-bord/", views.dashboard, name="dashboard"),
    path("statistiques/", views.StatistiquesView.as_view(), name="statistiques"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/lire/", views.notification_lire, name="notification_lire"),
    path("notifications/tout-lire/", views.notifications_tout_lire,
         name="notifications_tout_lire"),

    # Console propriétaire (super-administrateur de la plateforme).
    path("proprietaire/etablissements/", vp.EtablissementListeView.as_view(),
         name="proprietaire_etablissements"),
    path("proprietaire/etablissements/nouveau/", vp.EtablissementCreerView.as_view(),
         name="proprietaire_etablissement_creer"),
    path("proprietaire/etablissements/<int:pk>/", vp.EtablissementDetailView.as_view(),
         name="proprietaire_etablissement"),
    path("proprietaire/etablissements/<int:pk>/modifier/", vp.EtablissementModifierView.as_view(),
         name="proprietaire_etablissement_modifier"),
    path("proprietaire/etablissements/<int:pk>/activer/", vp.etablissement_activer,
         name="proprietaire_etablissement_activer"),
    path("proprietaire/etablissements/<int:pk>/suspendre/", vp.etablissement_suspendre,
         name="proprietaire_etablissement_suspendre"),
    path("proprietaire/etablissements/<int:pk>/prolonger-essai/",
         vp.etablissement_prolonger_essai, name="proprietaire_etablissement_prolonger_essai"),

    path("proprietaire/plans/", vp.PlanListeView.as_view(), name="proprietaire_plans"),
    path("proprietaire/plans/nouveau/", vp.PlanCreerView.as_view(), name="proprietaire_plan_creer"),
    path("proprietaire/plans/<int:pk>/modifier/", vp.PlanModifierView.as_view(),
         name="proprietaire_plan_modifier"),

    path("proprietaire/utilisateurs/", vp.UtilisateurListeView.as_view(),
         name="proprietaire_utilisateurs"),
    path("proprietaire/utilisateurs/nouveau/", vp.UtilisateurCreerView.as_view(),
         name="proprietaire_utilisateur_creer"),
    path("proprietaire/utilisateurs/<int:pk>/modifier/", vp.UtilisateurModifierView.as_view(),
         name="proprietaire_utilisateur_modifier"),
    path("proprietaire/utilisateurs/<int:pk>/renvoyer-invitation/",
         vp.utilisateur_renvoyer_invitation, name="proprietaire_utilisateur_renvoyer_invitation"),
    path("proprietaire/utilisateurs/<int:pk>/basculer-actif/", vp.utilisateur_basculer_actif,
         name="proprietaire_utilisateur_basculer_actif"),

    path("proprietaire/journal/", vp.JournalListeView.as_view(), name="proprietaire_journal"),
]
