"""Isolation multi-établissements (SaaS) : un hôpital ne voit jamais les données d'un autre."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Etablissement, Notification
from apps.core.tenancy import AUCUN, HORS_REQUETE, TOUS, contexte_courant, pour_etablissement
from apps.hospitalisation.models import Service
from apps.patients.models import Patient

Utilisateur = get_user_model()


class BaseDeuxHopitaux(TestCase):
    def setUp(self):
        self.a = Etablissement.objects.create(nom="Hôpital A", slug="a", statut="ACTIF")
        self.b = Etablissement.objects.create(nom="Hôpital B", slug="b", statut="ACTIF")
        role = Utilisateur.Role
        self.med_a = Utilisateur.objects.create_user(
            "med_a", password="x", role=role.MEDECIN, etablissement=self.a)
        self.med_b = Utilisateur.objects.create_user(
            "med_b", password="x", role=role.MEDECIN, etablissement=self.b)
        self.admin_b = Utilisateur.objects.create_user(
            "admin_b", password="x", role=role.ADMIN, etablissement=self.b)
        with pour_etablissement(self.a):
            self.patient_a = Patient.objects.create(nom="PatientHopitalA", prenom="Awa", sexe="F")
        with pour_etablissement(self.b):
            self.patient_b = Patient.objects.create(nom="PatientHopitalB", prenom="Ali", sexe="M")


class GestionnaireTests(BaseDeuxHopitaux):
    def test_le_gestionnaire_filtre_selon_le_contexte(self):
        with pour_etablissement(self.a):
            self.assertEqual(list(Patient.objects.all()), [self.patient_a])
        with pour_etablissement(self.b):
            self.assertEqual(list(Patient.objects.all()), [self.patient_b])

    def test_contexte_aucun_ne_montre_rien_et_tous_montre_tout(self):
        with pour_etablissement(AUCUN):
            self.assertEqual(Patient.objects.count(), 0)
        with pour_etablissement(TOUS):
            self.assertEqual(Patient.objects.count(), 2)

    def test_creation_sans_etablissement_actif_est_refusee(self):
        with pour_etablissement(AUCUN):
            with self.assertRaises(Exception):
                Patient.objects.create(nom="X", prenom="Y", sexe="M")

    def test_un_enfant_herite_de_l_etablissement_de_son_parent(self):
        # Même sous un autre contexte, le dossier médical suit le patient.
        with pour_etablissement(self.b):
            dossier = self.patient_a.dossier_medical
        self.assertEqual(dossier.etablissement_id, self.a.pk)

    def test_numerotation_independante_par_hopital(self):
        annee = date.today().year
        self.assertEqual(self.patient_a.numero_dossier, f"KS-{annee}-000001")
        self.assertEqual(self.patient_b.numero_dossier, f"KS-{annee}-000001")

    def test_memes_noms_autorises_dans_deux_hopitaux(self):
        with pour_etablissement(self.a):
            Service.objects.create(nom="Pédiatrie")
        with pour_etablissement(self.b):
            Service.objects.create(nom="Pédiatrie")
        with pour_etablissement(TOUS):
            self.assertEqual(Service.objects.filter(nom="Pédiatrie").count(), 2)

    def test_le_contexte_est_remis_a_zero_apres_une_requete(self):
        self.client.login(username="med_a", password="x")
        self.client.get(reverse("patients:liste"))
        self.assertIs(contexte_courant(), HORS_REQUETE)


class AccesHtmlTests(BaseDeuxHopitaux):
    def setUp(self):
        super().setUp()
        self.client.login(username="med_b", password="x")

    def test_la_liste_ne_montre_que_son_hopital(self):
        reponse = self.client.get(reverse("patients:liste"))
        self.assertContains(reponse, "PATIENTHOPITALB")
        self.assertNotContains(reponse, "PATIENTHOPITALA")

    def test_la_recherche_ne_trouve_pas_les_patients_d_un_autre_hopital(self):
        reponse = self.client.get(reverse("patients:liste"), {"q": "Awa"})  # prénom du patient A
        self.assertNotContains(reponse, "PATIENTHOPITALA")

    def test_fiche_d_un_patient_d_un_autre_hopital_introuvable(self):
        self.assertEqual(
            self.client.get(reverse("patients:detail", args=[self.patient_a.pk])).status_code, 404)

    def test_modification_d_un_patient_d_un_autre_hopital_introuvable(self):
        self.assertEqual(
            self.client.get(reverse("patients:modifier", args=[self.patient_a.pk])).status_code, 404)

    def test_consultation_pour_un_patient_d_un_autre_hopital_introuvable(self):
        self.assertEqual(
            self.client.get(reverse("consultations:creer", args=[self.patient_a.pk])).status_code, 404)

    def test_notifications_isolees(self):
        Notification.notifier(destinataire=self.med_a, titre="Secret hôpital A")
        reponse = self.client.get(reverse("core:notifications"))
        self.assertNotContains(reponse, "Secret hôpital A")


class AccesApiTests(BaseDeuxHopitaux):
    def setUp(self):
        super().setUp()
        self.client.login(username="med_b", password="x")

    def test_api_patients_liste_isolee(self):
        reponse = self.client.get("/api/v1/patients/")
        self.assertEqual(reponse.status_code, 200)
        noms = [p["nom"] for p in reponse.json()["results"]]
        self.assertEqual(noms, ["PatientHopitalB"])

    def test_api_patient_d_un_autre_hopital_introuvable(self):
        self.assertEqual(self.client.get(f"/api/v1/patients/{self.patient_a.pk}/").status_code, 404)

    def test_api_utilisateurs_isolee(self):
        self.client.login(username="admin_b", password="x")
        reponse = self.client.get("/api/v1/utilisateurs/")
        if reponse.status_code == 200:
            usernames = {u["username"] for u in reponse.json()["results"]}
            self.assertNotIn("med_a", usernames)
            self.assertIn("med_b", usernames)


class ComptesSansEtablissementTests(BaseDeuxHopitaux):
    def test_compte_sans_etablissement_ne_voit_aucune_donnee(self):
        Utilisateur.tous.filter(username="med_b").update(etablissement=None)
        self.client.login(username="med_b", password="x")
        reponse = self.client.get(reverse("patients:liste"))
        self.assertNotContains(reponse, "PATIENTHOPITALA")
        self.assertNotContains(reponse, "PATIENTHOPITALB")

    def test_visiteur_anonyme_refuse_sur_l_api(self):
        self.assertIn(self.client.get("/api/v1/patients/").status_code, (401, 403))


class AdministrationTests(BaseDeuxHopitaux):
    def test_un_admin_d_hopital_ne_liste_que_ses_utilisateurs(self):
        self.client.login(username="admin_b", password="x")
        reponse = self.client.get(reverse("admin:accounts_utilisateur_changelist"))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "med_b")
        self.assertNotContains(reponse, "med_a")

    def test_un_admin_d_hopital_ne_peut_pas_ouvrir_un_utilisateur_d_un_autre_hopital(self):
        self.client.login(username="admin_b", password="x")
        url = reverse("admin:accounts_utilisateur_change", args=[self.med_a.pk])
        self.assertIn(self.client.get(url, follow=True).status_code, (200, 404))
        reponse = self.client.get(url, follow=True)
        self.assertNotContains(reponse, "med_a")

    def test_un_admin_d_hopital_n_a_pas_les_champs_de_privilege(self):
        self.client.login(username="admin_b", password="x")
        url = reverse("admin:accounts_utilisateur_change", args=[self.med_b.pk])
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200)
        for champ in ("is_superuser", "user_permissions", "etablissement", "groups"):
            self.assertNotContains(reponse, f'name="{champ}"')

    def test_un_admin_d_hopital_n_a_pas_acces_aux_groupes_ni_aux_etablissements(self):
        self.client.login(username="admin_b", password="x")
        for nom in ("admin:auth_group_changelist", "admin:core_etablissement_changelist"):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 403, nom)

    def test_le_super_admin_de_la_plateforme_voit_tous_les_hopitaux(self):
        Utilisateur.objects.create_superuser("plateforme", password="x")
        self.client.login(username="plateforme", password="x")
        reponse = self.client.get(reverse("admin:accounts_utilisateur_changelist"))
        self.assertContains(reponse, "med_a")
        self.assertContains(reponse, "med_b")
        reponse = self.client.get(reverse("admin:core_etablissement_changelist"))
        self.assertContains(reponse, "Hôpital A")
        self.assertContains(reponse, "Hôpital B")


# Construit à l'import, donc hors de toute requête : le piège qui a causé une fuite
# sur l'API avant que le filtre ne soit déplacé à l'exécution SQL.
QUERYSET_CONSTRUIT_A_L_IMPORT = Patient.objects.all()


class PiegesDeConstructionTests(BaseDeuxHopitaux):
    def test_queryset_construit_a_l_import_est_filtre_a_l_execution(self):
        with pour_etablissement(self.a):
            self.assertEqual(QUERYSET_CONSTRUIT_A_L_IMPORT.all().count(), 1)
            self.assertTrue(QUERYSET_CONSTRUIT_A_L_IMPORT.exists())
            self.assertEqual([p.pk for p in QUERYSET_CONSTRUIT_A_L_IMPORT.all()], [self.patient_a.pk])
        with pour_etablissement(self.b):
            self.assertEqual([p.pk for p in QUERYSET_CONSTRUIT_A_L_IMPORT.all()], [self.patient_b.pk])
        with pour_etablissement(AUCUN):
            self.assertEqual(QUERYSET_CONSTRUIT_A_L_IMPORT.all().count(), 0)

    def test_update_et_delete_de_masse_restent_dans_l_etablissement(self):
        with pour_etablissement(self.a):
            Service.objects.create(nom="S-A")
        with pour_etablissement(self.b):
            Service.objects.create(nom="S-B")
        with pour_etablissement(self.a):
            Patient.objects.all().update(ville="Bamako")
            Service.objects.all().delete()
        with pour_etablissement(TOUS):
            self.assertEqual(Patient.objects.get(pk=self.patient_a.pk).ville, "Bamako")
            self.assertEqual(Patient.objects.get(pk=self.patient_b.pk).ville, "")
            self.assertEqual(list(Service.objects.values_list("nom", flat=True)), ["S-B"])

    def test_aggregation_et_statistiques_isolees(self):
        from apps.core.statistiques import tableau_de_bord_general
        with pour_etablissement(self.a):
            Patient.objects.create(nom="Deux", prenom="A", sexe="F")
            stats_a = tableau_de_bord_general()
        with pour_etablissement(self.b):
            stats_b = tableau_de_bord_general()
        self.assertEqual(stats_a["frequentation"]["patients_total"], 2)
        self.assertEqual(stats_b["frequentation"]["patients_total"], 1)

    def test_tout_modele_metier_est_rattache_a_un_etablissement(self):
        """Garde-fou : un futur modèle oublié ici serait partagé entre tous les hôpitaux."""
        from django.apps import apps as registre
        from apps.core.models import TenantOwnedModel

        exemptes = {"Etablissement", "Utilisateur", "HistoriqueAction"}
        oublies = [
            m.__name__ for m in registre.get_models()
            if m.__module__.startswith("apps.") and not issubclass(m, TenantOwnedModel)
            and m.__name__ not in exemptes
        ]
        self.assertEqual(oublies, [])
