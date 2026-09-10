from django.urls import path
from rest_framework.routers import DefaultRouter

from .api_views import (
    IndicateursBlocView,
    InterventionViewSet,
    MaterielBlocViewSet,
    SalleOperatoireViewSet,
    TypeInterventionViewSet,
)

router = DefaultRouter()
router.register("bloc/salles", SalleOperatoireViewSet, basename="salle-operatoire")
router.register("bloc/types-intervention", TypeInterventionViewSet,
                basename="type-intervention")
router.register("bloc/materiels", MaterielBlocViewSet, basename="materiel-bloc")
router.register("bloc/interventions", InterventionViewSet, basename="intervention")

urlpatterns = router.urls + [
    path("bloc/indicateurs/", IndicateursBlocView.as_view(), name="bloc-indicateurs"),
]
