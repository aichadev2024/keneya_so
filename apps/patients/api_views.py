from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import DjangoModelPermissionsStrict
from apps.core.models import HistoriqueAction

from .models import DossierMedical, Patient
from .serializers import (
    DossierMedicalSerializer,
    PatientDetailSerializer,
    PatientSerializer,
)


class PatientViewSet(viewsets.ModelViewSet):
    """
    CRUD patients + recherche multicritère (CDC 4.1).
    Les permissions de modèle Django (RBAC) sont appliquées : un rôle sans
    ``patients.add_patient`` ne peut pas créer de patient.
    """

    queryset = Patient.objects.all()
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["numero_dossier", "nom", "prenom", "telephone"]
    ordering_fields = ["nom", "prenom", "cree_le"]
    ordering = ["nom", "prenom"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PatientDetailSerializer
        return PatientSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("inactifs") != "1":
            qs = qs.actifs()
        terme = self.request.query_params.get("q")
        if terme:
            qs = qs.recherche(terme)
        return qs

    def perform_create(self, serializer):
        patient = serializer.save(cree_par=self.request.user,
                                  modifie_par=self.request.user)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user,
            action=HistoriqueAction.Action.CREATION,
            objet=patient,
            description=str(patient),
        )

    def perform_update(self, serializer):
        patient = serializer.save(modifie_par=self.request.user)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user,
            action=HistoriqueAction.Action.MODIFICATION,
            objet=patient,
            description=str(patient),
        )

    @action(detail=True, methods=["get", "put", "patch"],
            serializer_class=DossierMedicalSerializer)
    def dossier_medical(self, request, pk=None):
        patient = self.get_object()
        dossier, _created = DossierMedical.objects.get_or_create(patient=patient)
        if request.method == "GET":
            return Response(self.get_serializer(dossier).data)
        serializer = self.get_serializer(
            dossier, data=request.data, partial=request.method == "PATCH"
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(modifie_par=request.user)
        HistoriqueAction.enregistrer(
            utilisateur=request.user,
            action=HistoriqueAction.Action.MODIFICATION,
            objet=dossier,
            description="Dossier médical (API)",
        )
        return Response(serializer.data)
