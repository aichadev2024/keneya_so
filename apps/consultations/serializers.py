from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Constantes, Consultation, LigneOrdonnance, Ordonnance
from .services import alertes_prescription


class ConstantesSerializer(serializers.ModelSerializer):
    imc = serializers.FloatField(read_only=True)

    class Meta:
        model = Constantes
        fields = ["poids_kg", "taille_cm", "temperature_c", "tension_systolique",
                  "tension_diastolique", "frequence_cardiaque", "frequence_respiratoire",
                  "saturation_o2", "glycemie_g_l", "imc", "releve_le"]


class ConsultationSerializer(serializers.ModelSerializer):
    patient_nom = serializers.CharField(source="patient.nom_complet", read_only=True)
    constantes = ConstantesSerializer(read_only=True)

    class Meta:
        model = Consultation
        fields = ["id", "reference", "patient", "patient_nom", "praticien",
                  "date_consultation", "motif", "histoire_maladie", "examen_clinique",
                  "diagnostic", "conduite_a_tenir", "statut", "constantes"]
        read_only_fields = ["reference", "praticien"]


class LigneOrdonnanceSerializer(serializers.ModelSerializer):
    medicament_libelle = serializers.CharField(read_only=True)
    quantite_dispensee = serializers.IntegerField(read_only=True)

    class Meta:
        model = LigneOrdonnance
        fields = ["id", "medicament", "medicament_libelle", "posologie", "duree_jours",
                  "quantite_prescrite", "instructions", "quantite_dispensee"]


class OrdonnanceSerializer(serializers.ModelSerializer):
    lignes = LigneOrdonnanceSerializer(many=True)
    alertes = serializers.SerializerMethodField()

    class Meta:
        model = Ordonnance
        fields = ["id", "reference", "consultation", "prescripteur", "date_prescription",
                  "statut", "date_transmission", "notes", "lignes", "alertes"]
        read_only_fields = ["reference", "prescripteur", "statut", "date_transmission"]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_alertes(self, obj):
        if obj.pk:
            return alertes_prescription(obj)
        return []

    def create(self, validated_data):
        lignes = validated_data.pop("lignes", [])
        ordonnance = Ordonnance.objects.create(**validated_data)
        for ligne in lignes:
            LigneOrdonnance.objects.create(ordonnance=ordonnance, **ligne)
        return ordonnance

    def update(self, instance, validated_data):
        lignes = validated_data.pop("lignes", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lignes is not None:
            instance.lignes.all().delete()
            for ligne in lignes:
                LigneOrdonnance.objects.create(ordonnance=instance, **ligne)
        return instance
