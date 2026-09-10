from rest_framework import serializers

from .models import (
    Assurance,
    BordereauAssurance,
    ContratAssurance,
    LigneBordereau,
    PatientAssure,
)


class ContratAssuranceSerializer(serializers.ModelSerializer):
    assurance_nom = serializers.CharField(source="assurance.nom", read_only=True)

    class Meta:
        model = ContratAssurance
        fields = ["id", "assurance", "assurance_nom", "libelle", "taux_prise_en_charge",
                  "plafond_annuel", "actif"]


class AssuranceSerializer(serializers.ModelSerializer):
    contrats = ContratAssuranceSerializer(many=True, read_only=True)

    class Meta:
        model = Assurance
        fields = ["id", "nom", "code", "type", "adresse", "contact_nom",
                  "contact_telephone", "contact_email", "actif", "contrats"]


class PatientAssureSerializer(serializers.ModelSerializer):
    assurance_nom = serializers.CharField(source="assurance.nom", read_only=True)
    taux_effectif = serializers.DecimalField(max_digits=5, decimal_places=2,
                                             read_only=True)

    class Meta:
        model = PatientAssure
        fields = ["id", "patient", "contrat", "assurance_nom", "numero_adherent",
                  "taux_prise_en_charge", "taux_effectif", "plafond_annuel",
                  "date_debut", "date_fin", "actif"]


class LigneBordereauSerializer(serializers.ModelSerializer):
    facture_reference = serializers.CharField(source="facture.reference", read_only=True)
    patient = serializers.CharField(source="facture.patient.nom_complet", read_only=True)

    class Meta:
        model = LigneBordereau
        fields = ["id", "facture", "facture_reference", "patient", "montant_assurance"]


class BordereauAssuranceSerializer(serializers.ModelSerializer):
    assurance_nom = serializers.CharField(source="assurance.nom", read_only=True)
    lignes = LigneBordereauSerializer(many=True, read_only=True)

    class Meta:
        model = BordereauAssurance
        fields = ["id", "reference", "assurance", "assurance_nom", "periode_debut",
                  "periode_fin", "date_generation", "statut", "montant_total", "lignes"]
        read_only_fields = ["reference", "date_generation", "montant_total"]
