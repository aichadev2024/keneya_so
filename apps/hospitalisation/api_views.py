from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import DjangoModelPermissionsStrict
from apps.core.models import HistoriqueAction
from apps.patients.models import Patient

from .models import Chambre, Hospitalisation, Lit, Service
from .serializers import (
    ChambreSerializer,
    HospitalisationSerializer,
    LitSerializer,
    NoteSuiviSerializer,
    ServiceSerializer,
)
from .services import (
    ErreurHospitalisation,
    admettre,
    prononcer_sortie,
    transferer,
)


class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Service.objects.all()
    serializer_class = ServiceSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]


class LitViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Lit.objects.select_related("chambre__service")
    serializer_class = LitSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.OrderingFilter]

    def get_queryset(self):
        qs = super().get_queryset()
        service = self.request.query_params.get("service")
        if service:
            qs = qs.filter(chambre__service_id=service)
        if self.request.query_params.get("disponibles") == "1":
            qs = qs.filter(statut=Lit.Statut.DISPONIBLE).exclude(
                hospitalisations__statut=Hospitalisation.Statut.EN_COURS
            )
        return qs


class HospitalisationViewSet(viewsets.ModelViewSet):
    queryset = Hospitalisation.objects.select_related(
        "patient", "service", "lit__chambre"
    ).prefetch_related("notes")
    serializer_class = HospitalisationSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reference", "patient__nom", "patient__numero_dossier"]
    ordering_fields = ["date_admission"]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        patient = self.request.query_params.get("patient")
        if statut:
            qs = qs.filter(statut=statut)
        if patient:
            qs = qs.filter(patient_id=patient)
        return qs

    def create(self, request, *args, **kwargs):
        """Admission : POST {patient, service, lit?, motif, diagnostic_admission?}."""
        try:
            patient = Patient.objects.get(pk=request.data["patient"])
            service = Service.objects.get(pk=request.data["service"])
            lit = (Lit.objects.get(pk=request.data["lit"])
                   if request.data.get("lit") else None)
        except (KeyError, Patient.DoesNotExist, Service.DoesNotExist, Lit.DoesNotExist) as exc:
            return Response({"detail": f"Données invalides : {exc}"}, status=400)
        try:
            sejour = admettre(
                patient=patient, service=service, lit=lit,
                motif=request.data.get("motif", ""),
                diagnostic_admission=request.data.get("diagnostic_admission", ""),
                medecin_referent=request.user if request.user.role in {
                    "MEDECIN", "CHIRURGIEN"} else None,
                par=request.user,
            )
        except ErreurHospitalisation as exc:
            return Response({"detail": str(exc)}, status=400)
        HistoriqueAction.enregistrer(
            utilisateur=request.user, action=HistoriqueAction.Action.CREATION,
            objet=sejour, description=str(sejour),
        )
        return Response(self.get_serializer(sejour).data, status=201)

    @action(detail=True, methods=["post"])
    def transferer(self, request, pk=None):
        sejour = self.get_object()
        try:
            lit = Lit.objects.get(pk=request.data["nouveau_lit"])
        except (KeyError, Lit.DoesNotExist):
            return Response({"detail": "nouveau_lit invalide."}, status=400)
        try:
            transferer(hospitalisation=sejour, nouveau_lit=lit,
                       motif=request.data.get("motif", ""), par=request.user)
        except ErreurHospitalisation as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(sejour).data)

    @action(detail=True, methods=["post"])
    def sortie(self, request, pk=None):
        sejour = self.get_object()
        try:
            prononcer_sortie(
                hospitalisation=sejour,
                mode_sortie=request.data.get("mode_sortie", ""),
                compte_rendu=request.data.get("compte_rendu", ""),
                consignes_sortie=request.data.get("consignes_sortie", ""),
                par=request.user,
            )
        except ErreurHospitalisation as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(self.get_serializer(sejour).data)

    @action(detail=True, methods=["get", "post"], serializer_class=NoteSuiviSerializer)
    def notes(self, request, pk=None):
        sejour = self.get_object()
        if request.method == "GET":
            return Response(NoteSuiviSerializer(sejour.notes.all(), many=True).data)
        if not request.user.has_perm("hospitalisation.add_notesuivi"):
            return Response({"detail": "Permission refusée."}, status=403)
        serializer = NoteSuiviSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(hospitalisation=sejour, auteur=request.user)
        return Response(serializer.data, status=201)
