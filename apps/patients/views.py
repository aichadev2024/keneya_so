"""Vues gabarit pour la gestion des patients (CDC 4.1 / 4.2)."""

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.models import HistoriqueAction

from .forms import DossierMedicalForm, PatientForm
from .models import DossierMedical, Patient


class _AuteurMixin:
    """Renseigne cree_par / modifie_par et journalise l'action (CDC 7.1)."""

    action_audit = HistoriqueAction.Action.MODIFICATION

    def form_valid(self, form):
        est_creation = form.instance.pk is None
        if est_creation:
            form.instance.cree_par = self.request.user
        form.instance.modifie_par = self.request.user
        response = super().form_valid(form)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user,
            action=(HistoriqueAction.Action.CREATION if est_creation
                    else self.action_audit),
            objet=self.object,
            description=str(self.object),
        )
        return response


class PatientListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "patients.view_patient"
    model = Patient
    template_name = "patients/liste.html"
    context_object_name = "patients"
    paginate_by = 25

    def get_queryset(self):
        qs = Patient.objects.all()
        self.recherche = self.request.GET.get("q", "").strip()
        if self.recherche:
            qs = qs.recherche(self.recherche)
        if self.request.GET.get("inactifs") != "1":
            qs = qs.actifs()
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["recherche"] = self.recherche
        ctx["inclure_inactifs"] = self.request.GET.get("inactifs") == "1"
        return ctx


class PatientDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "patients.view_patient"
    model = Patient
    template_name = "patients/detail.html"
    context_object_name = "patient"

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Consultation d'un dossier médical = action sensible tracée (CDC 7.1 / 7.4).
        HistoriqueAction.enregistrer(
            utilisateur=request.user,
            action=HistoriqueAction.Action.CONSULTATION,
            objet=self.object,
            description=_("Consultation de la fiche patient"),
        )
        return response


class PatientCreateView(LoginRequiredMixin, PermissionRequiredMixin,
                        SuccessMessageMixin, _AuteurMixin, CreateView):
    permission_required = "patients.add_patient"
    model = Patient
    form_class = PatientForm
    template_name = "patients/formulaire.html"
    success_message = _("Patient créé. Numéro de dossier : %(numero_dossier)s")

    def get_success_url(self):
        return reverse("patients:detail", args=[self.object.pk])


class PatientUpdateView(LoginRequiredMixin, PermissionRequiredMixin,
                        SuccessMessageMixin, _AuteurMixin, UpdateView):
    permission_required = "patients.change_patient"
    model = Patient
    form_class = PatientForm
    template_name = "patients/formulaire.html"
    success_message = _("Fiche patient mise à jour.")

    def get_success_url(self):
        return reverse("patients:detail", args=[self.object.pk])


class DossierMedicalUpdateView(LoginRequiredMixin, PermissionRequiredMixin,
                               SuccessMessageMixin, UpdateView):
    permission_required = "patients.change_dossiermedical"
    form_class = DossierMedicalForm
    template_name = "patients/dossier_formulaire.html"
    success_message = _("Dossier médical mis à jour.")

    def get_object(self, queryset=None):
        patient = get_object_or_404(Patient, pk=self.kwargs["pk"])
        dossier, _created = DossierMedical.objects.get_or_create(patient=patient)
        return dossier

    def form_valid(self, form):
        form.instance.modifie_par = self.request.user
        response = super().form_valid(form)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user,
            action=HistoriqueAction.Action.MODIFICATION,
            objet=self.object,
            description=_("Modification du dossier médical"),
        )
        return response

    def get_success_url(self):
        return reverse("patients:detail", args=[self.object.patient.pk])


def racine_patients(request):
    return redirect("patients:liste")
