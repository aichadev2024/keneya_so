"""Vues gabarit du module pharmacie (CDC 4.5)."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView

from apps.core.models import HistoriqueAction

from .forms import EntreeStockForm, MedicamentForm
from .models import Dispensation, Medicament, MouvementStock
from .services import ErreurStock, dispenser_ordonnance, enregistrer_entree, retirer_perimes


class MedicamentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "pharmacie.view_medicament"
    template_name = "pharmacie/medicaments.html"
    context_object_name = "medicaments"
    paginate_by = 30

    def get_queryset(self):
        qs = Medicament.objects.prefetch_related("lots")
        self.q = self.request.GET.get("q", "").strip()
        if self.q:
            qs = qs.filter(Q(denomination__icontains=self.q) | Q(code__icontains=self.q))
        self.alerte = self.request.GET.get("alerte") == "1"
        medicaments = list(qs)
        if self.alerte:
            medicaments = [m for m in medicaments if m.en_alerte]
        return medicaments

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = self.q
        ctx["alerte"] = self.alerte
        ctx["nb_alertes"] = sum(1 for m in Medicament.objects.all() if m.en_alerte)
        return ctx


class MedicamentCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    permission_required = "pharmacie.add_medicament"
    form_class = MedicamentForm
    template_name = "pharmacie/medicament_formulaire.html"
    success_url = reverse_lazy("pharmacie:medicaments")

    def form_valid(self, form):
        form.instance.cree_par = self.request.user
        form.instance.modifie_par = self.request.user
        messages.success(self.request, _("Médicament ajouté au catalogue."))
        return super().form_valid(form)


class MedicamentUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    permission_required = "pharmacie.change_medicament"
    model = Medicament
    form_class = MedicamentForm
    template_name = "pharmacie/medicament_formulaire.html"

    def form_valid(self, form):
        form.instance.modifie_par = self.request.user
        messages.success(self.request, _("Médicament mis à jour."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("pharmacie:medicament", args=[self.object.pk])


class MedicamentDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "pharmacie.view_medicament"
    model = Medicament
    template_name = "pharmacie/medicament_detail.html"
    context_object_name = "medicament"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["lots"] = self.object.lots.all()
        ctx["mouvements"] = self.object.mouvements.select_related("utilisateur")[:20]
        return ctx


class EntreeStockView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    permission_required = "pharmacie.add_lotmedicament"
    form_class = EntreeStockForm
    template_name = "pharmacie/entree_stock.html"
    success_url = reverse_lazy("pharmacie:medicaments")

    def form_valid(self, form):
        d = form.cleaned_data
        try:
            lot = enregistrer_entree(
                medicament=d["medicament"], numero_lot=d["numero_lot"],
                quantite=d["quantite"], date_peremption=d["date_peremption"],
                utilisateur=self.request.user, fournisseur=d["fournisseur"] or "",
                date_reception=d["date_reception"],
            )
        except ErreurStock as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user,
            action=HistoriqueAction.Action.CREATION,
            objet=lot, description=f"Entrée stock {lot} × {d['quantite']}",
        )
        messages.success(self.request, _("Entrée de stock enregistrée."))
        return super().form_valid(form)


class DispensationListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "pharmacie.view_dispensation"
    template_name = "pharmacie/dispensations.html"
    context_object_name = "dispensations"
    paginate_by = 25

    def get_queryset(self):
        qs = Dispensation.objects.select_related(
            "ordonnance__consultation__patient", "pharmacien"
        )
        statut = self.request.GET.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        elif self.request.GET.get("toutes") != "1":
            qs = qs.exclude(statut__in=[Dispensation.Statut.COMPLETE,
                                        Dispensation.Statut.ANNULEE])
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["statuts"] = Dispensation.Statut.choices
        ctx["statut_actif"] = self.request.GET.get("statut", "")
        return ctx


class DispensationDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    permission_required = "pharmacie.view_dispensation"
    model = Dispensation
    template_name = "pharmacie/dispensation_detail.html"
    context_object_name = "dispensation"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        lignes = []
        for ligne in self.object.ordonnance.lignes.select_related("medicament"):
            lignes.append({
                "obj": ligne,
                "utilisable": ligne.medicament.quantite_utilisable,
                "reliquat": ligne.reliquat,
            })
        ctx["lignes"] = lignes
        ctx["cloturee"] = self.object.statut in [Dispensation.Statut.COMPLETE,
                                                 Dispensation.Statut.ANNULEE]
        return ctx


@require_POST
def dispensation_delivrer(request, pk):
    dispensation = get_object_or_404(Dispensation, pk=pk)
    if not request.user.has_perm("pharmacie.add_lignedispensation"):
        messages.error(request, _("Action non autorisée."))
        return redirect("pharmacie:dispensation", pk=pk)

    quantites = {}
    for ligne in dispensation.ordonnance.lignes.all():
        brut = request.POST.get(f"ligne_{ligne.id}", "").strip()
        if brut and brut.isdigit() and int(brut) > 0:
            quantites[ligne.id] = int(brut)

    if not quantites:
        messages.error(request, _("Aucune quantité à délivrer saisie."))
        return redirect("pharmacie:dispensation", pk=pk)

    try:
        dispenser_ordonnance(
            ordonnance=dispensation.ordonnance, pharmacien=request.user,
            quantites=quantites, commentaire=request.POST.get("commentaire", ""),
        )
    except ErreurStock as exc:
        messages.error(request, str(exc))
        return redirect("pharmacie:dispensation", pk=pk)

    HistoriqueAction.enregistrer(
        utilisateur=request.user,
        action=HistoriqueAction.Action.MODIFICATION,
        objet=dispensation,
        description=f"Dispensation {dispensation.ordonnance.reference}",
        donnees={"lignes": quantites},
    )
    messages.success(request, _("Délivrance enregistrée."))
    return redirect("pharmacie:dispensation", pk=pk)


class MouvementStockListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = "pharmacie.view_mouvementstock"
    template_name = "pharmacie/mouvements.html"
    context_object_name = "mouvements"
    paginate_by = 50

    def get_queryset(self):
        qs = MouvementStock.objects.select_related("medicament", "utilisateur")
        type_ = self.request.GET.get("type")
        return qs.filter(type=type_) if type_ else qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["types"] = MouvementStock.Type.choices
        ctx["type_actif"] = self.request.GET.get("type", "")
        return ctx


@require_POST
def retirer_perimes_view(request):
    if not request.user.has_perm("pharmacie.change_lotmedicament"):
        messages.error(request, _("Action non autorisée."))
        return redirect("pharmacie:medicaments")
    total = retirer_perimes(utilisateur=request.user)
    if total:
        messages.success(request, _("%(n)d unité(s) périmée(s) retirée(s) du stock.")
                         % {"n": total})
    else:
        messages.info(request, _("Aucun lot périmé à retirer."))
    return redirect("pharmacie:medicaments")
