"""Contexte global des gabarits : notifications non lues de l'utilisateur."""

from .models import Notification


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
