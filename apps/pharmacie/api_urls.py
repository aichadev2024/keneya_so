from rest_framework.routers import DefaultRouter

from .api_views import DispensationViewSet, MedicamentViewSet

router = DefaultRouter()
router.register("medicaments", MedicamentViewSet, basename="medicament")
router.register("dispensations", DispensationViewSet, basename="dispensation")

urlpatterns = router.urls
