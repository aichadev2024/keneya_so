from django.urls import path

from . import views

app_name = "hospitalisation"

urlpatterns = [
    path("", views.OccupationView.as_view(), name="occupation"),
    path("sejours/", views.HospitalisationListView.as_view(), name="liste"),
    path("sejours/<int:pk>/", views.HospitalisationDetailView.as_view(), name="detail"),
    path("patient/<int:patient_pk>/admettre/", views.AdmissionView.as_view(),
         name="admettre"),
    path("sejours/<int:pk>/note/", views.note_ajouter, name="note_ajouter"),
    path("sejours/<int:pk>/transferer/", views.sejour_transferer, name="transferer"),
    path("sejours/<int:pk>/sortie/", views.sejour_sortie, name="sortie"),
]
