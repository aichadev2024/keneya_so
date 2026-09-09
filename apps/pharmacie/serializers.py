from rest_framework import serializers

from .models import Dispensation, LigneDispensation, LotMedicament, Medicament


class MedicamentSerializer(serializers.ModelSerializer):
    quantite_utilisable = serializers.IntegerField(read_only=True)
    quantite_en_stock = serializers.IntegerField(read_only=True)
    en_alerte = serializers.BooleanField(read_only=True)

    class Meta:
        model = Medicament
        fields = ["id", "code", "denomination", "dosage", "forme", "unite",
                  "seuil_alerte", "actif", "quantite_utilisable", "quantite_en_stock",
                  "en_alerte"]


class LotMedicamentSerializer(serializers.ModelSerializer):
    est_perime = serializers.BooleanField(read_only=True)

    class Meta:
        model = LotMedicament
        fields = ["id", "medicament", "numero_lot", "quantite", "quantite_initiale",
                  "date_peremption", "date_reception", "fournisseur", "est_perime"]


class LigneDispensationSerializer(serializers.ModelSerializer):
    medicament_libelle = serializers.CharField(source="medicament.denomination",
                                               read_only=True)

    class Meta:
        model = LigneDispensation
        fields = ["id", "ligne_ordonnance", "medicament", "medicament_libelle", "lot",
                  "quantite_dispensee", "cree_le"]


class DispensationSerializer(serializers.ModelSerializer):
    lignes = LigneDispensationSerializer(many=True, read_only=True)
    ordonnance_reference = serializers.CharField(source="ordonnance.reference",
                                                 read_only=True)
    patient = serializers.CharField(source="ordonnance.patient.nom_complet",
                                    read_only=True)

    class Meta:
        model = Dispensation
        fields = ["id", "ordonnance", "ordonnance_reference", "patient", "pharmacien",
                  "statut", "date_delivrance", "commentaire", "lignes"]
        read_only_fields = fields
