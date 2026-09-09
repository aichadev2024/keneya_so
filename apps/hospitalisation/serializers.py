from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Chambre, Hospitalisation, Lit, NoteSuivi, Service


class LitSerializer(serializers.ModelSerializer):
    est_occupe = serializers.BooleanField(read_only=True)
    est_disponible = serializers.BooleanField(read_only=True)
    service = serializers.CharField(source="chambre.service.nom", read_only=True)
    patient = serializers.SerializerMethodField()

    class Meta:
        model = Lit
        fields = ["id", "numero", "statut", "chambre", "service", "est_occupe",
                  "est_disponible", "patient"]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_patient(self, obj):
        h = obj.hospitalisation_active
        return h.patient.nom_complet if h else None


class ChambreSerializer(serializers.ModelSerializer):
    lits = LitSerializer(many=True, read_only=True)

    class Meta:
        model = Chambre
        fields = ["id", "service", "numero", "type", "lits"]


class ServiceSerializer(serializers.ModelSerializer):
    nb_lits = serializers.IntegerField(read_only=True)
    nb_lits_occupes = serializers.IntegerField(read_only=True)
    taux_occupation = serializers.IntegerField(read_only=True)

    class Meta:
        model = Service
        fields = ["id", "nom", "code", "description", "actif", "nb_lits",
                  "nb_lits_occupes", "taux_occupation"]


class NoteSuiviSerializer(serializers.ModelSerializer):
    auteur_nom = serializers.CharField(source="auteur.get_full_name", read_only=True)

    class Meta:
        model = NoteSuivi
        fields = ["id", "hospitalisation", "type", "description", "temperature_c",
                  "tension_systolique", "tension_diastolique", "pouls", "date_note",
                  "auteur", "auteur_nom"]
        read_only_fields = ["hospitalisation", "auteur", "date_note"]


class HospitalisationSerializer(serializers.ModelSerializer):
    patient_nom = serializers.CharField(source="patient.nom_complet", read_only=True)
    lit_libelle = serializers.CharField(source="lit.__str__", read_only=True)
    duree_jours = serializers.IntegerField(read_only=True)
    notes = NoteSuiviSerializer(many=True, read_only=True)

    class Meta:
        model = Hospitalisation
        fields = ["id", "reference", "patient", "patient_nom", "service", "lit",
                  "lit_libelle", "consultation", "medecin_referent", "motif",
                  "diagnostic_admission", "date_admission", "statut", "date_sortie",
                  "mode_sortie", "compte_rendu", "consignes_sortie", "duree_jours",
                  "notes"]
        read_only_fields = ["reference", "statut", "date_sortie", "mode_sortie",
                            "lit", "service"]
