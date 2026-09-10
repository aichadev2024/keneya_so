from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    CompteRenduOperatoire,
    EtapeChecklist,
    Intervention,
    MaterielBloc,
    MembreEquipe,
    SalleOperatoire,
    TypeIntervention,
)


class SalleOperatoireSerializer(serializers.ModelSerializer):
    statut_effectif = serializers.CharField(read_only=True)

    class Meta:
        model = SalleOperatoire
        fields = ["id", "nom", "code", "equipement", "capacite", "duree_nettoyage_min",
                  "statut", "statut_effectif", "actif"]


class TypeInterventionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TypeIntervention
        fields = ["id", "libelle", "specialite", "duree_standard_min", "description",
                  "actif"]


class MaterielBlocSerializer(serializers.ModelSerializer):
    disponible_pour_intervention = serializers.BooleanField(read_only=True)

    class Meta:
        model = MaterielBloc
        fields = ["id", "designation", "reference", "quantite_disponible",
                  "quantite_totale", "statut_sterilisation", "date_sterilisation",
                  "disponible_pour_intervention", "actif"]


class MembreEquipeSerializer(serializers.ModelSerializer):
    membre = serializers.CharField(source="utilisateur.get_full_name", read_only=True)

    class Meta:
        model = MembreEquipe
        fields = ["id", "utilisateur", "membre", "role", "notifie_le"]


class EtapeChecklistSerializer(serializers.ModelSerializer):
    valide_par_nom = serializers.CharField(source="valide_par.get_full_name",
                                           read_only=True)

    class Meta:
        model = EtapeChecklist
        fields = ["id", "temps", "valide", "valide_par", "valide_par_nom", "valide_le",
                  "commentaire"]


class CompteRenduSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompteRenduOperatoire
        fields = ["id", "technique_operatoire", "constatations", "complications",
                  "suites_a_prevoir", "prescription_postoperatoire", "redige_par",
                  "redige_le"]
        read_only_fields = ["redige_par", "redige_le"]


class InterventionSerializer(serializers.ModelSerializer):
    patient_nom = serializers.CharField(source="patient.nom_complet", read_only=True)
    type_libelle = serializers.CharField(source="type_intervention.libelle",
                                         read_only=True)
    equipe = MembreEquipeSerializer(many=True, read_only=True)
    checklist = EtapeChecklistSerializer(many=True, read_only=True)
    compte_rendu = CompteRenduSerializer(read_only=True)
    duree_reelle_min = serializers.IntegerField(read_only=True)
    alertes = serializers.SerializerMethodField()

    class Meta:
        model = Intervention
        fields = ["id", "reference", "patient", "patient_nom", "type_intervention",
                  "type_libelle", "hospitalisation", "salle", "chirurgien_principal",
                  "motif_operation", "diagnostic_preop", "materiel_specifique",
                  "date_demande", "date_heure_debut_prevue", "duree_estimee_min",
                  "niveau_urgence", "statut", "faisabilite_anesthesique_validee",
                  "protocole_anesthesie", "heure_entree_salle",
                  "heure_debut_intervention", "heure_fin_intervention",
                  "heure_sortie_salle", "duree_reelle_min", "incidents_peroperatoires",
                  "motif_annulation", "equipe", "checklist", "compte_rendu", "alertes"]
        read_only_fields = ["reference", "statut", "salle", "date_heure_debut_prevue",
                            "faisabilite_anesthesique_validee", "heure_entree_salle",
                            "heure_debut_intervention", "heure_fin_intervention",
                            "heure_sortie_salle", "motif_annulation"]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_alertes(self, obj):
        from .services import alertes_intervention
        return alertes_intervention(obj) if obj.pk else []
