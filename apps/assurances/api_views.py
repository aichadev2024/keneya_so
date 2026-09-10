from datetime import date

from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import DjangoModelPermissionsStrict
from apps.core.models import HistoriqueAction

from . import services
from .models import Assurance, BordereauAssurance, ContratAssurance, PatientAssure
from .serializers import (
    AssuranceSerializer,
    BordereauAssuranceSerializer,
    ContratAssuranceSerializer,
    PatientAssureSerializer,
)


class AssuranceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Assurance.objects.prefetch_related("contrats")
    serializer_class = AssuranceSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]


class ContratAssuranceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ContratAssurance.objects.select_related("assurance")
    serializer_class = ContratAssuranceSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]


class PatientAssureViewSet(viewsets.ModelViewSet):
    queryset = PatientAssure.objects.select_related("contrat__assurance", "patient")
    serializer_class = PatientAssureSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.SearchFilter]
    search_fields = ["patient__nom", "patient__numero_dossier", "numero_adherent"]

    def get_queryset(self):
        qs = super().get_queryset()
        patient = self.request.query_params.get("patient")
        return qs.filter(patient_id=patient) if patient else qs


class BordereauAssuranceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = BordereauAssurance.objects.select_related("assurance").prefetch_related(
        "lignes__facture__patient"
    )
    serializer_class = BordereauAssuranceSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]

    @action(detail=False, methods=["post"])
    def generer(self, request):
        if not request.user.has_perm("assurances.add_bordereauassurance"):
            return Response({"detail": "Permission refusée."}, status=403)
        try:
            assurance = Assurance.objects.get(pk=request.data["assurance"])
            debut = date.fromisoformat(request.data["periode_debut"])
            fin = date.fromisoformat(request.data["periode_fin"])
        except (KeyError, ValueError, Assurance.DoesNotExist) as exc:
            return Response({"detail": f"Données invalides : {exc}"}, status=400)
        try:
            bordereau = services.generer_bordereau(assurance=assurance,
                                                   periode_debut=debut, periode_fin=fin,
                                                   par=request.user)
        except services.ErreurBordereau as exc:
            return Response({"detail": str(exc)}, status=400)
        HistoriqueAction.enregistrer(
            utilisateur=request.user, action=HistoriqueAction.Action.CREATION,
            objet=bordereau, description=f"Bordereau {bordereau.reference} (API)",
        )
        return Response(BordereauAssuranceSerializer(bordereau).data, status=201)
