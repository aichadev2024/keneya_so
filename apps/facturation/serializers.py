from rest_framework import serializers

from .models import Facture, LigneFacture, Paiement, Relance, Tarif


class TarifSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tarif
        fields = ["id", "code", "libelle", "categorie", "montant", "reference_externe",
                  "actif"]


class LigneFactureSerializer(serializers.ModelSerializer):
    class Meta:
        model = LigneFacture
        fields = ["id", "type_source", "source_id", "libelle", "quantite",
                  "prix_unitaire", "montant"]
        read_only_fields = ["montant"]


class PaiementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paiement
        fields = ["id", "reference", "montant", "mode", "payeur", "est_remboursement",
                  "reference_transaction", "date_paiement", "commentaire"]
        read_only_fields = ["reference", "date_paiement"]


class RelanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Relance
        fields = ["id", "date_relance", "canal", "commentaire"]
        read_only_fields = ["date_relance"]


class FactureSerializer(serializers.ModelSerializer):
    patient_nom = serializers.CharField(source="patient.nom_complet", read_only=True)
    lignes = LigneFactureSerializer(many=True, read_only=True)
    paiements = PaiementSerializer(many=True, read_only=True)
    relances = RelanceSerializer(many=True, read_only=True)
    montant_regle = serializers.DecimalField(max_digits=12, decimal_places=2,
                                             read_only=True)
    reste_a_payer = serializers.DecimalField(max_digits=12, decimal_places=2,
                                             read_only=True)
    reste_patient = serializers.DecimalField(max_digits=12, decimal_places=2,
                                             read_only=True)
    en_retard = serializers.BooleanField(read_only=True)

    class Meta:
        model = Facture
        fields = ["id", "reference", "patient", "patient_nom", "patient_assure",
                  "date_emission", "date_echeance", "statut", "montant_total",
                  "taux_couverture_applique", "part_assurance", "part_patient",
                  "montant_regle", "reste_a_payer", "reste_patient", "en_retard",
                  "notes", "motif_annulation", "lignes", "paiements", "relances"]
        read_only_fields = fields
