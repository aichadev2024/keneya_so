"""Vues gabarit du module bloc opératoire (CDC section 5)."""

from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView

from apps.core.models import HistoriqueAction
from apps.patients.models import Patient

from . import services, stats
from .forms import (
    AnnulationForm,
    ChecklistValidationForm,
    CompteRenduForm,
    DemandeInterventionForm,
    FaisabiliteAnesthesieForm,
    IncidentsForm,
    MembreEquipeForm,
    PlanificationForm,
)
from .models import (
    CompteRenduOperatoire,
    EtapeChecklist,
    Intervention,
    MembreEquipe,
    SalleOperatoire,
)


def _audit(request, action, objet, description):
    HistoriqueAction.enregistrer(utilisateur=request.user, action=action, objet=objet,
                                 description=description)


class PlanningView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """Planning du bloc par salle pour une journée (CDC 5.3.1)."""

    permission_required = "bloc_operatoire.view_intervention"
    template_name = "bloc_operatoire/planning.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        jour_str = self.request.GET.get("date")
        jour = (datetime.strptime(jour_str, "%Y-%m-%d").date() if jour_str
                else timezone.localdate())
        debut = timezone.make_aware(datetime.combine(jour, time.min))
        fin = timezone.make_aware(datetime.combine(jour, time.max))

        planning = []
        for salle in SalleOperatoire.objects.filter(actif=True):
            interventions = (
                salle.interventions.filter(
                    date_heure_debut_prevue__range=(debut, fin),
                    statut__in=[Intervention.Statut.PLANIFIEE, Intervention.Statut.EN_COURS,
                                Intervention.Statut.TERMINEE],
                )
                .select_related("patient", "type_intervention", "chirurgien_principal")
                .order_by("date_heure_debut_prevue")
            )
            planning.append({"salle": salle, "interventions": interventions})

        ctx["jour"] = jour
        ctx["jour_prec"] = jour.fromordinal(jour.toordinal() - 1)
        ctx["jour_suiv"] = jour.fromordinal(jour.toordinal() + 1)
        ctx["planning"] = planning
        ctx["a_planifier"] = (
            Intervention.objects.filter(statut=Intervention.Statut.DEMANDEE)
            .select_related("patient", "type_intervention")
            .order_by("-niveau_urgence", "date_demande")
        )
        return ctx


class InterventionListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "bloc_operatoire.view_intervention"
    template_name = "bloc_operatoire/liste.html"
    context_object_name = "interventions"
    paginate_by = 25

    def get_queryset(self):
        qs = Intervention.objects.select_related("patient", "type_intervention", "salle",
                                                 "chirurgien_principal")
        self.q = self.request.GET.get("q", "").strip()
        self.statut = self.request.GET.get("statut", "")
        if self.q:
            qs = qs.filter(
                Q(reference__icontains=self.q)
                | Q(patient__nom__icontains=self.q)
                | Q(patient__numero_dossier__icontains=self.q)
                | Q(type_intervention__libelle__icontains=self.q)
            )
        if self.statut:
            qs = qs.filter(statut=self.statut)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.q
        ctx["statut"] = self.statut
        ctx["statuts"] = Intervention.Statut.choices
        return ctx


class DemandeInterventionView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "bloc_operatoire.add_intervention"
    form_class = DemandeInterventionForm
    template_name = "bloc_operatoire/demande.html"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient, pk=kwargs["patient_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["patient"] = self.patient
        return kw

    def form_valid(self, form):
        form.instance.patient = self.patient
        form.instance.demandeur = self.request.user
        form.instance.cree_par = self.request.user
        form.instance.modifie_par = self.request.user
        response = super().form_valid(form)
        _audit(self.request, HistoriqueAction.Action.CREATION, self.object,
               f"Demande d'intervention — {self.patient.nom_complet}")
        messages.success(self.request, _("Demande d'intervention enregistrée."))
        return response

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["patient"] = self.patient
        return ctx

    def get_success_url(self):
        return reverse("bloc_operatoire:detail", args=[self.object.pk])


class InterventionDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "bloc_operatoire.view_intervention"
    model = Intervention
    template_name = "bloc_operatoire/detail.html"
    context_object_name = "intervention"

    def get_queryset(self):
        return super().get_queryset().select_related(
            "patient", "type_intervention", "salle", "chirurgien_principal"
        ).prefetch_related("equipe__utilisateur", "checklist")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        i = self.object
        checklist = {e.temps: e for e in i.checklist.all()}
        ctx["checklist"] = [checklist[t] for t in EtapeChecklist.ORDRE if t in checklist]
        ctx["alertes"] = services.alertes_intervention(i)
        ctx["form_planif"] = PlanificationForm(initial={
            "duree_estimee_min": i.duree_estimee_min})
        ctx["form_anesth"] = FaisabiliteAnesthesieForm(initial={
            "protocole_anesthesie": i.protocole_anesthesie})
        ctx["form_membre"] = MembreEquipeForm()
        ctx["form_annulation"] = AnnulationForm()
        ctx["form_incidents"] = IncidentsForm()
        ctx["form_checklist"] = ChecklistValidationForm()
        ctx["form_cr"] = CompteRenduForm(
            instance=getattr(i, "compte_rendu", None))
        ctx["cr"] = getattr(i, "compte_rendu", None)
        u = self.request.user
        ctx["peut_planifier"] = u.has_perm("bloc_operatoire.change_intervention")
        ctx["peut_checklist"] = u.has_perm("bloc_operatoire.change_etapechecklist")
        ctx["peut_cr"] = u.has_perm("bloc_operatoire.add_compterenduoperatoire")
        ctx["peut_equipe"] = u.has_perm("bloc_operatoire.add_membreequipe")
        return ctx


class IndicateursView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "bloc_operatoire.view_intervention"
    template_name = "bloc_operatoire/indicateurs.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tb"] = stats.tableau_de_bord()
        return ctx


# --------------------------------------------------------------------------- #
# Actions (POST)
# --------------------------------------------------------------------------- #
def _get(pk):
    return get_object_or_404(Intervention, pk=pk)


@require_POST
def planifier(request, pk):
    intervention = _get(pk)
    if not request.user.has_perm("bloc_operatoire.change_intervention"):
        messages.error(request, _("Action non autorisée.")); return redirect("bloc_operatoire:detail", pk=pk)
    form = PlanificationForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Formulaire de planification invalide."))
        return redirect("bloc_operatoire:detail", pk=pk)
    try:
        res = services.planifier(
            intervention=intervention, salle=form.cleaned_data["salle"],
            debut=form.debut(), duree_estimee_min=form.cleaned_data["duree_estimee_min"],
            par=request.user, forcer=form.cleaned_data["forcer"],
        )
    except services.ErreurBloc as exc:
        messages.error(request, str(exc)); return redirect("bloc_operatoire:detail", pk=pk)
    _audit(request, HistoriqueAction.Action.MODIFICATION, intervention,
           f"Planification {intervention.reference}")
    if res["reports"]:
        messages.warning(request, _("%(n)d intervention(s) programmée(s) reportée(s) "
                                    "pour priorité extrême urgence.")
                         % {"n": len(res["reports"])})
    messages.success(request, _("Intervention planifiée."))
    return redirect("bloc_operatoire:detail", pk=pk)


@require_POST
def valider_faisabilite(request, pk):
    intervention = _get(pk)
    if not request.user.has_perm("bloc_operatoire.change_intervention"):
        messages.error(request, _("Action non autorisée.")); return redirect("bloc_operatoire:detail", pk=pk)
    form = FaisabiliteAnesthesieForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Renseignez le protocole d'anesthésie."))
        return redirect("bloc_operatoire:detail", pk=pk)
    intervention.faisabilite_anesthesique_validee = True
    intervention.protocole_anesthesie = form.cleaned_data["protocole_anesthesie"]
    intervention.anesthesiste_validateur = request.user
    intervention.modifie_par = request.user
    intervention.save(update_fields=["faisabilite_anesthesique_validee",
                                     "protocole_anesthesie", "anesthesiste_validateur",
                                     "modifie_par", "modifie_le"])
    _audit(request, HistoriqueAction.Action.MODIFICATION, intervention,
           f"Faisabilité anesthésique validée — {intervention.reference}")
    messages.success(request, _("Faisabilité anesthésique validée."))
    return redirect("bloc_operatoire:detail", pk=pk)


@require_POST
def membre_ajouter(request, pk):
    intervention = _get(pk)
    if not request.user.has_perm("bloc_operatoire.add_membreequipe"):
        messages.error(request, _("Action non autorisée.")); return redirect("bloc_operatoire:detail", pk=pk)
    form = MembreEquipeForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Sélection invalide."))
        return redirect("bloc_operatoire:detail", pk=pk)
    try:
        services.ajouter_membre(
            intervention=intervention, utilisateur=form.cleaned_data["utilisateur"],
            role=form.cleaned_data["role"], par=request.user,
            forcer=form.cleaned_data["forcer"],
        )
    except services.ErreurBloc as exc:
        messages.error(request, str(exc)); return redirect("bloc_operatoire:detail", pk=pk)
    messages.success(request, _("Membre ajouté à l'équipe (notification envoyée)."))
    return redirect("bloc_operatoire:detail", pk=pk)


@require_POST
def membre_retirer(request, pk, membre_pk):
    intervention = _get(pk)
    if not request.user.has_perm("bloc_operatoire.delete_membreequipe"):
        messages.error(request, _("Action non autorisée.")); return redirect("bloc_operatoire:detail", pk=pk)
    MembreEquipe.objects.filter(pk=membre_pk, intervention=intervention).delete()
    messages.success(request, _("Membre retiré."))
    return redirect("bloc_operatoire:detail", pk=pk)


@require_POST
def checklist_valider(request, pk, temps):
    intervention = _get(pk)
    if not request.user.has_perm("bloc_operatoire.change_etapechecklist"):
        messages.error(request, _("Action non autorisée.")); return redirect("bloc_operatoire:detail", pk=pk)
    form = ChecklistValidationForm(request.POST)
    commentaire = form.cleaned_data.get("commentaire", "") if form.is_valid() else ""
    try:
        services.valider_etape(intervention=intervention, temps=temps,
                               utilisateur=request.user, commentaire=commentaire)
    except (services.ErreurBloc, ValueError) as exc:
        messages.error(request, str(exc)); return redirect("bloc_operatoire:detail", pk=pk)
    _audit(request, HistoriqueAction.Action.MODIFICATION, intervention,
           f"Checklist {temps} validée — {intervention.reference}")
    messages.success(request, _("Étape de checklist validée."))
    return redirect("bloc_operatoire:detail", pk=pk)


@require_POST
def etape_peroperatoire(request, pk, etape):
    intervention = _get(pk)
    if not request.user.has_perm("bloc_operatoire.change_intervention"):
        messages.error(request, _("Action non autorisée.")); return redirect("bloc_operatoire:detail", pk=pk)
    try:
        if etape == "entree":
            services.entree_en_salle(intervention=intervention, par=request.user)
        elif etape == "incision":
            services.pointer_incision(intervention=intervention, par=request.user)
        elif etape == "terminer":
            form = IncidentsForm(request.POST)
            incidents = form.cleaned_data["incidents"] if form.is_valid() else ""
            services.terminer(intervention=intervention, incidents=incidents,
                              par=request.user)
        else:
            messages.error(request, _("Étape inconnue.")); return redirect("bloc_operatoire:detail", pk=pk)
    except services.ErreurBloc as exc:
        messages.error(request, str(exc)); return redirect("bloc_operatoire:detail", pk=pk)
    _audit(request, HistoriqueAction.Action.MODIFICATION, intervention,
           f"Per-opératoire ({etape}) — {intervention.reference}")
    messages.success(request, _("Étape enregistrée."))
    return redirect("bloc_operatoire:detail", pk=pk)


@require_POST
def intervention_annuler(request, pk):
    intervention = _get(pk)
    if not request.user.has_perm("bloc_operatoire.change_intervention"):
        messages.error(request, _("Action non autorisée.")); return redirect("bloc_operatoire:detail", pk=pk)
    form = AnnulationForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Le motif est obligatoire."))
        return redirect("bloc_operatoire:detail", pk=pk)
    try:
        services.annuler(intervention=intervention, motif=form.cleaned_data["motif"],
                         par=request.user, reporter=form.cleaned_data["reporter"])
    except services.ErreurBloc as exc:
        messages.error(request, str(exc)); return redirect("bloc_operatoire:detail", pk=pk)
    _audit(request, HistoriqueAction.Action.MODIFICATION, intervention,
           f"{'Report' if form.cleaned_data['reporter'] else 'Annulation'} "
           f"{intervention.reference} : {form.cleaned_data['motif']}")
    messages.success(request, _("Intervention mise à jour."))
    return redirect("bloc_operatoire:detail", pk=pk)


@require_POST
def compte_rendu_enregistrer(request, pk):
    intervention = _get(pk)
    if not request.user.has_perm("bloc_operatoire.add_compterenduoperatoire"):
        messages.error(request, _("Action non autorisée.")); return redirect("bloc_operatoire:detail", pk=pk)
    cr = getattr(intervention, "compte_rendu", None)
    form = CompteRenduForm(request.POST, instance=cr)
    if not form.is_valid():
        messages.error(request, _("La technique opératoire est obligatoire."))
        return redirect("bloc_operatoire:detail", pk=pk)
    cr = form.save(commit=False)
    cr.intervention = intervention
    if not cr.pk:
        cr.redige_par = request.user
        cr.cree_par = request.user
    cr.modifie_par = request.user
    cr.save()
    _audit(request, HistoriqueAction.Action.MODIFICATION, intervention,
           f"Compte-rendu opératoire — {intervention.reference}")
    messages.success(request, _("Compte-rendu opératoire enregistré."))
    return redirect("bloc_operatoire:detail", pk=pk)
