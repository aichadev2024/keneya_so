from rest_framework.routers import DefaultRouter

from .api_views import ConsultationViewSet, OrdonnanceViewSet

router = DefaultRouter()
router.register("consultations", ConsultationViewSet, basename="consultation")
router.register("ordonnances", OrdonnanceViewSet, basename="ordonnance")

urlpatterns = router.urls
