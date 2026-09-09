"""Tests des règles de gestion des patients (CDC 4.1 / 4.2 / 7.5)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import DossierMedical, Patient

Utilisateur = get_user_model()


class NumeroDossierTests(TestCase):
    def test_numero_dossier_est_genere_et_incremente(self):
        p1 = Patient.objects.create(nom="Traoré", prenom="Awa", sexe="F")
        p2 = Patient.objects.create(nom="Koné", prenom="Modibo", sexe="M")
        annee = date.today().year
        self.assertEqual(p1.numero_dossier, f"KS-{annee}-000001")
        self.assertEqual(p2.numero_dossier, f"KS-{annee}-000002")

    def test_dossier_medical_cree_automatiquement(self):
        p = Patient.objects.create(nom="Diarra", prenom="Fanta", sexe="F")
        self.assertTrue(DossierMedical.objects.filter(patient=p).exists())

    def test_age_calcule_a_partir_de_la_date_de_naissance(self):
        p = Patient.objects.create(
            nom="Sissoko", prenom="Ba", sexe="M",
            date_naissance=date(date.today().year - 30, 1, 1),
        )
        self.assertEqual(p.age, 30)

    def test_recherche_multicritere(self):
        p = Patient.objects.create(nom="Coulibaly", prenom="Aminata", sexe="F",
                                   telephone="76001122")
        self.assertIn(p, Patient.objects.recherche("couli"))          # nom partiel
        self.assertIn(p, Patient.objects.recherche("Aminata"))        # prénom
        self.assertIn(p, Patient.objects.recherche("76001122"))       # téléphone
        self.assertIn(p, Patient.objects.recherche(p.numero_dossier))  # n° de dossier
        self.assertNotIn(p, Patient.objects.recherche("introuvable"))


class AccesListePatientsTests(TestCase):
    def setUp(self):
        Patient.objects.create(nom="Test", prenom="Un", sexe="M")

    def test_agent_accueil_accede_a_la_liste(self):
        Utilisateur.objects.create_user("acc", password="x",
                                        role=Utilisateur.Role.AGENT_ACCUEIL)
        self.client.login(username="acc", password="x")
        reponse = self.client.get(reverse("patients:liste"))
        self.assertEqual(reponse.status_code, 200)

    def test_agent_sterilisation_est_refuse(self):
        Utilisateur.objects.create_user("ster", password="x",
                                        role=Utilisateur.Role.AGENT_STERILISATION)
        self.client.login(username="ster", password="x")
        reponse = self.client.get(reverse("patients:liste"))
        self.assertEqual(reponse.status_code, 403)

    def test_visiteur_anonyme_est_redirige_vers_la_connexion(self):
        reponse = self.client.get(reverse("patients:liste"))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn("/comptes/connexion/", reponse.url)


class ApiPatientsTests(TestCase):
    def test_creation_patient_via_api_refusee_a_l_infirmier(self):
        Utilisateur.objects.create_user("inf", password="x",
                                        role=Utilisateur.Role.INFIRMIER)
        self.client.login(username="inf", password="x")
        reponse = self.client.post("/api/v1/patients/",
                                   {"nom": "X", "prenom": "Y", "sexe": "M"})
        self.assertEqual(reponse.status_code, 403)

    def test_creation_patient_via_api_autorisee_a_l_agent_accueil(self):
        Utilisateur.objects.create_user("acc", password="x",
                                        role=Utilisateur.Role.AGENT_ACCUEIL)
        self.client.login(username="acc", password="x")
        reponse = self.client.post(
            "/api/v1/patients/",
            {"nom": "Nouveau", "prenom": "Patient", "sexe": "M"},
            content_type="application/json",
        )
        self.assertEqual(reponse.status_code, 201, reponse.content)
        self.assertTrue(reponse.json()["numero_dossier"].startswith("KS-"))
