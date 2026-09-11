"""Vues transverses : page d'accueil et tableau de bord par profil (CDC 2.2)."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def dashboard(request):
    """
    Tableau de bord adapté au rôle de l'utilisateur connecté.

    Le contenu détaillé (indicateurs, raccourcis par module) sera enrichi au fil
    des phases du planning (CDC 11.2). Pour l'instant : point d'entrée unique
    après connexion, avec les accès disponibles dans le socle.
    """
    utilisateur = request.user
    context = {
        "role_affiche": utilisateur.get_role_display() if utilisateur.role else None,
        "raccourcis": _raccourcis_pour(utilisateur),
    }
    return render(request, "core/dashboard.html", context)


def accueil(request):
    """Redirige vers le tableau de bord si connecté, sinon vers la connexion."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    return redirect("accounts:login")


@login_required
def notifications(request):
    liste = request.user.notifications.all()[:100]
    return render(request, "core/notifications.html", {"notifications": liste})


@require_POST
@login_required
def notification_lire(request, pk):
    notif = get_object_or_404(Notification, pk=pk, destinataire=request.user)
    notif.lu = True
    notif.save(update_fields=["lu"])
    return redirect(notif.url or "core:notifications")


@require_POST
@login_required
def notifications_tout_lire(request):
    request.user.notifications.filter(lu=False).update(lu=True)
    return redirect("core:notifications")


def _raccourcis_pour(utilisateur):
    """Liste de raccourcis (libellé, url_name) selon les permissions réelles."""
    raccourcis = []
    if utilisateur.has_perm("patients.view_patient"):
        raccourcis.append((_("Patients"), "patients:liste"))
    if utilisateur.has_perm("consultations.view_consultation"):
        raccourcis.append((_("Consultations"), "consultations:liste"))
    if utilisateur.has_perm("hospitalisation.view_hospitalisation"):
        raccourcis.append((_("Hospitalisation"), "hospitalisation:occupation"))
    if utilisateur.has_perm("bloc_operatoire.view_intervention"):
        raccourcis.append((_("Bloc opératoire"), "bloc_operatoire:planning"))
    if utilisateur.has_perm("laboratoire.view_demandeexamen"):
        raccourcis.append((_("Analyses & imagerie"), "laboratoire:liste"))
    if utilisateur.has_perm("facturation.view_facture"):
        raccourcis.append((_("Facturation"), "facturation:liste"))
    if utilisateur.has_perm("assurances.view_bordereauassurance"):
        raccourcis.append((_("Bordereaux assurance"), "assurances:bordereaux"))
    if utilisateur.has_perm("pharmacie.view_dispensation"):
        raccourcis.append((_("Dispensations"), "pharmacie:dispensations"))
    if utilisateur.has_perm("pharmacie.view_medicament"):
        raccourcis.append((_("Pharmacie — stock"), "pharmacie:medicaments"))
    if utilisateur.is_staff:
        raccourcis.append((_("Administration"), "admin:index"))
    return raccourcis
