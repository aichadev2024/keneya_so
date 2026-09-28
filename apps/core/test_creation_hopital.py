"""Le propriétaire crée les hôpitaux ; l'inscription publique est fermée par défaut."""

import re
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Etablissement, ParametresSysteme, Plan
from apps.core.tenancy import pour_etablissement
from apps.facturation.models import Tarif

Utilisateur = get_user_model()

MDP = "MotDePasseDeLAdministrateur2026!"


class InscriptionFermeeParDefautTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_la_page_d_inscription_publique_est_fermee(self):
        self.assertEqual(self.client.get(reverse("accounts:inscription_hopital")).status_code, 404)
        reponse = self.client.post(reverse("accounts:inscription_hopital"), {
            "nom_hopital": "Pirate", "prenom": "A", "nom": "B", "email": "a@b.ml",
            "username": "pirate", "password1": MDP, "password2": MDP})
        self.assertEqual(reponse.status_code, 404)
        self.assertFalse(Etablissement.objects.filter(nom="Pirate").exists())

    def test_la_vitrine_et_la_connexion_ne_proposent_plus_d_inscription(self):
        url = reverse("accounts:inscription_hopital")
        for page in (reverse("core:accueil"), reverse("accounts:login")):
            self.assertNotContains(self.client.get(page), url, msg_prefix=page)

    @override_settings(CONTACT_EMAIL="contact@keneya.ml")
    def test_la_vitrine_propose_de_nous_contacter_si_une_adresse_est_configuree(self):
        self.assertContains(self.client.get(reverse("core:accueil")), "mailto:contact@keneya.ml")

    def test_sans_adresse_de_contact_aucun_lien_mailto(self):
        self.assertNotContains(self.client.get(reverse("core:accueil")), "mailto:")

    @override_settings(INSCRIPTION_LIBRE=True)
    def test_on_peut_rouvrir_l_inscription_libre(self):
        self.assertEqual(self.client.get(reverse("accounts:inscription_hopital")).status_code, 200)
        self.assertContains(self.client.get(reverse("core:accueil")),
                            reverse("accounts:inscription_hopital"))


class CreationHopitalParLeProprietaireTests(TestCase):
    def setUp(self):
        cache.clear()
        self.proprio = Utilisateur.tous.create_superuser("proprio", "proprio@keneya.ml", "x")
        self.client.login(username="proprio", password="x")
        self.url = reverse("admin:core_etablissement_add")
        self.plan = Plan.objects.get(code="essentiel")

    def _creer(self, **over):
        donnees = {"nom": "Hôpital de Sikasso", "plan": self.plan.pk, "statut": "ESSAI",
                   "essai_jusqu_au": "", "admin_prenom": "Fanta", "admin_nom": "Coulibaly",
                   "admin_email": "fanta@sikasso.ml", "admin_username": "fanta_admin"}
        donnees.update(over)
        return self.client.post(self.url, donnees)

    def test_le_formulaire_de_creation_s_affiche(self):
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        for champ in ("nom", "plan", "admin_email", "admin_username"):
            self.assertContains(page, f'name="{champ}"')

    def test_creation_de_l_hopital_et_de_son_administrateur(self):
        reponse = self._creer()
        self.assertEqual(reponse.status_code, 302)
        etab = Etablissement.objects.get(nom="Hôpital de Sikasso")
        self.assertEqual(etab.slug, "hopital-de-sikasso")
        self.assertEqual(etab.plan, self.plan)
        self.assertEqual(etab.statut, "ESSAI")
        self.assertEqual(etab.essai_jusqu_au, date.today() + timedelta(days=30))
        admin = Utilisateur.tous.get(username="fanta_admin")
        self.assertEqual(admin.etablissement_id, etab.pk)
        self.assertEqual(admin.role, Utilisateur.Role.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertFalse(admin.is_superuser)

    def test_l_hopital_est_prepare_comme_apres_une_inscription(self):
        self._creer()
        etab = Etablissement.objects.get(nom="Hôpital de Sikasso")
        with pour_etablissement(etab):
            self.assertTrue(ParametresSysteme.objects.filter(nom_etablissement="Hôpital de Sikasso").exists())
            self.assertTrue(Tarif.objects.exists())

    def test_l_administrateur_recoit_une_invitation_sans_mot_de_passe(self):
        self._creer()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["fanta@sikasso.ml"])
        self.assertIn("Hôpital de Sikasso", message.subject)
        self.assertIn("fanta_admin", message.body)
        self.assertIn("/comptes/invitation/", message.body)
        self.assertNotIn("password", message.body.lower())

    def test_l_administrateur_active_son_compte_et_arrive_dans_son_hopital(self):
        self._creer()
        self.client.logout()
        lien = re.search(r"https?://[^/\s]+(/\S*invitation/\S+)", mail.outbox[0].body).group(1)
        suite = self.client.get(lien, follow=True).redirect_chain[-1][0]
        reponse = self.client.post(suite, {"new_password1": MDP, "new_password2": MDP})
        self.assertRedirects(reponse, reverse("core:dashboard"), fetch_redirect_response=False)
        tableau = self.client.get(reverse("core:dashboard"))
        self.assertContains(tableau, "essai")  # bandeau d'essai de son hôpital

    def test_hopital_actif_directement_sans_date_d_essai(self):
        self._creer(statut="ACTIF")
        etab = Etablissement.objects.get(nom="Hôpital de Sikasso")
        self.assertIsNone(etab.essai_jusqu_au)
        self.assertTrue(etab.acces_autorise)

    def test_identifiant_deja_pris_refuse(self):
        self._creer()
        reponse = self._creer(nom="Autre hôpital")
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "déjà utilisé")
        self.assertFalse(Etablissement.objects.filter(nom="Autre hôpital").exists())

    def test_deux_hopitaux_du_meme_nom_ont_des_identifiants_courts_distincts(self):
        self._creer()
        self._creer(admin_username="autre_admin", admin_email="autre@sikasso.ml")
        slugs = set(Etablissement.objects.filter(nom="Hôpital de Sikasso").values_list("slug", flat=True))
        self.assertEqual(slugs, {"hopital-de-sikasso", "hopital-de-sikasso-2"})

    def test_la_modification_d_un_hopital_reste_le_formulaire_standard(self):
        self._creer()
        etab = Etablissement.objects.get(nom="Hôpital de Sikasso")
        page = self.client.get(reverse("admin:core_etablissement_change", args=[etab.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="slug"')
        self.assertNotContains(page, 'name="admin_email"')

    def test_un_admin_d_hopital_ne_peut_pas_creer_d_hopital(self):
        etab = Etablissement.objects.create(nom="Hôpital A", slug="hopital-a", statut="ACTIF")
        adm = Utilisateur(username="adm", role=Utilisateur.Role.ADMIN, etablissement=etab)
        adm.set_password("x")
        adm.save()
        self.client.logout()
        self.client.login(username="adm", password="x")
        self.assertEqual(self.client.get(self.url).status_code, 403)
