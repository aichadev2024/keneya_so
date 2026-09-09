from rest_framework.routers import DefaultRouter

from .api_views import UtilisateurViewSet

router = DefaultRouter()
router.register("utilisateurs", UtilisateurViewSet, basename="utilisateur")

urlpatterns = router.urls
