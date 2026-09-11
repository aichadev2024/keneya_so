from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import DjangoModelPermissionsStrict
from apps.core.models import HistoriqueAction

from . import services
from .models import DemandeExamen, LigneExamen, TypeExamen
from .serializers import DemandeExamenSerializer, TypeExamenSerializer


class TypeExamenViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TypeExamen.objects.all()
    serializer_class = TypeExamenSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.SearchFilter]
    search_fields = ["code", "libelle"]

    def get_queryset(self):
        qs = super().get_queryset()
        cat = self.request.query_params.get("categorie")
        return qs.filter(categorie=cat) if cat else qs


class DemandeExamenViewSet(viewsets.ModelViewSet):
    queryset = DemandeExamen.objects.select_related("patient", "prescripteur").prefetch_related(
        "lignes__type_examen", "lignes__resultat"
    )
    serializer_class = DemandeExamenSerializer
    permission_classes = [permissions.IsAuthenticated, DjangoModelPermissionsStrict]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reference", "patient__nom", "patient__numero_dossier"]
    ordering_fields = ["date_demande"]

    def get_queryset(self):
        qs = super().get_queryset()
        for champ in ("categorie", "statut", "patient"):
            val = self.request.query_params.get(champ)
            if val:
                qs = qs.filter(**{champ if champ != "patient" else "patient_id": val})
        return qs

    def _err(self, exc):
        return Response({"detail": str(exc)}, status=400)

    @action(detail=True, methods=["post"], url_path=r"lignes/(?P<ligne_pk>[0-9]+)/resultat")
    def resultat(self, request, pk=None, ligne_pk=None):
        if not request.user.has_perm("laboratoire.add_resultat"):
            return Response({"detail": "Permission refusée."}, status=403)
        ligne = LigneExamen.objects.filter(pk=ligne_pk, demande_id=pk).first()
        if ligne is None:
            return Response({"detail": "Ligne introuvable."}, status=404)
        try:
            services.saisir_resultat(
                ligne=ligne, par=request.user,
                valeur=request.data.get("valeur", ""),
                interpretation=request.data.get("interpretation", ""),
                compte_rendu=request.data.get("compte_rendu", ""),
                conclusion=request.data.get("conclusion", ""),
                fichier=request.FILES.get("fichier"),
                commentaire=request.data.get("commentaire", ""),
            )
        except services.ErreurLaboratoire as exc:
            return self._err(exc)
        return Response(self.get_serializer(ligne.demande).data)

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        try:
            services.valider_demande(demande=self.get_object(), par=request.user)
        except services.ErreurLaboratoire as exc:
            return self._err(exc)
        HistoriqueAction.enregistrer(
            utilisateur=request.user, action=HistoriqueAction.Action.MODIFICATION,
            objet=self.get_object(), description="Résultats validés (API)",
        )
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        try:
            services.annuler_demande(demande=self.get_object(),
                                     motif=request.data.get("motif", ""),
                                     par=request.user)
        except services.ErreurLaboratoire as exc:
            return self._err(exc)
        return Response(self.get_serializer(self.get_object()).data)
