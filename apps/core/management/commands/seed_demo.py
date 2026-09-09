"""
Jeu de données de démonstration (CDC 10 — livrables).

Crée un compte administrateur, un compte par rôle métier courant et quelques
patients fictifs. Idempotent : relançable sans créer de doublons.

    python manage.py seed_demo

Mot de passe par défaut de tous les comptes : « demo1234 » (à ne jamais
utiliser hors démonstration).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import ParametresSysteme
from apps.patients.models import Patient

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

        self.stdout.write(self.style.SUCCESS(
            f"\nTerminé. Comptes de démonstration : mot de passe « {MOT_DE_PASSE_DEMO} »."
        ))
