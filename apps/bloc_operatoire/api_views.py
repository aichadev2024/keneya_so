from datetime import datetime

from django.contrib.auth import get_user_model
from django.utils import timezone
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import DjangoModelPermissionsStrict
from apps.core.models import HistoriqueAction

from . import services, stats
from .models import (
    Intervention,
    MaterielBloc,
    SalleOperatoire,
    TypeIntervention,
)
from .serializers import (
    CompteRenduSerializer,
    InterventionSerializer,
    MaterielBlocSerializer,
    SalleOperatoireSerializer,
    TypeInterventionSerializer,
)

Utilisateur = get_user_model()


class SalleOperatoireViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SalleOperatoire.objects.all()
    serializer_class = SalleOperatoireSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]


class TypeInterventionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TypeIntervention.objects.all()
    serializer_class = TypeInterventionSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]


class MaterielBlocViewSet(viewsets.ModelViewSet):
    queryset = MaterielBloc.objects.all()
    serializer_class = MaterielBlocSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.SearchFilter]
    search_fields = ["designation", "reference"]


class InterventionViewSet(viewsets.ModelViewSet):
    queryset = Intervention.objects.select_related(
        "patient", "type_intervention", "salle", "chirurgien_principal"
    ).prefetch_related("equipe__utilisateur", "checklist")
    serializer_class = InterventionSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reference", "patient__nom", "patient__numero_dossier"]
    ordering_fields = ["date_heure_debut_prevue", "date_demande"]

    def get_queryset(self):
        qs = super().get_queryset()
        statut = self.request.query_params.get("statut")
        salle = self.request.query_params.get("salle")
        if statut:
            qs = qs.filter(statut=statut)
        if salle:
            qs = qs.filter(salle_id=salle)
        return qs

    def perform_create(self, serializer):
        intervention = serializer.save(demandeur=self.request.user,
                                       cree_par=self.request.user,
                                       modifie_par=self.request.user)
        HistoriqueAction.enregistrer(
            utilisateur=self.request.user, action=HistoriqueAction.Action.CREATION,
            objet=intervention, description=str(intervention),
        )

    def _err(self, exc):
        return Response({"detail": str(exc)}, status=400)

    @action(detail=True, methods=["post"])
    def planifier(self, request, pk=None):
        intervention = self.get_object()
        try:
            salle = SalleOperatoire.objects.get(pk=request.data["salle"])
            debut = datetime.fromisoformat(request.data["debut"])
            if timezone.is_naive(debut):
                debut = timezone.make_aware(debut)
            duree = int(request.data.get("duree_estimee_min",
                                         intervention.duree_estimee_min))
        except (KeyError, ValueError, SalleOperatoire.DoesNotExist) as exc:
            return self._err(f"Données invalides : {exc}")
        try:
            res = services.planifier(intervention=intervention, salle=salle, debut=debut,
                                     duree_estimee_min=duree, par=request.user,
                                     forcer=bool(request.data.get("forcer")))
        except services.ErreurBloc as exc:
            return self._err(exc)
        data = self.get_serializer(intervention).data
        data["reports"] = [i.reference for i in res["reports"]]
        return Response(data)

    @action(detail=True, methods=["post"])
    def faisabilite(self, request, pk=None):
        intervention = self.get_object()
        intervention.faisabilite_anesthesique_validee = True
        intervention.protocole_anesthesie = request.data.get("protocole_anesthesie", "")
        intervention.anesthesiste_validateur = request.user
        intervention.save()
        return Response(self.get_serializer(intervention).data)

    @action(detail=True, methods=["post"], url_path="equipe")
    def equipe(self, request, pk=None):
        intervention = self.get_object()
        try:
            membre = Utilisateur.objects.get(pk=request.data["utilisateur"])
            services.ajouter_membre(intervention=intervention, utilisateur=membre,
                                    role=request.data["role"], par=request.user,
                                    forcer=bool(request.data.get("forcer")))
        except (KeyError, Utilisateur.DoesNotExist) as exc:
            return self._err(f"Données invalides : {exc}")
        except services.ErreurBloc as exc:
            return self._err(exc)
        return Response(self.get_serializer(intervention).data, status=201)

    @action(detail=True, methods=["post"], url_path="checklist/(?P<temps>[A-Z_]+)")
    def checklist(self, request, pk=None, temps=None):
        intervention = self.get_object()
        try:
            services.valider_etape(intervention=intervention, temps=temps,
                                   utilisateur=request.user,
                                   commentaire=request.data.get("commentaire", ""))
        except (services.ErreurBloc, ValueError) as exc:
            return self._err(exc)
        return Response(self.get_serializer(intervention).data)

    @action(detail=True, methods=["post"], url_path="peroperatoire/(?P<etape>[a-z]+)")
    def peroperatoire(self, request, pk=None, etape=None):
        intervention = self.get_object()
        try:
            if etape == "entree":
                services.entree_en_salle(intervention=intervention, par=request.user)
            elif etape == "incision":
                services.pointer_incision(intervention=intervention, par=request.user)
            elif etape == "terminer":
                services.terminer(intervention=intervention,
                                  incidents=request.data.get("incidents", ""),
                                  par=request.user)
            else:
                return self._err("Étape inconnue.")
        except services.ErreurBloc as exc:
            return self._err(exc)
        return Response(self.get_serializer(intervention).data)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        intervention = self.get_object()
        try:
            services.annuler(intervention=intervention,
                             motif=request.data.get("motif", ""), par=request.user,
                             reporter=bool(request.data.get("reporter")))
        except services.ErreurBloc as exc:
            return self._err(exc)
        return Response(self.get_serializer(intervention).data)

    @action(detail=True, methods=["get", "put", "post"], url_path="compte-rendu",
            serializer_class=CompteRenduSerializer)
    def compte_rendu(self, request, pk=None):
        intervention = self.get_object()
        cr = getattr(intervention, "compte_rendu", None)
        if request.method == "GET":
            if cr is None:
                return Response({}, status=404)
            return Response(CompteRenduSerializer(cr).data)
        if not request.user.has_perm("bloc_operatoire.add_compterenduoperatoire"):
            return Response({"detail": "Permission refusée."}, status=403)
        serializer = CompteRenduSerializer(cr, data=request.data, partial=cr is not None)
        serializer.is_valid(raise_exception=True)
        serializer.save(intervention=intervention,
                        redige_par=request.user if cr is None else cr.redige_par)
        return Response(serializer.data)


class IndicateursBlocView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        if not request.user.has_perm("bloc_operatoire.view_intervention"):
            return Response({"detail": "Permission refusée."}, status=403)
        return Response(stats.tableau_de_bord())
