from django.contrib.auth import get_user_model
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .permissions import EstAdministrateur
from .serializers import MonProfilSerializer, UtilisateurSerializer

Utilisateur = get_user_model()


class UtilisateurViewSet(viewsets.ModelViewSet):
    """
    Gestion des comptes du personnel — réservée à l'administrateur (CDC 4.10).
    L'endpoint ``/api/v1/utilisateurs/moi/`` reste accessible à tout compte connecté.
    """

    queryset = Utilisateur.objects.all().order_by("last_name", "first_name")
    serializer_class = UtilisateurSerializer
    permission_classes = [permissions.IsAuthenticated, EstAdministrateur]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["username", "first_name", "last_name", "email", "matricule"]
    ordering_fields = ["last_name", "first_name", "date_joined"]

    def get_permissions(self):
        if self.action == "moi":
            return [permissions.IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        role = self.request.query_params.get("role")
        actif = self.request.query_params.get("actif")
        if role:
            qs = qs.filter(role=role)
        if actif in {"0", "1"}:
            qs = qs.filter(is_active=(actif == "1"))
        return qs

    @action(detail=False, methods=["get", "patch"], serializer_class=MonProfilSerializer)
    def moi(self, request):
        if request.method == "PATCH":
            serializer = self.get_serializer(request.user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(self.get_serializer(request.user).data)
