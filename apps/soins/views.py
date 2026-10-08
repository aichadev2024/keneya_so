"""Vues gabarit du module Soins (infirmier, chirurgien)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView

from apps.core.models import HistoriqueAction
from apps.patients.models import Patient

from .forms import SoinForm
from .models import Soin


class SoinListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "soins.view_soin"
    template_name = "soins/liste.html"
    context_object_name = "soins"
    paginate_by = 25

    def get_queryset(self):
        qs = Soin.objects.select_related("patient", "soignant")
        self.q = self.request.GET.get("q", "").strip()
        self.type_soin = self.request.GET.get("type", "")
        if self.q:
            qs = qs.filter(Q(reference__icontains=self.q)
                           | Q(patient__nom__icontains=self.q)
                           | Q(patient__prenom__icontains=self.q)
                           | Q(patient__numero_dossier__icontains=self.q))
        if self.type_soin in Soin.Type.values:
            qs = qs.filter(type_soin=self.type_soin)
        if self.request.GET.get("mes") == "1":
            qs = qs.filter(soignant=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({"q": self.q, "type_soin": self.type_soin, "types": Soin.Type.choices,
                    "mes": self.request.GET.get("mes") == "1"})
        return ctx


class SoinCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "soins.add_soin"
    form_class = SoinForm
    template_name = "soins/formulaire.html"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient, pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["patient"] = self.patient
        return kw

    def form_valid(self, form):
        form.instance.patient = self.patient
        form.instance.soignant = self.request.user
        form.instance.cree_par = self.request.user
        form.instance.modifie_par = self.request.user
        response = super().form_valid(form)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user, action=HistoriqueAction.Action.CREATION,
            objet=self.object,
            description=f"Soin {self.object.get_type_soin_display()} — {self.patient.nom_complet}")
        messages.success(self.request, _("Soin enregistré."))
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["patient"] = self.patient
        return ctx

    def get_success_url(self):
        return reverse("soins:detail", args=[self.object.pk])


class SoinDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "soins.view_soin"
    template_name = "soins/detail.html"
    context_object_name = "soin"

    def get_queryset(self):
        return Soin.objects.select_related("patient", "soignant", "hospitalisation",
                                           "intervention")
