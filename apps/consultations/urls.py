from django.urls import path

from . import views

app_name = "consultations"

urlpatterns = [
    path("", views.ConsultationListView.as_view(), name="liste"),
    path("patient/<int:patient_pk>/nouvelle/", views.ConsultationCreateView.as_view(),
         name="creer"),
    path("<int:pk>/", views.ConsultationDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.ConsultationUpdateView.as_view(), name="modifier"),
    path("<int:pk>/cloturer/", views.consultation_cloturer, name="cloturer"),
    path("<int:pk>/constantes/", views.ConstantesUpdateView.as_view(), name="constantes"),
    path("<int:pk>/ordonnance/creer/", views.OrdonnanceCreateView.as_view(),
         name="ordonnance_creer"),
    path("ordonnance/<int:pk>/", views.OrdonnanceDetailView.as_view(), name="ordonnance"),
    path("ordonnance/<int:pk>/ligne/ajouter/", views.ligne_ajouter, name="ligne_ajouter"),
    path("ordonnance/<int:pk>/ligne/<int:ligne_pk>/supprimer/", views.ligne_supprimer,
         name="ligne_supprimer"),
    path("ordonnance/<int:pk>/transmettre/", views.ordonnance_transmettre,
         name="ordonnance_transmettre"),
]
