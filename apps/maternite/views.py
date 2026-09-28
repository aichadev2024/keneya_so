"""Vues gabarit du module Maternité — espace de la sage-femme."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from apps.consultations.models import Constantes, Consultation
from apps.core.models import HistoriqueAction
from apps.patients.models import Patient

from .forms import DossierGrossesseForm, TerminerGrossesseForm, VisitePrenataleForm
from .models import ConsultationPrenatale, DossierGrossesse
from .services import alertes_dossier, alertes_visite

MOTIF_CPN = "Consultation prénatale"


class AccueilMaterniteView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """Tableau de bord de la sage-femme : qui voir aujourd'hui, qui relancer, qui va accoucher."""

    permission_required = "maternite.view_dossiergrossesse"
    template_name = "maternite/accueil.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        aujourdhui = timezone.localdate()
        en_cours = (DossierGrossesse.objects.filter(statut=DossierGrossesse.Statut.EN_COURS)
                    .select_related("patient"))
        # DPA = DDR + 280 j  =>  DPA dans les 30 prochains jours  <=>  DDR entre -280 et -250 j.
        ctx.update({
            "nb_en_cours": en_cours.count(),
            "rdv_aujourdhui": en_cours.filter(prochain_rdv=aujourdhui),
            "rdv_semaine": en_cours.filter(
                prochain_rdv__gt=aujourdhui,
                prochain_rdv__lte=aujourdhui + timedelta(days=7)).order_by("prochain_rdv"),
            "rdv_manques": en_cours.filter(prochain_rdv__lt=aujourdhui).order_by("prochain_rdv"),
            "sans_rdv": en_cours.filter(prochain_rdv__isnull=True),
            "accouchements_proches": en_cours.filter(
                date_dernieres_regles__gte=aujourdhui - timedelta(days=280),
                date_dernieres_regles__lte=aujourdhui - timedelta(days=250),
            ).order_by("date_dernieres_regles"),
            "dpa_depassee": en_cours.filter(
                date_dernieres_regles__lt=aujourdhui - timedelta(days=280)),
        })
        return ctx


class DossierListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "maternite.view_dossiergrossesse"
    template_name = "maternite/dossier_liste.html"
    context_object_name = "dossiers"
    paginate_by = 25

    def get_queryset(self):
        qs = DossierGrossesse.objects.select_related("patient")
        self.q = self.request.GET.get("q", "").strip()
        self.statut = self.request.GET.get("statut", "EN_COURS")
        if self.q:
            qs = qs.filter(
                Q(reference__icontains=self.q) | Q(patient__nom__icontains=self.q)
                | Q(patient__prenom__icontains=self.q)
                | Q(patient__numero_dossier__icontains=self.q))
        if self.statut in DossierGrossesse.Statut.values:
            qs = qs.filter(statut=self.statut)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({"q": self.q, "statut": self.statut,
                    "statuts": DossierGrossesse.Statut.choices})
        return ctx


class DossierCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "maternite.add_dossiergrossesse"
    form_class = DossierGrossesseForm
    template_name = "maternite/dossier_formulaire.html"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient, pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        if self.patient.sexe != Patient.Sexe.FEMININ:
            messages.error(request, _("Un dossier de grossesse ne peut concerner qu'une patiente."))
            return redirect("patients:detail", pk=self.patient.pk)
        existant = self.patient.grossesses.filter(statut=DossierGrossesse.Statut.EN_COURS).first()
        if existant:
            messages.info(request, _("Cette patiente a déjà une grossesse en cours."))
            return redirect("maternite:dossier", pk=existant.pk)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if self.patient.sexe != Patient.Sexe.FEMININ or self.patient.grossesses.filter(
                statut=DossierGrossesse.Statut.EN_COURS).exists():
            return redirect("maternite:dossier_nouveau", patient_pk=self.patient.pk)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.patient = self.patient
        form.instance.sage_femme = self.request.user
        form.instance.cree_par = self.request.user
        form.instance.modifie_par = self.request.user
        response = super().form_valid(form)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user, action=HistoriqueAction.Action.CREATION,
            objet=self.object, description=f"Dossier de grossesse — {self.patient.nom_complet}")
        messages.success(self.request, _("Dossier de grossesse ouvert."))
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["patient"] = self.patient
        return ctx

    def get_success_url(self):
        return reverse("maternite:dossier", args=[self.object.pk])


class DossierDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "maternite.view_dossiergrossesse"
    model = DossierGrossesse
    template_name = "maternite/dossier_detail.html"
    context_object_name = "dossier"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        dossier = self.object
        ctx["visites"] = dossier.visites.select_related("consultation").order_by("-numero")
        ctx["alertes"] = alertes_dossier(dossier)
        return ctx


class DossierUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "maternite.change_dossiergrossesse"
    model = DossierGrossesse
    form_class = DossierGrossesseForm
    template_name = "maternite/dossier_formulaire.html"

    def form_valid(self, form):
        form.instance.modifie_par = self.request.user
        messages.success(self.request, _("Dossier mis à jour."))
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["patient"] = self.object.patient
        return ctx

    def get_success_url(self):
        return reverse("maternite:dossier", args=[self.object.pk])


class DossierTerminerView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """Clôture du suivi : accouchement ou interruption de la grossesse."""

    permission_required = "maternite.change_dossiergrossesse"
    model = DossierGrossesse
    form_class = TerminerGrossesseForm
    template_name = "maternite/dossier_terminer.html"

    def dispatch(self, request, *args, **kwargs):
        dossier = get_object_or_404(DossierGrossesse, pk=kwargs["pk"])
        if dossier.statut != DossierGrossesse.Statut.EN_COURS:
            messages.info(request, _("Cette grossesse est déjà clôturée."))
            return redirect("maternite:dossier", pk=dossier.pk)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.modifie_par = self.request.user
        form.instance.prochain_rdv = None
        messages.success(self.request, _("Suivi de grossesse clôturé."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("maternite:dossier", args=[self.object.pk])


class VisiteBaseMixin(LoginRequiredMixin, PermissionRequiredMixin):
    form_class = VisitePrenataleForm
    template_name = "maternite/visite_formulaire.html"

    def _enregistrer_constantes(self, consultation, data):
        constantes, _cree = Constantes.objects.get_or_create(consultation=consultation)
        for champ in VisitePrenataleForm.CHAMPS_CONSTANTES:
            setattr(constantes, champ, data.get(champ))
        constantes.releve_par = self.request.user
        constantes.save()


class VisiteCreateView(VisiteBaseMixin, CreateView):
    permission_required = ("maternite.add_consultationprenatale", "consultations.add_consultation",
                           "consultations.add_constantes")

    def dispatch(self, request, *args, **kwargs):
        self.dossier = get_object_or_404(DossierGrossesse, pk=kwargs["dossier_pk"])
        if self.dossier.statut != DossierGrossesse.Statut.EN_COURS:
            messages.error(request, _("Cette grossesse est clôturée : plus de nouvelle visite."))
            return redirect("maternite:dossier", pk=self.dossier.pk)
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        consultation = Consultation.objects.create(
            patient=self.dossier.patient, praticien=self.request.user, motif=MOTIF_CPN,
            cree_par=self.request.user, modifie_par=self.request.user)
        visite = form.save(commit=False)
        visite.dossier = self.dossier
        visite.consultation = consultation
        visite.save()
        self._enregistrer_constantes(consultation, form.cleaned_data)
        self.object = visite
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user, action=HistoriqueAction.Action.CREATION,
            objet=visite, description=f"CPN {visite.numero} — {self.dossier.patient.nom_complet}")
        messages.success(self.request, _("Consultation prénatale enregistrée."))
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["dossier"] = self.dossier
        return ctx

    def get_success_url(self):
        return reverse("maternite:visite", args=[self.object.pk])


class VisiteUpdateView(VisiteBaseMixin, UpdateView):
    permission_required = ("maternite.change_consultationprenatale",
                           "consultations.change_constantes")
    model = ConsultationPrenatale

    def dispatch(self, request, *args, **kwargs):
        visite = get_object_or_404(ConsultationPrenatale, pk=kwargs["pk"])
        if visite.consultation.statut != Consultation.Statut.EN_COURS:
            messages.error(request, _("La consultation est clôturée : elle n'est plus modifiable."))
            return redirect("maternite:visite", pk=visite.pk)
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        visite = form.save()
        self._enregistrer_constantes(visite.consultation, form.cleaned_data)
        visite.dossier.actualiser_prochain_rdv()
        messages.success(self.request, _("Consultation prénatale mise à jour."))
        self.object = visite
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["dossier"] = self.object.dossier
        return ctx

    def get_success_url(self):
        return reverse("maternite:visite", args=[self.object.pk])


class VisiteDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "maternite.view_consultationprenatale"
    model = ConsultationPrenatale
    template_name = "maternite/visite_detail.html"
    context_object_name = "visite"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        visite = self.object
        ctx["dossier"] = visite.dossier
        ctx["alertes"] = alertes_visite(visite)
        ctx["consultation"] = visite.consultation
        ctx["modifiable"] = visite.consultation.statut == Consultation.Statut.EN_COURS
        return ctx
