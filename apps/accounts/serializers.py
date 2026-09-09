from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

Utilisateur = get_user_model()


class UtilisateurSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Utilisateur
        fields = [
            "id", "username", "first_name", "last_name", "email",
            "role", "role_display", "matricule", "telephone", "specialite",
            "langue_preferee", "is_active", "is_staff", "permissions",
        ]
        read_only_fields = ["is_staff"]

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_permissions(self, obj):
        return sorted(obj.get_all_permissions())


class MonProfilSerializer(UtilisateurSerializer):
    """Version restreinte pour l'endpoint /me : l'utilisateur ne change pas son rôle."""

    class Meta(UtilisateurSerializer.Meta):
        read_only_fields = ["is_staff", "role", "matricule", "is_active", "username"]
