from django.urls import path

from . import views

app_name = "assurances"

urlpatterns = [
    path("", views.AssuranceListView.as_view(), name="liste"),
    path("bordereaux/", views.BordereauListView.as_view(), name="bordereaux"),
    path("bordereaux/<int:pk>/", views.BordereauDetailView.as_view(), name="bordereau"),
    path("bordereaux/generer/<int:assurance_pk>/", views.generer_bordereau,
         name="bordereau_generer"),
    path("patient/<int:patient_pk>/adhesion/", views.PatientAssureCreateView.as_view(),
         name="patient_adhesion"),
]
