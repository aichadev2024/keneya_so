from django.apps import apps as django_apps
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import DjangoModelPermissionsStrict
from apps.core.models import HistoriqueAction

from . import services
from .models import Facture, Tarif
from .serializers import FactureSerializer, TarifSerializer

_GENERATEURS = {
    "consultation": ("consultations", "Consultation", services.facturer_consultation),
    "hospitalisation": ("hospitalisation", "Hospitalisation",
                        services.facturer_hospitalisation),
    "intervention": ("bloc_operatoire", "Intervention", services.facturer_intervention),
    "dispensation": ("pharmacie", "Dispensation", services.facturer_dispensation),
    "examen": ("laboratoire", "DemandeExamen", services.facturer_demande_examen),
}


class TarifViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tarif.objects.all()
    serializer_class = TarifSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]


class FactureViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Facture.objects.select_related("patient").prefetch_related(
        "lignes", "paiements", "relances"
    )
    serializer_class = FactureSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reference", "patient__nom", "patient__numero_dossier"]
    ordering_fields = ["date_emission", "date_echeance"]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        if statut:
            qs = qs.filter(statut=statut)
        if self.request.query_params.get("retard") == "1":
            from datetime import date
            qs = qs.filter(statut__in=[Facture.Statut.EMISE, Facture.Statut.PARTIELLE],
                           date_echeance__lt=date.today())
        return qs

    def _err(self, exc):
        return Response({"detail": str(exc)}, status=400)

    @action(detail=False, methods=["post"],
            url_path=r"generer/(?P<type_acte>[a-z]+)/(?P<acte_id>[0-9]+)")
    def generer(self, request, type_acte=None, acte_id=None):
        if not request.user.has_perm("facturation.add_facture"):
            return Response({"detail": "Permission refusée."}, status=403)
        conf = _GENERATEURS.get(type_acte)
        if not conf:
            return self._err("Type d'acte inconnu.")
        app_label, model_name, generateur = conf
        acte = django_apps.get_model(app_label, model_name).objects.filter(
            pk=acte_id).first()
        if acte is None:
            return Response({"detail": "Acte introuvable."}, status=404)
        try:
            facture = generateur(acte, par=request.user,
                                 forcer=bool(request.data.get("forcer")))
        except services.ErreurFacturation as exc:
            return self._err(exc)
        if facture is None:
            return Response({"detail": "Acte déjà facturé."}, status=200)
        HistoriqueAction.enregistrer(
            utilisateur=request.user, action=HistoriqueAction.Action.CREATION,
            objet=facture, description=f"Facture {facture.reference} (API)",
        )
        return Response(FactureSerializer(facture).data, status=201)

    @action(detail=True, methods=["post"])
    def emettre(self, request, pk=None):
        try:
            services.emettre_facture(facture=self.get_object(), par=request.user)
        except services.ErreurFacturation as exc:
            return self._err(exc)
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def paiement(self, request, pk=None):
        if not request.user.has_perm("facturation.add_paiement"):
            return Response({"detail": "Permission refusée."}, status=403)
        try:
            services.enregistrer_paiement(
                facture=self.get_object(), montant=request.data["montant"],
                mode=request.data.get("mode", "ESPECES"),
                payeur=request.data.get("payeur", "PATIENT"),
                est_remboursement=bool(request.data.get("est_remboursement")),
                reference_transaction=request.data.get("reference_transaction", ""),
                par=request.user,
            )
        except KeyError:
            return self._err("Champ 'montant' requis.")
        except services.ErreurFacturation as exc:
            return self._err(exc)
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        try:
            services.annuler_facture(facture=self.get_object(),
                                     motif=request.data.get("motif", ""),
                                     par=request.user)
        except services.ErreurFacturation as exc:
            return self._err(exc)
        return Response(self.get_serializer(self.get_object()).data)
