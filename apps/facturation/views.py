"""Vues gabarit du module facturation (CDC 4.8)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView

from apps.core.exports import ExportableListMixin
from apps.core.models import HistoriqueAction

from . import services
from .forms import AnnulationFactureForm, LigneFactureForm, PaiementForm, RelanceForm
from .models import Facture, LigneFacture, Tarif

_GENERATEURS = {
    "consultation": ("consultations", "Consultation", services.facturer_consultation),
    "hospitalisation": ("hospitalisation", "Hospitalisation",
                        services.facturer_hospitalisation),
    "intervention": ("bloc_operatoire", "Intervention", services.facturer_intervention),
    "dispensation": ("pharmacie", "Dispensation", services.facturer_dispensation),
    "examen": ("laboratoire", "DemandeExamen", services.facturer_demande_examen),
}


def _audit(request, action, objet, description):
    HistoriqueAction.enregistrer(utilisateur=request.user, action=action, objet=objet,
                                 description=description)


class FactureListView(LoginRequiredMixin, PermissionRequiredMixin,
                      ExportableListMixin, ListView):
    permission_required = "facturation.view_facture"
    template_name = "facturation/liste.html"
    context_object_name = "factures"
    paginate_by = 25
    export_titre = _("Factures")
    export_nom_fichier = "factures"

    def export_colonnes(self):
        return [str(_("Référence")), str(_("Patient")), str(_("Émission")),
                str(_("Total")), str(_("Part patient")), str(_("Reste")), str(_("Statut"))]

    def export_ligne(self, f):
        return [f.reference, f.patient.nom_complet, f.date_emission, f.montant_total,
                f.part_patient, f.reste_a_payer, f.get_statut_display()]

    def get_queryset(self):
        qs = Facture.objects.select_related("patient", "patient_assure__contrat__assurance")
        self.q = self.request.GET.get("q", "").strip()
        self.statut = self.request.GET.get("statut", "")
        self.retard = self.request.GET.get("retard") == "1"
        if self.q:
            qs = qs.filter(
                Q(reference__icontains=self.q)
                | Q(patient__nom__icontains=self.q)
                | Q(patient__numero_dossier__icontains=self.q)
            )
        if self.statut:
            qs = qs.filter(statut=self.statut)
        if self.retard:
            from datetime import date
            qs = qs.filter(statut__in=[Facture.Statut.EMISE, Facture.Statut.PARTIELLE],
                           date_echeance__lt=date.today())
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(q=self.q, statut=self.statut, retard=self.retard,
                   statuts=Facture.Statut.choices,
                   nb_retard=services.factures_en_retard().count())
        return ctx


class FactureDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "facturation.view_facture"
    model = Facture
    template_name = "facturation/detail.html"
    context_object_name = "facture"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        u = self.request.user
        ctx["form_paiement"] = PaiementForm()
        ctx["form_ligne"] = LigneFactureForm()
        ctx["form_relance"] = RelanceForm()
        ctx["form_annulation"] = AnnulationFactureForm()
        ctx["peut_gerer"] = u.has_perm("facturation.change_facture")
        ctx["peut_encaisser"] = u.has_perm("facturation.add_paiement")
        ctx["peut_relancer"] = u.has_perm("facturation.add_relance")
        return ctx


class ImpayesView(LoginRequiredMixin, PermissionRequiredMixin,
                  ExportableListMixin, ListView):
    permission_required = "facturation.view_facture"
    template_name = "facturation/impayes.html"
    context_object_name = "factures"
    export_titre = _("Factures impayées échues")
    export_nom_fichier = "impayes"

    def export_colonnes(self):
        return [str(_("Référence")), str(_("Patient")), str(_("Échéance")),
                str(_("Reste à payer")), str(_("Relances"))]

    def export_ligne(self, f):
        return [f.reference, f.patient.nom_complet, f.date_echeance, f.reste_a_payer,
                f.relances.count()]

    def get_queryset(self):
        return services.factures_en_retard()


class TarifListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "facturation.view_tarif"
    template_name = "facturation/tarifs.html"
    context_object_name = "tarifs"
    queryset = Tarif.objects.all()


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
@require_POST
def generer_facture(request, type_acte, acte_id):
    if not request.user.has_perm("facturation.add_facture"):
        messages.error(request, _("Action non autorisée."))
        return redirect("facturation:liste")
    conf = _GENERATEURS.get(type_acte)
    if not conf:
        messages.error(request, _("Type d'acte inconnu."))
        return redirect("facturation:liste")
    app_label, model_name, generateur = conf
    from django.apps import apps
    modele = apps.get_model(app_label, model_name)
    acte = get_object_or_404(modele, pk=acte_id)
    try:
        facture = generateur(acte, par=request.user, forcer=request.POST.get("forcer") == "1")
    except services.ErreurFacturation as exc:
        messages.error(request, str(exc))
        return redirect(request.META.get("HTTP_REFERER", reverse("facturation:liste")))
    if facture is None:
        messages.info(request, _("Cet acte est déjà facturé."))
        return redirect(request.META.get("HTTP_REFERER", reverse("facturation:liste")))
    _audit(request, HistoriqueAction.Action.CREATION, facture,
           f"Facture {facture.reference} générée depuis {acte}")
    messages.success(request, _("Facture %(r)s générée (brouillon).")
                     % {"r": facture.reference})
    return redirect("facturation:detail", pk=facture.pk)


@require_POST
def facture_emettre(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    if not request.user.has_perm("facturation.change_facture"):
        messages.error(request, _("Action non autorisée.")); return redirect("facturation:detail", pk=pk)
    try:
        services.emettre_facture(facture=facture, par=request.user)
    except services.ErreurFacturation as exc:
        messages.error(request, str(exc)); return redirect("facturation:detail", pk=pk)
    _audit(request, HistoriqueAction.Action.MODIFICATION, facture,
           f"Facture {facture.reference} émise")
    messages.success(request, _("Facture émise."))
    return redirect("facturation:detail", pk=pk)


@require_POST
def facture_annuler(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    if not request.user.has_perm("facturation.change_facture"):
        messages.error(request, _("Action non autorisée.")); return redirect("facturation:detail", pk=pk)
    form = AnnulationFactureForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Le motif est obligatoire.")); return redirect("facturation:detail", pk=pk)
    try:
        services.annuler_facture(facture=facture, motif=form.cleaned_data["motif"],
                                 par=request.user)
    except services.ErreurFacturation as exc:
        messages.error(request, str(exc)); return redirect("facturation:detail", pk=pk)
    _audit(request, HistoriqueAction.Action.MODIFICATION, facture,
           f"Facture {facture.reference} annulée : {form.cleaned_data['motif']}")
    messages.success(request, _("Facture annulée."))
    return redirect("facturation:detail", pk=pk)


@require_POST
def ligne_ajouter(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    if not request.user.has_perm("facturation.add_lignefacture") \
            or facture.statut != Facture.Statut.BROUILLON:
        messages.error(request, _("Action non autorisée.")); return redirect("facturation:detail", pk=pk)
    form = LigneFactureForm(request.POST)
    if form.is_valid():
        ligne = form.save(commit=False)
        ligne.facture = facture
        ligne.save()
        facture.recalculer_totaux()
        messages.success(request, _("Ligne ajoutée."))
    else:
        messages.error(request, _("Formulaire invalide."))
    return redirect("facturation:detail", pk=pk)


@require_POST
def ligne_supprimer(request, pk, ligne_pk):
    facture = get_object_or_404(Facture, pk=pk)
    if not request.user.has_perm("facturation.delete_lignefacture") \
            or facture.statut != Facture.Statut.BROUILLON:
        messages.error(request, _("Action non autorisée.")); return redirect("facturation:detail", pk=pk)
    LigneFacture.objects.filter(pk=ligne_pk, facture=facture).delete()
    facture.recalculer_totaux()
    messages.success(request, _("Ligne retirée."))
    return redirect("facturation:detail", pk=pk)


@require_POST
def paiement_ajouter(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    if not request.user.has_perm("facturation.add_paiement"):
        messages.error(request, _("Action non autorisée.")); return redirect("facturation:detail", pk=pk)
    form = PaiementForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Formulaire de paiement invalide.")); return redirect("facturation:detail", pk=pk)
    d = form.cleaned_data
    try:
        paiement = services.enregistrer_paiement(
            facture=facture, montant=d["montant"], mode=d["mode"], payeur=d["payeur"],
            est_remboursement=d["est_remboursement"],
            reference_transaction=d["reference_transaction"],
            commentaire=d["commentaire"], par=request.user,
        )
    except services.ErreurFacturation as exc:
        messages.error(request, str(exc)); return redirect("facturation:detail", pk=pk)
    _audit(request, HistoriqueAction.Action.MODIFICATION, facture,
           f"Paiement {paiement.reference} sur {facture.reference}")
    messages.success(request, _("Paiement enregistré."))
    return redirect("facturation:detail", pk=pk)


@require_POST
def relance_ajouter(request, pk):
    facture = get_object_or_404(Facture, pk=pk)
    if not request.user.has_perm("facturation.add_relance"):
        messages.error(request, _("Action non autorisée.")); return redirect("facturation:detail", pk=pk)
    form = RelanceForm(request.POST)
    if form.is_valid():
        relance = form.save(commit=False)
        relance.facture = facture
        relance.par = request.user
        relance.save()
        messages.success(request, _("Relance enregistrée."))
    else:
        messages.error(request, _("Formulaire invalide."))
    return redirect("facturation:detail", pk=pk)
