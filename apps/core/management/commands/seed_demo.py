"""
Jeu de données de démonstration (CDC 10 — livrables).

Crée un compte administrateur, un compte par rôle métier courant et quelques
patients fictifs. Idempotent : relançable sans créer de doublons.

    python manage.py seed_demo

Mot de passe par défaut de tous les comptes : « demo1234 » (à ne jamais
utiliser hors démonstration).
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.bloc_operatoire.models import (
    Intervention,
    MaterielBloc,
    SalleOperatoire,
    TypeIntervention,
)
from apps.core.models import ParametresSysteme
from apps.hospitalisation.models import Chambre, Hospitalisation, Lit, Service
from apps.hospitalisation.services import admettre
from apps.patients.models import Patient
from apps.pharmacie.models import InteractionMedicamenteuse, Medicament
from apps.pharmacie.services import enregistrer_entree

Utilisateur = get_user_model()
MOT_DE_PASSE_DEMO = "demo1234"

COMPTES = [
    ("admin", "Aïssata", "KEÏTA", Utilisateur.Role.ADMIN, True),
    ("accueil", "Fatoumata", "SANGARÉ", Utilisateur.Role.AGENT_ACCUEIL, False),
    ("medecin", "Ibrahima", "TRAORÉ", Utilisateur.Role.MEDECIN, False),
    ("infirmier", "Salif", "DIALLO", Utilisateur.Role.INFIRMIER, False),
    ("pharmacien", "Kadiatou", "CISSÉ", Utilisateur.Role.PHARMACIEN, False),
    ("chirurgien", "Moussa", "DEMBÉLÉ", Utilisateur.Role.CHIRURGIEN, False),
    ("comptable", "Rokia", "TOURÉ", Utilisateur.Role.COMPTABLE, False),
]

PATIENTS = [
    {"nom": "Coulibaly", "prenom": "Aminata", "sexe": "F", "ville": "Bamako",
     "telephone": "76112233", "groupe_sanguin": "O+"},
    {"nom": "Konaté", "prenom": "Sékou", "sexe": "M", "ville": "Ségou",
     "telephone": "65443322", "groupe_sanguin": "A+"},
    {"nom": "Maïga", "prenom": "Hawa", "sexe": "F", "ville": "Mopti",
     "telephone": "90778811", "groupe_sanguin": "B-"},
]

MEDICAMENTS = [
    # denomination, dosage, forme, unite, seuil, stock_initial
    ("Paracétamol", "500 mg", "COMPRIME", "comprimé", 100, 400),
    ("Amoxicilline", "500 mg", "GELULE", "gélule", 60, 250),
    ("Ibuprofène", "400 mg", "COMPRIME", "comprimé", 60, 30),   # sous le seuil volontairement
    ("Métronidazole", "250 mg", "COMPRIME", "comprimé", 40, 180),
    ("Artéméther + Luméfantrine", "20/120 mg", "COMPRIME", "comprimé", 50, 300),
    ("Sérum glucosé 5%", "500 ml", "PERFUSION", "poche", 20, 60),
    ("Oméprazole", "20 mg", "GELULE", "gélule", 40, 150),
    ("Ceftriaxone", "1 g", "INJECTABLE", "flacon", 30, 90),
]


class Command(BaseCommand):
    help = "Charge un jeu de données de démonstration (comptes + patients)."

    @transaction.atomic
    def handle(self, *args, **options):
        params = ParametresSysteme.charger()
        params.langues_actives = ["fr", "en", "ar", "bm", "ff", "snk"]
        params.save()

        for username, prenom, nom, role, superuser in COMPTES:
            u, cree = Utilisateur.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": prenom, "last_name": nom, "role": role,
                    "email": f"{username}@demo.keneya.local",
                    "is_superuser": superuser, "is_staff": superuser,
                },
            )
            if cree:
                u.set_password(MOT_DE_PASSE_DEMO)
                u.save()
                self.stdout.write(self.style.SUCCESS(f"  + compte {username} ({role})"))
            else:
                self.stdout.write(f"  = compte {username} déjà présent")

        for donnees in PATIENTS:
            existe = Patient.objects.filter(
                nom=donnees["nom"], prenom=donnees["prenom"]
            ).exists()
            if existe:
                self.stdout.write(f"  = patient {donnees['nom']} {donnees['prenom']} déjà présent")
                continue
            p = Patient.objects.create(**donnees)
            self.stdout.write(self.style.SUCCESS(
                f"  + patient {p.numero_dossier} — {p.nom_complet}"
            ))

        admin = Utilisateur.objects.filter(username="admin").first()
        for deno, dosage, forme, unite, seuil, stock in MEDICAMENTS:
            med, cree = Medicament.objects.get_or_create(
                denomination=deno, dosage=dosage,
                defaults={"forme": forme, "unite": unite, "seuil_alerte": seuil},
            )
            if cree:
                enregistrer_entree(
                    medicament=med, numero_lot="LOT-DEMO-1", quantite=stock,
                    date_peremption=date.today() + timedelta(days=540),
                    utilisateur=admin, fournisseur="PPM (démo)",
                )
                self.stdout.write(self.style.SUCCESS(
                    f"  + médicament {med.denomination} ({stock} en stock)"
                ))
            else:
                self.stdout.write(f"  = médicament {med.denomination} déjà présent")

        try:
            amox = Medicament.objects.get(denomination="Amoxicilline")
            metro = Medicament.objects.get(denomination="Métronidazole")
            _inter, cree = InteractionMedicamenteuse.objects.get_or_create(
                medicament_a=amox, medicament_b=metro,
                defaults={
                    "gravite": InteractionMedicamenteuse.Gravite.MODEREE,
                    "description": "Surveiller la tolérance digestive (exemple de démonstration).",
                },
            )
            if cree:
                self.stdout.write(self.style.SUCCESS(
                    "  + interaction Amoxicilline / Metronidazole"))
        except Medicament.DoesNotExist:
            pass

        self._seed_hospitalisation()
        self._seed_bloc()

        self.stdout.write(self.style.SUCCESS(
            f"\nTerminé. Comptes de démonstration : mot de passe « {MOT_DE_PASSE_DEMO} »."
        ))

    def _seed_bloc(self):
        for nom, code, nettoyage in [("Salle A", "SOP-A", 30), ("Salle B", "SOP-B", 45)]:
            salle, cree = SalleOperatoire.objects.get_or_create(
                nom=nom, defaults={"code": code, "duree_nettoyage_min": nettoyage,
                                   "equipement": "Table opératoire, scialytique, respirateur"})
            if cree:
                self.stdout.write(self.style.SUCCESS(f"  + salle opératoire {nom}"))

        for mat, statut in [("Kit de laparotomie", "STERILISE"),
                            ("Kit d'appendicectomie", "STERILISE"),
                            ("Boîte de césarienne", "STERILISE"),
                            ("Set de coelioscopie", "EN_STERILISATION")]:
            MaterielBloc.objects.get_or_create(
                designation=mat,
                defaults={"quantite_disponible": 3, "quantite_totale": 3,
                          "statut_sterilisation": statut},
            )

        types = [
            ("Appendicectomie", "Chirurgie viscérale", 60),
            ("Césarienne", "Gynéco-obstétrique", 45),
            ("Herniorraphie inguinale", "Chirurgie viscérale", 75),
            ("Cholécystectomie", "Chirurgie viscérale", 90),
        ]
        for libelle, spec, duree in types:
            _t, cree = TypeIntervention.objects.get_or_create(
                libelle=libelle,
                defaults={"specialite": spec, "duree_standard_min": duree},
            )
            if cree:
                self.stdout.write(self.style.SUCCESS(f"  + type d'acte {libelle}"))

        patient = Patient.objects.filter(nom="Maïga", prenom="Hawa").first()
        chirurgien = Utilisateur.objects.filter(username="chirurgien").first()
        type_appendice = TypeIntervention.objects.filter(
            libelle="Appendicectomie").first()
        if patient and chirurgien and type_appendice and not Intervention.objects.filter(
                patient=patient).exists():
            interv = Intervention.objects.create(
                patient=patient, type_intervention=type_appendice,
                chirurgien_principal=chirurgien, demandeur=chirurgien,
                motif_operation="Appendicite aiguë non compliquée",
                niveau_urgence=Intervention.Urgence.URGENTE,
                duree_estimee_min=60, cree_par=chirurgien, modifie_par=chirurgien,
            )
            self.stdout.write(self.style.SUCCESS(
                f"  + intervention {interv.reference} ({patient.nom_complet}) à planifier"))

    def _seed_hospitalisation(self):
        plan = {
            "Médecine générale": {"chambres": 3, "lits_par_chambre": 2},
            "Chirurgie": {"chambres": 2, "lits_par_chambre": 2},
            "Maternité": {"chambres": 2, "lits_par_chambre": 3},
        }
        medecin = Utilisateur.objects.filter(username="medecin").first()
        for nom, conf in plan.items():
            service, cree = Service.objects.get_or_create(nom=nom)
            if cree:
                for i in range(1, conf["chambres"] + 1):
                    chambre = Chambre.objects.create(service=service, numero=f"{i:02d}")
                    for j in range(1, conf["lits_par_chambre"] + 1):
                        Lit.objects.create(chambre=chambre, numero=str(j))
                self.stdout.write(self.style.SUCCESS(
                    f"  + service {nom} ({service.nb_lits} lits)"))
            else:
                self.stdout.write(f"  = service {nom} déjà présent")

        patient = Patient.objects.filter(nom="Konaté", prenom="Sékou").first()
        service = Service.objects.filter(nom="Médecine générale").first()
        if patient and service and not patient.hospitalisations.filter(
                statut=Hospitalisation.Statut.EN_COURS).exists():
            lit = next((l for l in service.lits if l.est_disponible), None)
            if lit:
                sejour = admettre(
                    patient=patient, service=service, lit=lit,
                    motif="Paludisme grave — surveillance", medecin_referent=medecin,
                    par=medecin,
                )
                self.stdout.write(self.style.SUCCESS(
                    f"  + hospitalisation {sejour.reference} ({patient.nom_complet})"))
