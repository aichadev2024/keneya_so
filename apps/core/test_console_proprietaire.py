"""Écrans dédiés de la console propriétaire : établissements, plans, utilisateurs, journal."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from .models import Etablissement, HistoriqueAction, Plan

Utilisateur = get_user_model()

MDP = "MotDePasseDuProprietaire2026!"


def creer_proprietaire(username="proprio"):
    u = Utilisateur.tous.create_superuser(username, f"{username}@keneya.ml", MDP)
    return u


def creer_admin_hopital(etab, username="adm"):
    u = Utilisateur(username=username, role=Utilisateur.Role.ADMIN, etablissement=etab)
    u.set_password(MDP)
    u.save()
    return u


class AccesReserveAuProprietaireTests(TestCase):
    """Chaque écran de la console propriétaire est fermé à qui n'est pas le propriétaire."""

    def setUp(self):
        self.etab = Etablissement.objects.create(nom="Hôpital A", slug="hopital-a", statut="ACTIF")
        self.admin = creer_admin_hopital(self.etab)

    def _urls(self):
        return [
            reverse("core:proprietaire_etablissements"),
            reverse("core:proprietaire_etablissement_creer"),
            reverse("core:proprietaire_etablissement", args=[self.etab.pk]),
            reverse("core:proprietaire_plans"),
            reverse("core:proprietaire_plan_creer"),
            reverse("core:proprietaire_utilisateurs"),
            reverse("core:proprietaire_utilisateur_creer"),
            reverse("core:proprietaire_journal"),
        ]

    def test_anonyme_redirige_vers_la_connexion(self):
        for url in self._urls():
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_un_administrateur_d_hopital_recoit_403(self):
        self.client.login(username="adm", password=MDP)
        for url in self._urls():
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_le_proprietaire_y_accede(self):
        creer_proprietaire()
        self.client.login(username="proprio", password=MDP)
        for url in self._urls():
            self.assertEqual(self.client.get(url).status_code, 200, url)


class EtablissementListeTests(TestCase):
    def setUp(self):
        creer_proprietaire()
        self.client.login(username="proprio", password=MDP)
        Etablissement.objects.create(nom="Hôpital du Point G", slug="point-g", statut="ACTIF")
        Etablissement.objects.create(nom="Clinique Bon Secours", slug="bon-secours", statut="ESSAI",
                                     essai_jusqu_au=date.today() + timedelta(days=10))

    def test_liste_tous_les_etablissements(self):
        page = self.client.get(reverse("core:proprietaire_etablissements"))
        self.assertContains(page, "Hôpital du Point G")
        self.assertContains(page, "Clinique Bon Secours")

    def test_recherche_par_nom(self):
        page = self.client.get(reverse("core:proprietaire_etablissements"), {"q": "Point G"})
        self.assertContains(page, "Hôpital du Point G")
        self.assertNotContains(page, "Clinique Bon Secours")

    def test_filtre_par_statut(self):
        page = self.client.get(reverse("core:proprietaire_etablissements"), {"statut": "ESSAI"})
        self.assertContains(page, "Clinique Bon Secours")
        self.assertNotContains(page, "Hôpital du Point G")


class EtablissementCreationTests(TestCase):
    def setUp(self):
        creer_proprietaire()
        self.client.login(username="proprio", password=MDP)
        self.url = reverse("core:proprietaire_etablissement_creer")

    def _post(self, **over):
        donnees = {"nom": "Hôpital de Sikasso", "statut": "ESSAI", "essai_jusqu_au": "",
                   "admin_prenom": "Fanta", "admin_nom": "Coulibaly", "admin_email": "fanta@sikasso.ml",
                   "admin_username": "fanta_admin"}
        donnees.update(over)
        return self.client.post(self.url, donnees)

    def test_creation_de_l_hopital_et_de_son_administrateur(self):
        reponse = self._post()
        etab = Etablissement.objects.get(nom="Hôpital de Sikasso")
        self.assertRedirects(reponse, reverse("core:proprietaire_etablissement", args=[etab.pk]))
        self.assertEqual(etab.slug, "hopital-de-sikasso")
        self.assertEqual(etab.essai_jusqu_au, date.today() + timedelta(days=30))
        admin = Utilisateur.tous.get(username="fanta_admin")
        self.assertEqual(admin.etablissement_id, etab.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["fanta@sikasso.ml"])

    def test_identifiant_deja_pris_refuse(self):
        self._post()
        reponse = self._post(nom="Autre hôpital")
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "déjà utilisé")
        self.assertFalse(Etablissement.objects.filter(nom="Autre hôpital").exists())

    def test_hopital_actif_directement_sans_date_d_essai(self):
        self._post(statut="ACTIF")
        etab = Etablissement.objects.get(nom="Hôpital de Sikasso")
        self.assertIsNone(etab.essai_jusqu_au)
        self.assertTrue(etab.acces_autorise)


class EtablissementDetailEtActionsTests(TestCase):
    def setUp(self):
        creer_proprietaire()
        self.client.login(username="proprio", password=MDP)
        self.etab = Etablissement.objects.create(
            nom="Hôpital B", slug="hopital-b", statut="ESSAI",
            essai_jusqu_au=date.today() - timedelta(days=1))
        creer_admin_hopital(self.etab, "adm_b")

    def test_la_fiche_liste_le_personnel_et_les_chiffres(self):
        page = self.client.get(reverse("core:proprietaire_etablissement", args=[self.etab.pk]))
        self.assertContains(page, "adm_b")
        self.assertContains(page, "Illimité")  # pas de plan => pas de limite

    def test_modifier_l_etablissement(self):
        url = reverse("core:proprietaire_etablissement_modifier", args=[self.etab.pk])
        reponse = self.client.post(url, {
            "nom": "Hôpital B renommé", "statut": "ACTIF", "essai_jusqu_au": ""})
        self.etab.refresh_from_db()
        self.assertEqual(self.etab.nom, "Hôpital B renommé")
        self.assertEqual(self.etab.statut, "ACTIF")
        self.assertRedirects(reponse, reverse("core:proprietaire_etablissement", args=[self.etab.pk]))

    def test_activer_debloque_un_essai_termine(self):
        self.assertFalse(self.etab.acces_autorise)
        self.client.post(reverse("core:proprietaire_etablissement_activer", args=[self.etab.pk]))
        self.etab.refresh_from_db()
        self.assertEqual(self.etab.statut, "ACTIF")
        self.assertIsNone(self.etab.essai_jusqu_au)
        self.assertTrue(self.etab.acces_autorise)

    def test_suspendre_bloque_l_acces(self):
        self.client.post(reverse("core:proprietaire_etablissement_suspendre", args=[self.etab.pk]))
        self.etab.refresh_from_db()
        self.assertEqual(self.etab.statut, "SUSPENDU")
        self.assertFalse(self.etab.acces_autorise)

    def test_prolonger_l_essai_de_30_jours_a_partir_d_aujourd_hui(self):
        self.client.post(reverse("core:proprietaire_etablissement_prolonger_essai", args=[self.etab.pk]))
        self.etab.refresh_from_db()
        self.assertEqual(self.etab.essai_jusqu_au, date.today() + timedelta(days=30))
        self.assertEqual(self.etab.statut, "ESSAI")
        self.assertTrue(self.etab.acces_autorise)

    def test_les_actions_sont_en_lecture_seule_pour_un_admin_d_hopital(self):
        self.client.logout()
        self.client.login(username="adm_b", password=MDP)
        reponse = self.client.post(
            reverse("core:proprietaire_etablissement_activer", args=[self.etab.pk]))
        self.assertEqual(reponse.status_code, 403)
        self.etab.refresh_from_db()
        self.assertEqual(self.etab.statut, "ESSAI")

    def test_les_actions_refusent_get(self):
        reponse = self.client.get(
            reverse("core:proprietaire_etablissement_activer", args=[self.etab.pk]))
        self.assertEqual(reponse.status_code, 405)


class PlanTests(TestCase):
    def setUp(self):
        creer_proprietaire()
        self.client.login(username="proprio", password=MDP)

    def test_creation_d_un_plan(self):
        reponse = self.client.post(reverse("core:proprietaire_plan_creer"), {
            "nom": "Sur mesure", "code": "sur-mesure", "prix_mensuel": "50000",
            "max_utilisateurs": "100", "actif": "on"})
        self.assertRedirects(reponse, reverse("core:proprietaire_plans"))
        plan = Plan.objects.get(code="sur-mesure")
        self.assertEqual(plan.max_utilisateurs, 100)

    def test_modification_d_un_plan(self):
        plan = Plan.objects.create(nom="Essentiel", code="essentiel-2", max_utilisateurs=15)
        self.client.post(reverse("core:proprietaire_plan_modifier", args=[plan.pk]), {
            "nom": "Essentiel", "code": "essentiel-2", "prix_mensuel": "", "max_utilisateurs": ""})
        plan.refresh_from_db()
        self.assertIsNone(plan.max_utilisateurs)  # vide = illimité

    def test_liste_compte_les_hopitaux_par_plan(self):
        plan = Plan.objects.create(nom="Essentiel", code="essentiel-3")
        Etablissement.objects.create(nom="Hôpital C", slug="hopital-c", statut="ACTIF", plan=plan)
        page = self.client.get(reverse("core:proprietaire_plans"))
        self.assertContains(page, "Essentiel")


class UtilisateurListeEtCreationTests(TestCase):
    def setUp(self):
        creer_proprietaire()
        self.client.login(username="proprio", password=MDP)
        self.etab_a = Etablissement.objects.create(nom="Hôpital A", slug="hopital-a-u", statut="ACTIF")
        self.etab_b = Etablissement.objects.create(nom="Hôpital B", slug="hopital-b-u", statut="ACTIF")
        creer_admin_hopital(self.etab_a, "adm_a")
        creer_admin_hopital(self.etab_b, "adm_b")

    def test_la_liste_montre_tous_les_hopitaux(self):
        page = self.client.get(reverse("core:proprietaire_utilisateurs"))
        self.assertContains(page, "adm_a")
        self.assertContains(page, "adm_b")

    def test_filtre_par_etablissement(self):
        page = self.client.get(reverse("core:proprietaire_utilisateurs"),
                               {"etablissement": self.etab_a.pk})
        self.assertContains(page, "adm_a")
        self.assertNotContains(page, "adm_b")

    def test_recherche_par_nom(self):
        page = self.client.get(reverse("core:proprietaire_utilisateurs"), {"q": "adm_a"})
        self.assertContains(page, "adm_a")
        self.assertNotContains(page, "adm_b")

    def test_creation_preremplie_avec_l_etablissement_passe_en_parametre(self):
        url = reverse("core:proprietaire_utilisateur_creer") + f"?etablissement={self.etab_a.pk}"
        page = self.client.get(url)
        self.assertContains(page, f'value="{self.etab_a.pk}" selected')

    def test_creation_envoie_l_invitation_et_rattache_le_bon_hopital(self):
        reponse = self.client.post(reverse("core:proprietaire_utilisateur_creer"), {
            "username": "dr_test", "first_name": "Ali", "last_name": "Koné",
            "email": "ali@hopital-a.ml", "role": "MEDECIN", "etablissement": self.etab_a.pk,
            "langue_preferee": "fr"})
        nouveau = Utilisateur.tous.get(username="dr_test")
        self.assertRedirects(
            reponse, f"{reverse('core:proprietaire_utilisateurs')}?etablissement={self.etab_a.pk}")
        self.assertEqual(nouveau.etablissement_id, self.etab_a.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ali@hopital-a.ml"])
        self.assertFalse(nouveau.has_usable_password() is False)  # mot de passe aléatoire, pas vide
        self.assertNotIn("password", mail.outbox[0].body.lower())

    def test_email_obligatoire_a_la_creation(self):
        reponse = self.client.post(reverse("core:proprietaire_utilisateur_creer"), {
            "username": "sans_email", "first_name": "A", "last_name": "B", "email": "",
            "role": "MEDECIN", "etablissement": self.etab_a.pk, "langue_preferee": "fr"})
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Utilisateur.tous.filter(username="sans_email").exists())

    def test_etablissement_obligatoire_a_la_creation(self):
        reponse = self.client.post(reverse("core:proprietaire_utilisateur_creer"), {
            "username": "sans_hopital", "first_name": "A", "last_name": "B",
            "email": "a@b.ml", "role": "MEDECIN", "langue_preferee": "fr"})
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Utilisateur.tous.filter(username="sans_hopital").exists())


class UtilisateurModificationEtActionsTests(TestCase):
    def setUp(self):
        creer_proprietaire()
        self.client.login(username="proprio", password=MDP)
        self.etab = Etablissement.objects.create(nom="Hôpital A", slug="hopital-a-m", statut="ACTIF")
        self.autre = Etablissement.objects.create(nom="Hôpital Z", slug="hopital-z-m", statut="ACTIF")
        self.medecin = Utilisateur(username="dr_x", email="drx@a.ml", role=Utilisateur.Role.MEDECIN,
                                   etablissement=self.etab)
        self.medecin.set_password(MDP)
        self.medecin.save()

    def test_modifier_un_compte_y_compris_le_changer_d_hopital(self):
        url = reverse("core:proprietaire_utilisateur_modifier", args=[self.medecin.pk])
        reponse = self.client.post(url, {
            "username": "dr_x", "first_name": "Nouveau", "last_name": "Nom", "email": "drx@a.ml",
            "etablissement": self.autre.pk, "role": "MEDECIN", "langue_preferee": "fr",
            "is_active": "on"})
        self.medecin.refresh_from_db()
        self.assertEqual(self.medecin.etablissement_id, self.autre.pk)
        self.assertEqual(self.medecin.first_name, "Nouveau")
        self.assertRedirects(
            reponse, f"{reverse('core:proprietaire_utilisateurs')}?etablissement={self.autre.pk}")

    def test_renvoyer_l_invitation(self):
        url = reverse("core:proprietaire_utilisateur_renvoyer_invitation", args=[self.medecin.pk])
        self.client.post(url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["drx@a.ml"])

    def test_renvoyer_l_invitation_sans_email_echoue_proprement(self):
        self.medecin.email = ""
        self.medecin.save()
        url = reverse("core:proprietaire_utilisateur_renvoyer_invitation", args=[self.medecin.pk])
        self.client.post(url)
        self.assertEqual(len(mail.outbox), 0)

    def test_basculer_actif(self):
        self.assertTrue(self.medecin.is_active)
        url = reverse("core:proprietaire_utilisateur_basculer_actif", args=[self.medecin.pk])
        self.client.post(url)
        self.medecin.refresh_from_db()
        self.assertFalse(self.medecin.is_active)
        self.client.post(url)
        self.medecin.refresh_from_db()
        self.assertTrue(self.medecin.is_active)

    def test_le_mot_de_passe_ne_se_change_pas_depuis_ce_formulaire(self):
        page = self.client.get(reverse("core:proprietaire_utilisateur_modifier", args=[self.medecin.pk]))
        self.assertNotContains(page, 'name="password"')
        self.assertNotContains(page, 'name="password1"')


class JournalAuditTests(TestCase):
    def setUp(self):
        creer_proprietaire()
        self.client.login(username="proprio", password=MDP)
        self.etab_a = Etablissement.objects.create(nom="Hôpital A", slug="hopital-a-j", statut="ACTIF")
        self.etab_b = Etablissement.objects.create(nom="Hôpital B", slug="hopital-b-j", statut="ACTIF")
        HistoriqueAction.objects.create(etablissement=self.etab_a, action="CREATION",
                                        description="Action chez A")
        HistoriqueAction.objects.create(etablissement=self.etab_b, action="MODIFICATION",
                                        description="Action chez B")

    def test_le_journal_montre_tous_les_hopitaux(self):
        page = self.client.get(reverse("core:proprietaire_journal"))
        self.assertContains(page, "Action chez A")
        self.assertContains(page, "Action chez B")

    def test_filtre_par_type_d_action(self):
        page = self.client.get(reverse("core:proprietaire_journal"), {"action": "MODIFICATION"})
        self.assertContains(page, "Action chez B")
        self.assertNotContains(page, "Action chez A")

    def test_recherche_par_description(self):
        page = self.client.get(reverse("core:proprietaire_journal"), {"q": "chez A"})
        self.assertContains(page, "Action chez A")
        self.assertNotContains(page, "Action chez B")
