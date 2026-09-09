"""Routage racine du projet Kènèya Sô."""

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

# --------------------------------------------------------------------------- #
# URLs non traduites (API, admin, bascule de langue)
# --------------------------------------------------------------------------- #
urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),  # POST set_language (CDC 4.11)
    path("admin/", admin.site.urls),

    # API REST versionnée (CDC 8)
    path("api/v1/", include("apps.accounts.api_urls")),
    path("api/v1/", include("apps.patients.api_urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
]

# --------------------------------------------------------------------------- #
# URLs traduites (préfixe de langue /fr/, /en/, /ar/ ...)
# --------------------------------------------------------------------------- #
urlpatterns += i18n_patterns(
    path("", include("apps.core.urls")),
    path("comptes/", include("apps.accounts.urls")),
    path("patients/", include("apps.patients.urls")),
    prefix_default_language=True,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Administration — Kènèya Sô"
admin.site.site_title = "Kènèya Sô"
admin.site.index_title = "Gestion hospitalière"
