from rest_framework.routers import DefaultRouter

from .api_views import FactureViewSet, TarifViewSet

router = DefaultRouter()
router.register("factures", FactureViewSet, basename="facture")
router.register("tarifs", TarifViewSet, basename="tarif")

urlpatterns = router.urls
