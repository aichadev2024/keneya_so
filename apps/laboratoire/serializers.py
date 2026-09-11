from rest_framework import serializers

from .models import DemandeExamen, LigneExamen, Resultat, TypeExamen


class TypeExamenSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeExamen
        fields = ["id", "code", "libelle", "categorie", "unite", "valeurs_reference",
                  "delai_rendu_heures", "actif"]


class ResultatSerializer(serializers.ModelSerializer):
    est_anormal = serializers.BooleanField(read_only=True)

    class Meta:
        model = Resultat
        fields = ["id", "valeur", "interpretation", "compte_rendu", "conclusion",
                  "fichier", "commentaire", "saisi_par", "saisi_le", "valide",
                  "valide_par", "valide_le", "est_anormal"]
        read_only_fields = ["saisi_par", "saisi_le", "valide", "valide_par", "valide_le"]


class LigneExamenSerializer(serializers.ModelSerializer):
    type_libelle = serializers.CharField(source="type_examen.libelle", read_only=True)
    resultat = ResultatSerializer(read_only=True)

    class Meta:
        model = LigneExamen
        fields = ["id", "type_examen", "type_libelle", "unite", "valeurs_reference",
                  "resultat"]


class DemandeExamenSerializer(serializers.ModelSerializer):
    patient_nom = serializers.CharField(source="patient.nom_complet", read_only=True)
    lignes = LigneExamenSerializer(many=True, read_only=True)
    types_examens = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=TypeExamen.objects.filter(actif=True))

    class Meta:
        model = DemandeExamen
        fields = ["id", "reference", "patient", "patient_nom", "categorie",
                  "consultation", "hospitalisation", "prescripteur", "priorite",
                  "renseignements_cliniques", "date_demande", "date_prelevement",
                  "statut", "motif_annulation", "lignes", "types_examens"]
        read_only_fields = ["reference", "prescripteur", "statut", "motif_annulation"]

    def create(self, validated_data):
        from .services import creer_demande
        types = validated_data.pop("types_examens", [])
        return creer_demande(
            patient=validated_data["patient"],
            prescripteur=self.context["request"].user,
            categorie=validated_data["categorie"],
            types_examens=list(types),
            consultation=validated_data.get("consultation"),
            hospitalisation=validated_data.get("hospitalisation"),
            priorite=validated_data.get("priorite", "ROUTINE"),
            renseignements_cliniques=validated_data.get("renseignements_cliniques", ""),
            par=self.context["request"].user,
        )
