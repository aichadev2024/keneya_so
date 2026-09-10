"""Vues gabarit du module assurances (CDC 4.9)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView

from apps.core.models import HistoriqueAction
from apps.patients.models import Patient

from . import services
from .forms import GenererBordereauForm, PatientAssureForm
from .models import Assurance, BordereauAssurance


class AssuranceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "assurances.view_assurance"
    template_name = "assurances/liste.html"
    context_object_name = "assurances"
    queryset = Assurance.objects.prefetch_related("contrats")


class PatientAssureCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "assurances.add_patientassure"
    form_class = PatientAssureForm
    template_name = "assurances/patient_assure_formulaire.html"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient, pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.patient = self.patient
        response = super().form_valid(form)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user, action=HistoriqueAction.Action.CREATION,
            objet=self.object, description=f"Adhésion assurance — {self.patient.nom_complet}",
        )
        messages.success(self.request, _("Couverture d'assurance enregistrée."))
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["patient"] = self.patient
        return ctx

    def get_success_url(self):
        return reverse("patients:detail", args=[self.patient.pk])


class BordereauListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "assurances.view_bordereauassurance"
    template_name = "assurances/bordereaux.html"
    context_object_name = "bordereaux"
    paginate_by = 25
    queryset = BordereauAssurance.objects.select_related("assurance")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["assurances"] = Assurance.objects.filter(actif=True)
        ctx["form"] = GenererBordereauForm()
        return ctx


class BordereauDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "assurances.view_bordereauassurance"
    model = BordereauAssurance
    template_name = "assurances/bordereau_detail.html"
    context_object_name = "bordereau"


def generer_bordereau(request, assurance_pk):
    if request.method != "POST":
        return redirect("assurances:bordereaux")
    if not request.user.has_perm("assurances.add_bordereauassurance"):
        messages.error(request, _("Action non autorisée."))
        return redirect("assurances:bordereaux")
    assurance = get_object_or_404(Assurance, pk=assurance_pk)
    form = GenererBordereauForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Période invalide."))
        return redirect("assurances:bordereaux")
    try:
        bordereau = services.generer_bordereau(
            assurance=assurance, periode_debut=form.cleaned_data["periode_debut"],
            periode_fin=form.cleaned_data["periode_fin"], par=request.user,
        )
    except services.ErreurBordereau as exc:
        messages.error(request, str(exc))
        return redirect("assurances:bordereaux")
    HistoriqueAction.enregistrer(
        utilisateur=request.user, action=HistoriqueAction.Action.CREATION,
        objet=bordereau, description=f"Bordereau {bordereau.reference} — {assurance.nom}",
    )
    messages.success(request, _("Bordereau %(r)s généré (%(n)d factures, %(m)s FCFA).")
                     % {"r": bordereau.reference, "n": bordereau.lignes.count(),
                        "m": bordereau.montant_total})
    return redirect("assurances:bordereau", pk=bordereau.pk)
