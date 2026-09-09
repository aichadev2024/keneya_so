"""Vues gabarit du module hospitalisation (CDC 4.4)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from apps.core.models import HistoriqueAction
from apps.patients.models import Patient

from .forms import AdmissionForm, NoteSuiviForm, SortieForm, TransfertForm
from .models import Hospitalisation, Service
from .services import ErreurHospitalisation, admettre, prononcer_sortie, transferer


class OccupationView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """Vue d'occupation des lits en temps réel par service (CDC 4.4)."""

    permission_required = "hospitalisation.view_hospitalisation"
    template_name = "hospitalisation/occupation.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        services = []
        qs = Service.objects.filter(actif=True).prefetch_related(
            "chambres__lits__hospitalisations__patient"
        )
        for service in qs:
            chambres = []
            for chambre in service.chambres.all():
                chambres.append({"obj": chambre, "lits": list(chambre.lits.all())})
            services.append({
                "obj": service, "chambres": chambres,
                "nb_lits": service.nb_lits, "occupes": service.nb_lits_occupes,
                "taux": service.taux_occupation,
            })
        ctx["services"] = services
        return ctx


class HospitalisationListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "hospitalisation.view_hospitalisation"
    template_name = "hospitalisation/liste.html"
    context_object_name = "sejours"
    paginate_by = 25

    def get_queryset(self):
        qs = Hospitalisation.objects.select_related("patient", "service", "lit__chambre",
                                                    "medecin_referent")
        self.q = self.request.GET.get("q", "").strip()
        self.statut = self.request.GET.get("statut", "EN_COURS")
        if self.q:
            qs = qs.filter(
                Q(reference__icontains=self.q)
                | Q(patient__nom__icontains=self.q)
                | Q(patient__prenom__icontains=self.q)
                | Q(patient__numero_dossier__icontains=self.q)
            )
        if self.statut:
            qs = qs.filter(statut=self.statut)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.q
        ctx["statut"] = self.statut
        ctx["statuts"] = Hospitalisation.Statut.choices
        return ctx


class HospitalisationDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "hospitalisation.view_hospitalisation"
    model = Hospitalisation
    template_name = "hospitalisation/detail.html"
    context_object_name = "sejour"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form_note"] = NoteSuiviForm()
        ctx["form_transfert"] = TransfertForm()
        ctx["form_sortie"] = SortieForm()
        ctx["peut_soigner"] = self.request.user.has_perm("hospitalisation.add_notesuivi")
        ctx["peut_gerer"] = self.request.user.has_perm(
            "hospitalisation.change_hospitalisation")
        return ctx


class AdmissionView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "hospitalisation.add_hospitalisation"
    template_name = "hospitalisation/admission.html"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient, pk=kwargs["patient_pk"])
        self.sejour_actif = self.patient.hospitalisations.filter(
            statut=Hospitalisation.Statut.EN_COURS).first()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["patient"] = self.patient
        ctx["sejour_actif"] = self.sejour_actif
        ctx.setdefault("form", AdmissionForm())
        return ctx

    def post(self, request, *args, **kwargs):
        if self.sejour_actif:
            messages.error(request, _("Ce patient est déjà hospitalisé."))
            return redirect("hospitalisation:detail", pk=self.sejour_actif.pk)
        form = AdmissionForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        d = form.cleaned_data
        try:
            sejour = admettre(
                patient=self.patient, service=d["service"], lit=d["lit"],
                motif=d["motif"], diagnostic_admission=d["diagnostic_admission"] or "",
                medecin_referent=request.user if request.user.role in {
                    "MEDECIN", "CHIRURGIEN"} else None,
                par=request.user,
            )
        except ErreurHospitalisation as exc:
            form.add_error(None, str(exc))
            return self.render_to_response(self.get_context_data(form=form))
        HistoriqueAction.enregistrer(
            utilisateur=request.user, action=HistoriqueAction.Action.CREATION,
            objet=sejour, description=f"Admission — {self.patient.nom_complet}",
        )
        messages.success(request, _("Patient admis. Séjour %(r)s.") % {"r": sejour.reference})
        return redirect("hospitalisation:detail", pk=sejour.pk)


@require_POST
def note_ajouter(request, pk):
    sejour = get_object_or_404(Hospitalisation, pk=pk)
    if not request.user.has_perm("hospitalisation.add_notesuivi"):
        messages.error(request, _("Action non autorisée."))
        return redirect("hospitalisation:detail", pk=pk)
    form = NoteSuiviForm(request.POST)
    if form.is_valid():
        note = form.save(commit=False)
        note.hospitalisation = sejour
        note.auteur = request.user
        note.save()
        messages.success(request, _("Note de suivi ajoutée."))
    else:
        messages.error(request, _("Formulaire invalide."))
    return redirect("hospitalisation:detail", pk=pk)


@require_POST
def sejour_transferer(request, pk):
    sejour = get_object_or_404(Hospitalisation, pk=pk)
    if not request.user.has_perm("hospitalisation.change_hospitalisation"):
        messages.error(request, _("Action non autorisée."))
        return redirect("hospitalisation:detail", pk=pk)
    form = TransfertForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Sélection de lit invalide."))
        return redirect("hospitalisation:detail", pk=pk)
    try:
        transferer(hospitalisation=sejour, nouveau_lit=form.cleaned_data["nouveau_lit"],
                   motif=form.cleaned_data["motif"], par=request.user)
    except ErreurHospitalisation as exc:
        messages.error(request, str(exc))
        return redirect("hospitalisation:detail", pk=pk)
    HistoriqueAction.enregistrer(
        utilisateur=request.user, action=HistoriqueAction.Action.MODIFICATION,
        objet=sejour, description=f"Transfert de lit — {sejour.reference}",
    )
    messages.success(request, _("Patient transféré."))
    return redirect("hospitalisation:detail", pk=pk)


@require_POST
def sejour_sortie(request, pk):
    sejour = get_object_or_404(Hospitalisation, pk=pk)
    if not request.user.has_perm("hospitalisation.change_hospitalisation"):
        messages.error(request, _("Action non autorisée."))
        return redirect("hospitalisation:detail", pk=pk)
    form = SortieForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Renseignez le mode de sortie et le compte-rendu."))
        return redirect("hospitalisation:detail", pk=pk)
    try:
        prononcer_sortie(
            hospitalisation=sejour, mode_sortie=form.cleaned_data["mode_sortie"],
            compte_rendu=form.cleaned_data["compte_rendu"],
            consignes_sortie=form.cleaned_data["consignes_sortie"] or "",
            par=request.user,
        )
    except ErreurHospitalisation as exc:
        messages.error(request, str(exc))
        return redirect("hospitalisation:detail", pk=pk)
    HistoriqueAction.enregistrer(
        utilisateur=request.user, action=HistoriqueAction.Action.MODIFICATION,
        objet=sejour, description=f"Sortie — {sejour.reference}",
    )
    messages.success(request, _("Sortie enregistrée."))
    return redirect("hospitalisation:detail", pk=pk)
