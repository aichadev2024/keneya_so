from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import DjangoModelPermissionsStrict
from apps.core.models import HistoriqueAction

from .models import Dispensation, Medicament
from .serializers import DispensationSerializer, MedicamentSerializer
from .services import ErreurStock, dispenser_ordonnance, enregistrer_entree


class MedicamentViewSet(viewsets.ModelViewSet):
    queryset = Medicament.objects.all()
    serializer_class = MedicamentSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["denomination", "code", "dosage"]
    ordering_fields = ["denomination"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("alerte") == "1":
            ids = [m.id for m in qs if m.en_alerte]
            return qs.filter(id__in=ids)
        return qs

    def perform_create(self, serializer):
        serializer.save(cree_par=self.request.user, modifie_par=self.request.user)

    @action(detail=True, methods=["post"], url_path="entree-stock")
    def entree_stock(self, request, pk=None):
        medicament = self.get_object()
        try:
            lot = enregistrer_entree(
                medicament=medicament,
                numero_lot=request.data["numero_lot"],
                quantite=int(request.data["quantite"]),
                date_peremption=request.data["date_peremption"],
                fournisseur=request.data.get("fournisseur", ""),
                utilisateur=request.user,
            )
        except (KeyError, ValueError) as exc:
            return Response({"detail": f"Données invalides : {exc}"}, status=400)
        except ErreurStock as exc:
            return Response({"detail": str(exc)}, status=400)
        HistoriqueAction.enregistrer(
            utilisateur=request.user, action=HistoriqueAction.Action.CREATION,
            objet=lot, description=f"Entrée stock {lot}",
        )
        return Response(MedicamentSerializer(medicament).data)


class DispensationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Dispensation.objects.select_related(
        "ordonnance__consultation__patient"
    ).prefetch_related("lignes")
    serializer_class = DispensationSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]

    @action(detail=True, methods=["post"])
    def delivrer(self, request, pk=None):
        dispensation = self.get_object()
        if not request.user.has_perm("pharmacie.add_lignedispensation"):
            return Response({"detail": "Permission refusée."}, status=403)
        quantites = request.data.get("quantites") or {}
        try:
            quantites = {int(k): int(v) for k, v in quantites.items()}
        except (ValueError, AttributeError):
            return Response({"detail": "'quantites' doit être un objet {ligne_id: qté}."},
                            status=400)
        try:
            dispenser_ordonnance(
                ordonnance=dispensation.ordonnance, pharmacien=request.user,
                quantites=quantites, commentaire=request.data.get("commentaire", ""),
            )
        except ErreurStock as exc:
            return Response({"detail": str(exc)}, status=400)
        dispensation.refresh_from_db()
        HistoriqueAction.enregistrer(
            utilisateur=request.user, action=HistoriqueAction.Action.MODIFICATION,
            objet=dispensation,
            description=f"Dispensation {dispensation.ordonnance.reference} (API)",
        )
        return Response(self.get_serializer(dispensation).data)
