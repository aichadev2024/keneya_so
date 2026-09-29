"""Création du personnel : e-mail obligatoire, invitation avec identifiant et lien de connexion."""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.invitations import generateur_invitation
from apps.core.models import Etablissement

Utilisateur = get_user_model()

MDP = "MotDePasseDeLaNouvelleRecrue2026!"


class InvitationPersonnelTests(TestCase):
    def setUp(self):
        self.etab = Etablissement.objects.create(nom="Hôpital du Point G", slug="point-g",
                                                 statut="ACTIF")
        self.admin = Utilisateur(username="adm", email="adm@pointg.ml", is_active=True,
                                 role=Utilisateur.Role.ADMIN, etablissement=self.etab)
        self.admin.set_password("x")
        self.admin.save()
        self.client.login(username="adm", password="x")
        self.url = reverse("admin:accounts_utilisateur_add")

    def _creer(self, **over):
        donnees = {"username": "dr_keita", "first_name": "Moussa", "last_name": "Keïta",
                   "email": "moussa@pointg.ml", "role": "MEDECIN", "langue_preferee": "fr"}
        donnees.update(over)
        return self.client.post(self.url, donnees)

    def _lien_invitation(self):
        return re.search(r"https?://[^/\s]+(/\S*invitation/\S+)", mail.outbox[0].body).group(1)

    def test_formulaire_sans_champ_mot_de_passe_et_email_obligatoire(self):
        page = self.client.get(self.url)
        self.assertNotContains(page, "password1")
        reponse = self._creer(email="")
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Utilisateur.tous.filter(username="dr_keita").exists())

    def test_creation_envoie_identifiant_et_lien(self):
        self._creer()
        nouveau = Utilisateur.tous.get(username="dr_keita")
        self.assertEqual(nouveau.etablissement_id, self.etab.pk)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["moussa@pointg.ml"])
        self.assertIn("Hôpital du Point G", message.subject)
        self.assertIn("dr_keita", message.body)
        self.assertIn("/comptes/invitation/", message.body)
        self.assertIn("/comptes/connexion/", message.body)

    def test_aucun_mot_de_passe_n_est_envoye_par_email(self):
        self._creer()
        nouveau = Utilisateur.tous.get(username="dr_keita")
        self.assertNotIn("password", mail.outbox[0].body.lower())
        self.assertTrue(nouveau.has_usable_password())  # aléatoire, inconnu de tous

    def test_le_compte_ne_peut_pas_se_connecter_avant_d_avoir_choisi_son_mot_de_passe(self):
        self._creer()
        self.client.logout()
        self.assertFalse(self.client.login(username="dr_keita", password=""))
        self.assertFalse(self.client.login(username="dr_keita", password="password"))

    def test_lien_choix_du_mot_de_passe_puis_connexion_directe(self):
        self._creer()
        self.client.logout()
        suite = self.client.get(self._lien_invitation(), follow=True)
        self.assertContains(suite, "Bienvenue")
        url_saisie = suite.redirect_chain[-1][0]
        reponse = self.client.post(url_saisie, {"new_password1": MDP, "new_password2": MDP})
        self.assertRedirects(reponse, reverse("core:dashboard"), fetch_redirect_response=False)
        # connecté sans autre étape
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)
        nouveau = Utilisateur.tous.get(username="dr_keita")
        self.assertTrue(nouveau.check_password(MDP))
        # et il pourra se reconnecter normalement ensuite
        self.client.logout()
        self.assertTrue(self.client.login(username="dr_keita", password=MDP))

    def test_le_lien_ne_sert_qu_une_fois(self):
        self._creer()
        self.client.logout()
        lien = self._lien_invitation()
        suite = self.client.get(lien, follow=True).redirect_chain[-1][0]
        self.client.post(suite, {"new_password1": MDP, "new_password2": MDP})
        self.client.logout()
        reponse = self.client.get(lien, follow=True)
        self.assertNotContains(reponse, 'name="new_password1"')

    def test_le_lien_d_invitation_reste_valable_plusieurs_jours(self):
        from datetime import timedelta
        from unittest import mock

        self._creer()
        nouveau = Utilisateur.tous.get(username="dr_keita")
        jeton = generateur_invitation.make_token(nouveau)
        avant_expiration = generateur_invitation._now() + timedelta(days=6)
        apres_expiration = generateur_invitation._now() + timedelta(days=8)
        with mock.patch.object(generateur_invitation, "_now", return_value=avant_expiration):
            self.assertTrue(generateur_invitation.check_token(nouveau, jeton))
        with mock.patch.object(generateur_invitation, "_now", return_value=apres_expiration):
            self.assertFalse(generateur_invitation.check_token(nouveau, jeton))

    def test_un_jeton_de_reinitialisation_ne_sert_pas_d_invitation(self):
        from django.contrib.auth.tokens import default_token_generator

        self._creer()
        nouveau = Utilisateur.tous.get(username="dr_keita")
        jeton = default_token_generator.make_token(nouveau)
        uid = urlsafe_base64_encode(force_bytes(nouveau.pk))
        self.client.logout()
        reponse = self.client.get(reverse("accounts:invitation", args=[uid, jeton]), follow=True)
        self.assertNotContains(reponse, 'name="new_password1"')

    def test_renvoyer_l_invitation(self):
        self._creer()
        nouveau = Utilisateur.tous.get(username="dr_keita")
        mail.outbox.clear()
        self.client.post(reverse("admin:accounts_utilisateur_changelist"), {
            "action": "renvoyer_invitation", "_selected_action": [nouveau.pk]})
        self.assertEqual(len(mail.outbox), 1)

    def test_email_dans_la_langue_preferee_de_la_personne(self):
        self._creer(langue_preferee="en")
        self.assertIn("Your username", mail.outbox[0].body)
        self.assertIn("/en/comptes/invitation/", mail.outbox[0].body)

    def test_echec_d_envoi_ne_bloque_pas_la_creation(self):
        from unittest import mock

        with mock.patch("apps.accounts.invitations.envoyer_invitation", side_effect=OSError("smtp")):
            reponse = self._creer()
        self.assertEqual(reponse.status_code, 302)
        self.assertTrue(Utilisateur.tous.filter(username="dr_keita").exists())

    def test_un_admin_d_hopital_ne_peut_pas_rattacher_le_compte_a_un_autre_hopital(self):
        autre = Etablissement.objects.create(nom="Autre", slug="autre", statut="ACTIF")
        self._creer(etablissement=autre.pk)
        self.assertEqual(Utilisateur.tous.get(username="dr_keita").etablissement_id, self.etab.pk)
