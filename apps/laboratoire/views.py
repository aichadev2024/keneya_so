"""Vues gabarit du module laboratoire / imagerie (CDC 4.6)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, TemplateView

from apps.consultations.models import Consultation
from apps.core.models import HistoriqueAction
from apps.patients.models import Patient

from . import services
from .forms import (
    AnnulationDemandeForm,
    DemandeExamenForm,
    ResultatBiologieForm,
    ResultatImagerieForm,
)
from .models import Categorie, DemandeExamen, LigneExamen

_CATEGORIE_PAR_ROLE = {"LABORANTIN": Categorie.BIOLOGIE, "RADIOLOGUE": Categorie.IMAGERIE}


def _audit(request, action, objet, description):
    HistoriqueAction.enregistrer(utilisateur=request.user, action=action, objet=objet,
                                 description=description)


class DemandeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "laboratoire.view_demandeexamen"
    template_name = "laboratoire/liste.html"
    context_object_name = "demandes"
    paginate_by = 25

    def get_queryset(self):
        qs = DemandeExamen.objects.select_related("patient", "prescripteur")
        cat_role = _CATEGORIE_PAR_ROLE.get(self.request.user.role)
        if cat_role:
            qs = qs.filter(categorie=cat_role)
        self.q = self.request.GET.get("q", "").strip()
        self.statut = self.request.GET.get("statut", "")
        self.mes = self.request.GET.get("mes") == "1"
        if self.q:
            qs = qs.filter(
                Q(reference__icontains=self.q)
                | Q(patient__nom__icontains=self.q)
                | Q(patient__numero_dossier__icontains=self.q)
            )
        if self.statut:
            qs = qs.filter(statut=self.statut)
        elif self.request.GET.get("toutes") != "1":
            qs = qs.exclude(statut__in=[DemandeExamen.Statut.VALIDEE,
                                        DemandeExamen.Statut.ANNULEE])
        if self.mes:
            qs = qs.filter(prescripteur=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(q=self.q, statut=self.statut, mes=self.mes,
                   statuts=DemandeExamen.Statut.choices)
        return ctx


class DemandeCreateView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = "laboratoire.add_demandeexamen"
    template_name = "laboratoire/demande.html"

    def dispatch(self, request, *args, **kwargs):
        self.patient = get_object_or_404(Patient, pk=kwargs["patient_pk"])
        cid = request.GET.get("consultation")
        self.consultation = (Consultation.objects.filter(pk=cid,
                                                         patient=self.patient).first()
                             if cid else None)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["patient"] = self.patient
        ctx["consultation"] = self.consultation
        ctx.setdefault("form", DemandeExamenForm())
        return ctx

    def post(self, request, *args, **kwargs):
        form = DemandeExamenForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        d = form.cleaned_data
        try:
            demande = services.creer_demande(
                patient=self.patient, prescripteur=request.user,
                categorie=d["categorie"], types_examens=list(d["types_examens"]),
                consultation=self.consultation, priorite=d["priorite"],
                renseignements_cliniques=d["renseignements_cliniques"], par=request.user,
            )
        except services.ErreurLaboratoire as exc:
            form.add_error(None, str(exc))
            return self.render_to_response(self.get_context_data(form=form))
        _audit(request, HistoriqueAction.Action.CREATION, demande,
               f"Demande d'examen — {self.patient.nom_complet}")
        messages.success(request, _("Demande d'examen enregistrée."))
        return redirect("laboratoire:detail", pk=demande.pk)


class DemandeDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "laboratoire.view_demandeexamen"
    model = DemandeExamen
    template_name = "laboratoire/detail.html"
    context_object_name = "demande"

    def get_queryset(self):
        return super().get_queryset().select_related("patient", "prescripteur",
                                                     "consultation").prefetch_related(
            "lignes__type_examen", "lignes__resultat")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        d = self.object
        u = self.request.user
        est_bio = d.categorie == Categorie.BIOLOGIE
        ctx["form_resultat_classe"] = "bio" if est_bio else "imagerie"
        ctx["form_resultat"] = (ResultatBiologieForm() if est_bio
                                else ResultatImagerieForm())
        ctx["form_annulation"] = AnnulationDemandeForm()
        ctx["peut_saisir"] = u.has_perm("laboratoire.add_resultat")
        ctx["peut_valider"] = u.has_perm("laboratoire.change_demandeexamen")
        return ctx


class MesResultatsView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "laboratoire.view_demandeexamen"
    template_name = "laboratoire/mes_resultats.html"
    context_object_name = "demandes"

    def get_queryset(self):
        return (DemandeExamen.objects
                .filter(prescripteur=self.request.user,
                        statut=DemandeExamen.Statut.VALIDEE)
                .select_related("patient")[:50])


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
@require_POST
def saisir_resultat(request, pk, ligne_pk):
    demande = get_object_or_404(DemandeExamen, pk=pk)
    ligne = get_object_or_404(LigneExamen, pk=ligne_pk, demande=demande)
    if not request.user.has_perm("laboratoire.add_resultat"):
        messages.error(request, _("Action non autorisée.")); return redirect("laboratoire:detail", pk=pk)

    est_bio = demande.categorie == Categorie.BIOLOGIE
    form = (ResultatBiologieForm(request.POST) if est_bio
            else ResultatImagerieForm(request.POST, request.FILES))
    if not form.is_valid():
        messages.error(request, _("Formulaire de résultat invalide."))
        return redirect("laboratoire:detail", pk=pk)
    d = form.cleaned_data
    try:
        if est_bio:
            services.saisir_resultat(ligne=ligne, par=request.user, valeur=d["valeur"],
                                     interpretation=d["interpretation"],
                                     commentaire=d["commentaire"])
        else:
            services.saisir_resultat(ligne=ligne, par=request.user,
                                     compte_rendu=d["compte_rendu"],
                                     conclusion=d["conclusion"], fichier=d.get("fichier"),
                                     commentaire=d["commentaire"])
    except services.ErreurLaboratoire as exc:
        messages.error(request, str(exc)); return redirect("laboratoire:detail", pk=pk)
    _audit(request, HistoriqueAction.Action.MODIFICATION, demande,
           f"Résultat saisi — {ligne.type_examen.libelle} ({demande.reference})")
    messages.success(request, _("Résultat enregistré."))
    return redirect("laboratoire:detail", pk=pk)


@require_POST
def demande_valider(request, pk):
    demande = get_object_or_404(DemandeExamen, pk=pk)
    if not request.user.has_perm("laboratoire.change_demandeexamen"):
        messages.error(request, _("Action non autorisée.")); return redirect("laboratoire:detail", pk=pk)
    try:
        services.valider_demande(demande=demande, par=request.user)
    except services.ErreurLaboratoire as exc:
        messages.error(request, str(exc)); return redirect("laboratoire:detail", pk=pk)
    _audit(request, HistoriqueAction.Action.MODIFICATION, demande,
           f"Résultats validés — {demande.reference} (prescripteur notifié)")
    messages.success(request, _("Résultats validés. Le prescripteur a été notifié."))
    return redirect("laboratoire:detail", pk=pk)


@require_POST
def demande_annuler(request, pk):
    demande = get_object_or_404(DemandeExamen, pk=pk)
    if not request.user.has_perm("laboratoire.change_demandeexamen"):
        messages.error(request, _("Action non autorisée.")); return redirect("laboratoire:detail", pk=pk)
    form = AnnulationDemandeForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Le motif est obligatoire.")); return redirect("laboratoire:detail", pk=pk)
    try:
        services.annuler_demande(demande=demande, motif=form.cleaned_data["motif"],
                                 par=request.user)
    except services.ErreurLaboratoire as exc:
        messages.error(request, str(exc)); return redirect("laboratoire:detail", pk=pk)
    messages.success(request, _("Demande annulée."))
    return redirect("laboratoire:detail", pk=pk)
