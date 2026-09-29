"""Console propriétaire : écrans dédiés (établissements, plans, utilisateurs, journal
d'audit) pour le super-administrateur de la plateforme, sans repasser par l'admin Django.

Toutes les vues sont réservées à ``request.user.est_plateforme`` (super-utilisateur sans
hôpital) : un administrateur d'hôpital, même « is_staff », n'y a pas accès.
"""

from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.accounts.invitations import tenter_invitation

from .forms import (
    CreationHopitalForm, EtablissementModifierForm, PlanForm, UtilisateurCreationForm,
    UtilisateurModifierForm,
)
from .models import Etablissement, HistoriqueAction, Plan
from .onboarding import creer_hopital_client

Utilisateur = get_user_model()


class ProprietaireRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Réserve la vue au propriétaire de la plateforme ; 403 pour tout autre compte connecté."""

    def test_func(self):
        return self.request.user.est_plateforme


def _redirection_sure(request, repli):
    """Revient sur ``next`` (champ caché du formulaire) si c'est une URL du site, sinon ``repli``."""
    cible = request.POST.get("next", "")
    if cible and url_has_allowed_host_and_scheme(
            cible, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(cible)
    return redirect(repli)


def proprietaire_requis(vue):
    """Décorateur pour les vues fonction : équivalent de ``ProprietaireRequiredMixin``."""

    @login_required
    @wraps(vue)
    def wrapper(request, *args, **kwargs):
        if not request.user.est_plateforme:
            raise PermissionDenied
        return vue(request, *args, **kwargs)
    return wrapper


# --------------------------------------------------------------------------- #
# Établissements
# --------------------------------------------------------------------------- #

class EtablissementListeView(ProprietaireRequiredMixin, ListView):
    template_name = "core/proprietaire/etablissements.html"
    context_object_name = "etablissements"
    paginate_by = 25

    def get_queryset(self):
        qs = Etablissement.objects.select_related("plan").annotate(
            nb_utilisateurs=Count("utilisateurs", filter=Q(utilisateurs__is_active=True)))
        self.q = self.request.GET.get("q", "").strip()
        self.statut = self.request.GET.get("statut", "")
        if self.q:
            qs = qs.filter(Q(nom__icontains=self.q) | Q(slug__icontains=self.q))
        if self.statut in Etablissement.Statut.values:
            qs = qs.filter(statut=self.statut)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({"q": self.q, "statut": self.statut, "statuts": Etablissement.Statut.choices})
        return ctx


class EtablissementDetailView(ProprietaireRequiredMixin, DetailView):
    model = Etablissement
    template_name = "core/proprietaire/etablissement_detail.html"
    context_object_name = "etablissement"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["utilisateurs"] = self.object.utilisateurs.order_by("last_name", "first_name")
        ctx["places_restantes"] = self.object.places_utilisateurs_restantes()
        return ctx


class EtablissementCreerView(ProprietaireRequiredMixin, CreateView):
    form_class = CreationHopitalForm
    template_name = "core/proprietaire/etablissement_creer.html"

    def form_valid(self, form):
        etab, admin_hopital, invitation_envoyee = creer_hopital_client(form, request=self.request)
        self.object = etab
        if invitation_envoyee:
            messages.success(
                self.request, _("Hôpital créé. Invitation envoyée à %(e)s.") % {"e": admin_hopital.email})
        else:
            messages.warning(
                self.request,
                _("L'hôpital est créé, mais l'e-mail d'invitation n'a pas pu être envoyé. "
                  "Depuis la fiche de son administrateur, utilisez « Renvoyer l'invitation »."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("core:proprietaire_etablissement", args=[self.object.pk])


class EtablissementModifierView(ProprietaireRequiredMixin, UpdateView):
    model = Etablissement
    form_class = EtablissementModifierForm
    template_name = "core/proprietaire/etablissement_modifier.html"

    def form_valid(self, form):
        messages.success(self.request, _("Établissement mis à jour."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("core:proprietaire_etablissement", args=[self.object.pk])


@proprietaire_requis
@require_POST
def etablissement_activer(request, pk):
    etab = get_object_or_404(Etablissement, pk=pk)
    etab.statut = Etablissement.Statut.ACTIF
    etab.essai_jusqu_au = None
    etab.save(update_fields=["statut", "essai_jusqu_au"])
    messages.success(request, _("Abonnement activé : accès sans limite de date."))
    return _redirection_sure(request, reverse("core:proprietaire_etablissement", args=[pk]))


@proprietaire_requis
@require_POST
def etablissement_suspendre(request, pk):
    etab = get_object_or_404(Etablissement, pk=pk)
    etab.statut = Etablissement.Statut.SUSPENDU
    etab.save(update_fields=["statut"])
    messages.warning(request, _("Accès suspendu."))
    return _redirection_sure(request, reverse("core:proprietaire_etablissement", args=[pk]))


@proprietaire_requis
@require_POST
def etablissement_prolonger_essai(request, pk):
    etab = get_object_or_404(Etablissement, pk=pk)
    etab.prolonger_essai()
    messages.success(request, _("Essai prolongé de 30 jours."))
    return _redirection_sure(request, reverse("core:proprietaire_etablissement", args=[pk]))


# --------------------------------------------------------------------------- #
# Plans d'abonnement
# --------------------------------------------------------------------------- #

class PlanListeView(ProprietaireRequiredMixin, ListView):
    template_name = "core/proprietaire/plans.html"
    context_object_name = "plans"

    def get_queryset(self):
        return Plan.objects.annotate(nb_etablissements=Count("etablissements"))


class PlanCreerView(ProprietaireRequiredMixin, CreateView):
    model = Plan
    form_class = PlanForm
    template_name = "core/proprietaire/plan_formulaire.html"
    success_url = reverse_lazy("core:proprietaire_plans")

    def form_valid(self, form):
        messages.success(self.request, _("Plan créé."))
        return super().form_valid(form)


class PlanModifierView(ProprietaireRequiredMixin, UpdateView):
    model = Plan
    form_class = PlanForm
    template_name = "core/proprietaire/plan_formulaire.html"
    success_url = reverse_lazy("core:proprietaire_plans")

    def form_valid(self, form):
        messages.success(self.request, _("Plan mis à jour."))
        return super().form_valid(form)


# --------------------------------------------------------------------------- #
# Utilisateurs (tous hôpitaux confondus)
# --------------------------------------------------------------------------- #

class UtilisateurListeView(ProprietaireRequiredMixin, ListView):
    template_name = "core/proprietaire/utilisateurs.html"
    context_object_name = "utilisateurs"
    paginate_by = 25

    def get_queryset(self):
        qs = Utilisateur.tous.select_related("etablissement").order_by(
            "etablissement__nom", "last_name", "first_name")
        self.q = self.request.GET.get("q", "").strip()
        self.etablissement_id = self.request.GET.get("etablissement", "")
        if self.q:
            qs = qs.filter(Q(username__icontains=self.q) | Q(first_name__icontains=self.q)
                           | Q(last_name__icontains=self.q) | Q(email__icontains=self.q))
        if self.etablissement_id:
            qs = qs.filter(etablissement_id=self.etablissement_id)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            "q": self.q, "etablissement_id": self.etablissement_id,
            "etablissements": Etablissement.objects.order_by("nom"),
        })
        return ctx


class UtilisateurCreerView(ProprietaireRequiredMixin, CreateView):
    form_class = UtilisateurCreationForm
    template_name = "core/proprietaire/utilisateur_formulaire.html"

    def get_initial(self):
        initial = super().get_initial()
        etab_id = self.request.GET.get("etablissement")
        if etab_id:
            initial["etablissement"] = etab_id
        return initial

    def form_valid(self, form):
        self.object = form.save()
        if tenter_invitation(self.object, self.request):
            messages.success(
                self.request, _("Invitation envoyée à %(e)s.") % {"e": self.object.email})
        else:
            messages.warning(
                self.request,
                _("Le compte est créé, mais l'e-mail d'invitation n'a pas pu être envoyé. "
                  "Depuis la liste, utilisez « Renvoyer l'invitation »."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return f"{reverse('core:proprietaire_utilisateurs')}?etablissement={self.object.etablissement_id}"


class UtilisateurModifierView(ProprietaireRequiredMixin, UpdateView):
    form_class = UtilisateurModifierForm
    template_name = "core/proprietaire/utilisateur_formulaire.html"

    def get_queryset(self):
        return Utilisateur.tous.all()

    def form_valid(self, form):
        messages.success(self.request, _("Compte mis à jour."))
        return super().form_valid(form)

    def get_success_url(self):
        return f"{reverse('core:proprietaire_utilisateurs')}?etablissement={self.object.etablissement_id or ''}"


@proprietaire_requis
@require_POST
def utilisateur_renvoyer_invitation(request, pk):
    utilisateur = get_object_or_404(Utilisateur.tous, pk=pk)
    if not utilisateur.email:
        messages.error(request, _("« %(u)s » n'a pas d'adresse e-mail.") % {"u": utilisateur.username})
    elif not utilisateur.is_active:
        messages.error(request, _("« %(u)s » est désactivé.") % {"u": utilisateur.username})
    elif tenter_invitation(utilisateur, request):
        messages.success(request, _("Invitation envoyée à %(e)s.") % {"e": utilisateur.email})
    else:
        messages.error(request, _("L'envoi de l'invitation a échoué. Réessayez plus tard."))
    return _redirection_sure(request, reverse("core:proprietaire_utilisateurs"))


@proprietaire_requis
@require_POST
def utilisateur_basculer_actif(request, pk):
    utilisateur = get_object_or_404(Utilisateur.tous, pk=pk)
    utilisateur.is_active = not utilisateur.is_active
    utilisateur.save(update_fields=["is_active"])
    if utilisateur.is_active:
        messages.success(request, _("« %(u)s » réactivé(e).") % {"u": utilisateur.username})
    else:
        messages.warning(request, _("« %(u)s » désactivé(e).") % {"u": utilisateur.username})
    return _redirection_sure(request, reverse("core:proprietaire_utilisateurs"))


# --------------------------------------------------------------------------- #
# Journal d'audit (lecture seule)
# --------------------------------------------------------------------------- #

class JournalListeView(ProprietaireRequiredMixin, ListView):
    template_name = "core/proprietaire/journal.html"
    context_object_name = "entrees"
    paginate_by = 30

    def get_queryset(self):
        qs = HistoriqueAction.objects.select_related("utilisateur", "etablissement").order_by(
            "-horodatage")
        self.q = self.request.GET.get("q", "").strip()
        self.action = self.request.GET.get("action", "")
        if self.q:
            qs = qs.filter(Q(description__icontains=self.q)
                           | Q(utilisateur__username__icontains=self.q)
                           | Q(objet_id__icontains=self.q))
        if self.action in HistoriqueAction.Action.values:
            qs = qs.filter(action=self.action)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({"q": self.q, "action": self.action, "actions": HistoriqueAction.Action.choices})
        return ctx
