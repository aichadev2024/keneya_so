"""
Passage au multi-établissements : rattache toutes les données existantes à un
établissement par défaut (celui de l'installation historique).

Doit s'exécuter après l'ajout de la colonne ``etablissement`` sur chaque table
et avant qu'elle ne devienne obligatoire (migrations ``*_etablissement_obligatoire``).
"""

from django.db import migrations

MODELES_RATTACHES = [
    ("core", "ParametresSysteme"),
    ("core", "Notification"),
    ("core", "HistoriqueAction"),
    ("accounts", "Utilisateur"),
    ("patients", "Patient"), ("patients", "DossierMedical"), ("patients", "Allergie"),
    ("consultations", "Consultation"), ("consultations", "Constantes"),
    ("consultations", "Ordonnance"), ("consultations", "LigneOrdonnance"),
    ("pharmacie", "Medicament"), ("pharmacie", "LotMedicament"),
    ("pharmacie", "MouvementStock"), ("pharmacie", "InteractionMedicamenteuse"),
    ("pharmacie", "Dispensation"), ("pharmacie", "LigneDispensation"),
    ("hospitalisation", "Service"), ("hospitalisation", "Chambre"),
    ("hospitalisation", "Lit"), ("hospitalisation", "Hospitalisation"),
    ("hospitalisation", "MouvementLit"), ("hospitalisation", "NoteSuivi"),
    ("bloc_operatoire", "SalleOperatoire"), ("bloc_operatoire", "MaterielBloc"),
    ("bloc_operatoire", "TypeIntervention"), ("bloc_operatoire", "MaterielRequis"),
    ("bloc_operatoire", "Intervention"), ("bloc_operatoire", "MembreEquipe"),
    ("bloc_operatoire", "EtapeChecklist"), ("bloc_operatoire", "CompteRenduOperatoire"),
    ("bloc_operatoire", "IndisponibiliteSalle"),
    ("laboratoire", "TypeExamen"), ("laboratoire", "DemandeExamen"),
    ("laboratoire", "LigneExamen"), ("laboratoire", "Resultat"),
    ("facturation", "Tarif"), ("facturation", "Facture"), ("facturation", "LigneFacture"),
    ("facturation", "Paiement"), ("facturation", "Relance"),
    ("assurances", "Assurance"), ("assurances", "ContratAssurance"),
    ("assurances", "PatientAssure"), ("assurances", "BordereauAssurance"),
    ("assurances", "LigneBordereau"),
]


def rattacher(apps, schema_editor):
    Etablissement = apps.get_model("core", "Etablissement")
    Parametres = apps.get_model("core", "ParametresSysteme")

    # Rien à rattacher sur une base vide (nouvelle installation, tests).
    a_rattacher = False
    for app_label, nom in MODELES_RATTACHES:
        Modele = apps.get_model(app_label, nom)
        if Modele._default_manager.filter(etablissement__isnull=True).exists():
            a_rattacher = True
            break
    if not a_rattacher:
        return

    etab = Etablissement.objects.order_by("pk").first()
    if etab is None:
        params = Parametres.objects.order_by("pk").first()
        etab = Etablissement.objects.create(
            nom=(params.nom_etablissement if params else "Établissement principal"),
            slug="principal", statut="ACTIF",
        )

    for app_label, nom in MODELES_RATTACHES:
        Modele = apps.get_model(app_label, nom)
        qs = Modele._default_manager.filter(etablissement__isnull=True)
        if app_label == "accounts":
            # Les super-administrateurs de la plateforme n'appartiennent à aucun établissement.
            qs = qs.filter(is_superuser=False)
        qs.update(etablissement=etab)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_etablissement_historiqueaction_etablissement_and_more"),
        ("accounts", "0002_alter_utilisateur_managers_utilisateur_etablissement_and_more"),
        ("patients", "0002_allergie_etablissement_dossiermedical_etablissement_and_more"),
        ("consultations", "0003_constantes_etablissement_consultation_etablissement_and_more"),
        ("pharmacie", "0003_dispensation_etablissement_and_more"),
        ("hospitalisation", "0002_chambre_etablissement_hospitalisation_etablissement_and_more"),
        ("bloc_operatoire", "0002_compterenduoperatoire_etablissement_and_more"),
        ("laboratoire", "0002_demandeexamen_etablissement_and_more"),
        ("facturation", "0003_facture_etablissement_lignefacture_etablissement_and_more"),
        ("assurances", "0003_assurance_etablissement_and_more"),
    ]

    operations = [migrations.RunPython(rattacher, migrations.RunPython.noop)]
