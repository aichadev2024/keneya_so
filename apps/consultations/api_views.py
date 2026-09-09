from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import DjangoModelPermissionsStrict
from apps.core.models import HistoriqueAction

from .models import Constantes, Consultation, Ordonnance
from .serializers import ConstantesSerializer, ConsultationSerializer, OrdonnanceSerializer


class ConsultationViewSet(viewsets.ModelViewSet):
    queryset = Consultation.objects.select_related("patient", "praticien")
    serializer_class = ConsultationSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reference", "patient__nom", "patient__numero_dossier", "motif"]
    ordering_fields = ["date_consultation"]

    def get_queryset(self):
        qs = super().get_queryset()
        patient = self.request.query_params.get("patient")
        return qs.filter(patient_id=patient) if patient else qs

    def perform_create(self, serializer):
        consultation = serializer.save(praticien=self.request.user,
                                       cree_par=self.request.user,
                                       modifie_par=self.request.user)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user,
            action=HistoriqueAction.Action.CREATION,
            objet=consultation, description=str(consultation),
        )

    @action(detail=True, methods=["get", "put", "patch"],
            serializer_class=ConstantesSerializer)
    def constantes(self, request, pk=None):
        consultation = self.get_object()
        obj, _created = Constantes.objects.get_or_create(consultation=consultation)
        if request.method == "GET":
            return Response(self.get_serializer(obj).data)
        serializer = self.get_serializer(obj, data=request.data,
                                         partial=request.method == "PATCH")
        serializer.is_valid(raise_exception=True)
        serializer.save(releve_par=request.user)
        return Response(serializer.data)


class OrdonnanceViewSet(viewsets.ModelViewSet):
    queryset = Ordonnance.objects.select_related("consultation__patient").prefetch_related(
        "lignes__medicament"
    )
    serializer_class = OrdonnanceSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]

    def perform_create(self, serializer):
        ordonnance = serializer.save(prescripteur=self.request.user,
                                     cree_par=self.request.user,
                                     modifie_par=self.request.user)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user,
            action=HistoriqueAction.Action.CREATION,
            objet=ordonnance, description=str(ordonnance),
        )

    @action(detail=True, methods=["post"])
    def transmettre(self, request, pk=None):
        ordonnance = self.get_object()
        if not ordonnance.lignes.exists():
            return Response({"detail": "Ordonnance sans médicament."}, status=400)
        ordonnance.transmettre()
        HistoriqueAction.enregistrer(
            utilisateur=request.user,
            action=HistoriqueAction.Action.MODIFICATION,
            objet=ordonnance,
            description=f"Ordonnance {ordonnance.reference} transmise",
        )
        return Response(self.get_serializer(ordonnance).data)
