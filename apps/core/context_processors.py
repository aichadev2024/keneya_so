"""Contexte global des gabarits : notifications non lues, navigation principale."""

from .models import Notification


def navigation(request):
    """Expose la navigation principale (barre latérale) à tous les gabarits."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    from .views import _raccourcis_pour

    vue_active = None
    if getattr(request, "resolver_match", None):
        vue_active = request.resolver_match.view_name  # ex. "patients:liste"

    items = _raccourcis_pour(user)
    for item in items:
        # Actif sur l'URL exacte du raccourci, ou sur toute autre vue du même
        # module (ex. la fiche d'un patient reste sous "Patients").
        namespace = item["url_name"].split(":")[0]
        item["actif"] = (
            item["url_name"] == vue_active
            or (vue_active and vue_active.split(":")[0] == namespace
                and namespace not in {"core", "admin"})
        )
    return {"navigation_principale": items}


def notifications(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    recentes = list(
        Notification.objects.filter(destinataire=user)[:8]
    )
    non_lues = sum(1 for n in recentes if not n.lu)
    # Compte exact au-delà des 8 dernières si nécessaire.
    if non_lues == 0:
        non_lues = Notification.objects.filter(destinataire=user, lu=False).count()
    return {
        "notifications_recentes": recentes,
        "notifications_non_lues": Notification.objects.filter(
            destinataire=user, lu=False).count(),
    }


def abonnement(request):
    """Établissement courant et jours d'essai restants (bandeau d'information)."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.etablissement_id:
        return {}
    etab = user.etablissement
    return {"etablissement_courant": etab, "jours_essai_restants": etab.jours_essai_restants}


def plateforme(request):
    """Réglages publics de la plateforme (vitrine, page de connexion)."""
    from django.conf import settings

    return {"INSCRIPTION_LIBRE": settings.INSCRIPTION_LIBRE,
            "CONTACT_EMAIL": settings.CONTACT_EMAIL}
