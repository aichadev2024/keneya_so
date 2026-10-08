from django.urls import path

from . import views

app_name = "soins"

urlpatterns = [
    path("", views.SoinListView.as_view(), name="liste"),
    path("patient/<int:patient_pk>/nouveau/", views.SoinCreateView.as_view(), name="creer"),
    path("<int:pk>/", views.SoinDetailView.as_view(), name="detail"),
]
