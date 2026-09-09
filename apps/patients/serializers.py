from rest_framework import serializers

from .models import Allergie, DossierMedical, Patient


class AllergieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Allergie
        fields = ["id", "libelle", "type", "severite", "remarque"]


class DossierMedicalSerializer(serializers.ModelSerializer):
    allergies = AllergieSerializer(many=True, read_only=True)

    class Meta:
        model = DossierMedical
        fields = [
            "id", "antecedents_medicaux", "antecedents_chirurgicaux",
            "antecedents_familiaux", "antecedents_gyneco_obstetricaux",
            "traitements_en_cours", "habitudes_vie", "observations", "allergies",
        ]


class PatientSerializer(serializers.ModelSerializer):
    age = serializers.IntegerField(read_only=True)
    nom_complet = serializers.CharField(read_only=True)

    class Meta:
        model = Patient
        fields = [
            "id", "numero_dossier", "nom", "prenom", "nom_complet", "sexe",
            "date_naissance", "date_naissance_estimee", "age", "lieu_naissance",
            "nationalite", "telephone", "adresse", "ville", "personne_a_prevenir",
            "lien_personne_a_prevenir", "telephone_urgence", "profession",
            "statut_matrimonial", "groupe_sanguin", "actif", "cree_le", "modifie_le",
        ]
        read_only_fields = ["numero_dossier", "cree_le", "modifie_le"]


class PatientDetailSerializer(PatientSerializer):
    dossier_medical = DossierMedicalSerializer(read_only=True)

    class Meta(PatientSerializer.Meta):
        fields = PatientSerializer.Meta.fields + ["dossier_medical"]
