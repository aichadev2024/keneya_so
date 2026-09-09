"""Vues gabarit du module consultations (CDC 4.2 / 4.3)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.models import HistoriqueAction
from apps.patients.models import Patient

from .forms import ConstantesForm, ConsultationForm, LigneOrdonnanceForm, OrdonnanceForm
from .models import Consultation, LigneOrdonnance, Ordonnance
from .services import alertes_prescription


class ConsultationListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "consultations.view_consultation"
    template_name = "consultations/liste.html"
    context_object_name = "consultations"
    paginate_by = 25

    def get_queryset(self):
        qs = Consultation.objects.select_related("patient", "praticien")
        self.q = self.request.GET.get("q", "").strip()
        if self.q:
            qs = qs.filter(
                Q(reference__icontains=self.q)
                | Q(patient__nom__icontains=self.q)
                | Q(patient__prenom__icontains=self.q)
                | Q(patient__numero_dossier__icontains=self.q)
                | Q(motif__icontains=self.q)
            )
        if self.request.GET.get("mes") == "1":
            qs = qs.filter(praticien=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.q
        ctx["mes"] = self.request.GET.get("mes") == "1"
        return ctx


class ConsultationCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "consultations.add_consultation"
    form_class = ConsultationForm
    template_name = "consultations/formulaire.html"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient, pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.patient = self.patient
        form.instance.praticien = self.request.user
        form.instance.cree_par = self.request.user
        form.instance.modifie_par = self.request.user
        response = super().form_valid(form)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user,
            action=HistoriqueAction.Action.CREATION,
            objet=self.object,
            description=f"Consultation — {self.patient.nom_complet}",
        )
        messages.success(self.request, _("Consultation créée."))
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["patient"] = self.patient
        return ctx

    def get_success_url(self):
        return reverse("consultations:detail", args=[self.object.pk])


class ConsultationUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "consultations.change_consultation"
    model = Consultation
    form_class = ConsultationForm
    template_name = "consultations/formulaire.html"

    def form_valid(self, form):
        form.instance.modifie_par = self.request.user
        messages.success(self.request, _("Consultation mise à jour."))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["patient"] = self.object.patient
        return ctx

    def get_success_url(self):
        return reverse("consultations:detail", args=[self.object.pk])


class ConsultationDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "consultations.view_consultation"
    model = Consultation
    template_name = "consultations/detail.html"
    context_object_name = "consultation"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ordonnance = getattr(self.object, "ordonnance", None)
        ctx["ordonnance"] = ordonnance
        if ordonnance:
            ctx["alertes"] = alertes_prescription(ordonnance)
        return ctx


class ConstantesUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "consultations.change_constantes"
    form_class = ConstantesForm
    template_name = "consultations/constantes.html"

    def get_object(self, queryset=None):
        from .models import Constantes
        self.consultation = get_object_or_404(Consultation, pk=self.kwargs["pk"])
        obj, _created = Constantes.objects.get_or_create(consultation=self.consultation)
        return obj

    def form_valid(self, form):
        form.instance.releve_par = self.request.user
        messages.success(self.request, _("Constantes enregistrées."))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["consultation"] = self.consultation
        return ctx

    def get_success_url(self):
        return reverse("consultations:detail", args=[self.consultation.pk])


class OrdonnanceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "consultations.add_ordonnance"
    form_class = OrdonnanceForm
    template_name = "consultations/ordonnance_formulaire.html"

    def dispatch(self, request, *args, **kwargs):
        self.consultation = get_object_or_404(Consultation, pk=kwargs["pk"])
        if hasattr(self.consultation, "ordonnance"):
            return redirect("consultations:ordonnance", pk=self.consultation.ordonnance.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.consultation = self.consultation
        form.instance.prescripteur = self.request.user
        form.instance.cree_par = self.request.user
        form.instance.modifie_par = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, _("Ordonnance créée. Ajoutez les médicaments."))
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["consultation"] = self.consultation
        return ctx

    def get_success_url(self):
        return reverse("consultations:ordonnance", args=[self.object.pk])


class OrdonnanceDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "consultations.view_ordonnance"
    model = Ordonnance
    template_name = "consultations/ordonnance_detail.html"
    context_object_name = "ordonnance"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["alertes"] = alertes_prescription(self.object)
        ctx["form_ligne"] = LigneOrdonnanceForm()
        ctx["peut_modifier"] = (
            self.object.modifiable
            and self.request.user.has_perm("consultations.change_ordonnance")
        )
        return ctx


@require_POST
def ligne_ajouter(request, pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    if not request.user.has_perm("consultations.change_ordonnance"):
        messages.error(request, _("Action non autorisée."))
        return redirect("consultations:ordonnance", pk=pk)
    if not ordonnance.modifiable:
        messages.error(request, _("Cette ordonnance n'est plus modifiable."))
        return redirect("consultations:ordonnance", pk=pk)
    form = LigneOrdonnanceForm(request.POST)
    if form.is_valid():
        ligne = form.save(commit=False)
        ligne.ordonnance = ordonnance
        ligne.save()
        messages.success(request, _("Médicament ajouté à l'ordonnance."))
    else:
        messages.error(request, _("Formulaire invalide : %(err)s") % {"err": form.errors})
    return redirect("consultations:ordonnance", pk=pk)


@require_POST
def ligne_supprimer(request, pk, ligne_pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    if not request.user.has_perm("consultations.delete_ligneordonnance") \
            or not ordonnance.modifiable:
        messages.error(request, _("Action non autorisée."))
        return redirect("consultations:ordonnance", pk=pk)
    LigneOrdonnance.objects.filter(pk=ligne_pk, ordonnance=ordonnance).delete()
    messages.success(request, _("Ligne retirée."))
    return redirect("consultations:ordonnance", pk=pk)


@require_POST
def ordonnance_transmettre(request, pk):
    ordonnance = get_object_or_404(Ordonnance, pk=pk)
    if not request.user.has_perm("consultations.change_ordonnance"):
        messages.error(request, _("Action non autorisée."))
        return redirect("consultations:ordonnance", pk=pk)
    if not ordonnance.lignes.exists():
        messages.error(request, _("Ajoutez au moins un médicament avant de transmettre."))
        return redirect("consultations:ordonnance", pk=pk)

    ordonnance.transmettre()
    HistoriqueAction.enregistrer(
        utilisateur=request.user,
        action=HistoriqueAction.Action.MODIFICATION,
        objet=ordonnance,
        description=f"Ordonnance {ordonnance.reference} transmise à la pharmacie",
    )
    messages.success(request, _("Ordonnance transmise à la pharmacie."))
    return redirect("consultations:ordonnance", pk=pk)


@require_POST
def consultation_cloturer(request, pk):
    consultation = get_object_or_404(Consultation, pk=pk)
    if not request.user.has_perm("consultations.change_consultation"):
        messages.error(request, _("Action non autorisée."))
        return redirect("consultations:detail", pk=pk)
    consultation.statut = Consultation.Statut.CLOTUREE
    consultation.modifie_par = request.user
    consultation.save(update_fields=["statut", "modifie_par", "modifie_le"])
    messages.success(request, _("Consultation clôturée."))
    return redirect("consultations:detail", pk=pk)
