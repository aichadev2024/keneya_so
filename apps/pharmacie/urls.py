from django.urls import path

from . import views

app_name = "pharmacie"

urlpatterns = [
    path("", views.MedicamentListView.as_view(), name="medicaments"),
    path("nouveau/", views.MedicamentCreateView.as_view(), name="medicament_creer"),
    path("<int:pk>/", views.MedicamentDetailView.as_view(), name="medicament"),
    path("<int:pk>/modifier/", views.MedicamentUpdateView.as_view(),
         name="medicament_modifier"),
    path("stock/entree/", views.EntreeStockView.as_view(), name="entree_stock"),
    path("stock/perimes/retirer/", views.retirer_perimes_view, name="retirer_perimes"),
    path("stock/mouvements/", views.MouvementStockListView.as_view(), name="mouvements"),
    path("dispensations/", views.DispensationListView.as_view(), name="dispensations"),
    path("dispensations/<int:pk>/", views.DispensationDetailView.as_view(),
         name="dispensation"),
    path("dispensations/<int:pk>/delivrer/", views.dispensation_delivrer,
         name="dispensation_delivrer"),
]
