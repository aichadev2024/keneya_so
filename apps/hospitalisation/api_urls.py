from rest_framework.routers import DefaultRouter

from .api_views import (
    HospitalisationViewSet,
    LitViewSet,
    ServiceViewSet,
)

router = DefaultRouter()
router.register("services", ServiceViewSet, basename="service")
router.register("lits", LitViewSet, basename="lit")
router.register("hospitalisations", HospitalisationViewSet, basename="hospitalisation")

urlpatterns = router.urls
