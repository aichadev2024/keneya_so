from rest_framework.routers import DefaultRouter

from .api_views import (
    AssuranceViewSet,
    BordereauAssuranceViewSet,
    ContratAssuranceViewSet,
    PatientAssureViewSet,
)

router = DefaultRouter()
router.register("assurances", AssuranceViewSet, basename="assurance")
router.register("assurances-contrats", ContratAssuranceViewSet, basename="contrat")
router.register("patients-assures", PatientAssureViewSet, basename="patient-assure")
router.register("assurances-bordereaux", BordereauAssuranceViewSet, basename="bordereau")

urlpatterns = router.urls
