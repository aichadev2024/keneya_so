from rest_framework.routers import DefaultRouter

from .api_views import DemandeExamenViewSet, TypeExamenViewSet

router = DefaultRouter()
router.register("examens/types", TypeExamenViewSet, basename="type-examen")
router.register("examens/demandes", DemandeExamenViewSet, basename="demande-examen")

urlpatterns = router.urls
