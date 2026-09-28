"""Réinitialisation du mot de passe par e-mail."""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.core.models import Etablissement, HistoriqueAction

Utilisateur = get_user_model()

ANCIEN = "AncienMotDePasse2026!"
NOUVEAU = "NouveauMotDePasse2026!"


class ReinitialisationMotDePasseTests(TestCase):
    def setUp(self):
        cache.clear()
        self.etab = Etablissement.objects.create(nom="Hôpital A", slug="hopital-a")
        self.user = Utilisateur(username="awa", email="awa@hopital-a.ml",
                                role=Utilisateur.Role.ADMIN, etablissement=self.etab)
        self.user.set_password(ANCIEN)
        self.user.save()
        self.url = reverse("accounts:password_reset")

    def _demander(self, email="awa@hopital-a.ml"):
        return self.client.post(self.url, {"email": email})

    def _lien(self):
        corps = mail.outbox[0].body
        return re.search(r"https?://[^/]+(/\S+)", corps).group(1)

    def test_lien_present_sur_la_page_de_connexion(self):
        reponse = self.client.get(reverse("accounts:login"))
        self.assertContains(reponse, self.url)

    def test_demande_envoie_un_email_avec_un_lien(self):
        reponse = self._demander()
        self.assertRedirects(reponse, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["awa@hopital-a.ml"])
        self.assertIn("/comptes/reinitialisation/", mail.outbox[0].body)
        self.assertIn("awa", mail.outbox[0].body)  # rappel de l'identifiant

    def test_adresse_inconnue_meme_reponse_et_aucun_email(self):
        reponse = self._demander("personne@nulle-part.ml")
        self.assertRedirects(reponse, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_compte_desactive_ne_recoit_rien(self):
        self.user.is_active = False
        self.user.save()
        self._demander()
        self.assertEqual(len(mail.outbox), 0)

    def test_parcours_complet_puis_connexion_avec_le_nouveau_mot_de_passe(self):
        self._demander()
        lien = self.client.get(self._lien(), follow=True)  # jeton -> session
        self.assertContains(lien, 'name="new_password1"')
        url_saisie = lien.redirect_chain[-1][0]
        reponse = self.client.post(url_saisie, {"new_password1": NOUVEAU, "new_password2": NOUVEAU})
        self.assertRedirects(reponse, reverse("accounts:password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NOUVEAU))
        self.assertFalse(self.user.check_password(ANCIEN))
        self.assertTrue(self.client.login(username="awa", password=NOUVEAU))

    def test_le_lien_ne_sert_qu_une_fois(self):
        self._demander()
        lien = self._lien()
        suite = self.client.get(lien, follow=True).redirect_chain[-1][0]
        self.client.post(suite, {"new_password1": NOUVEAU, "new_password2": NOUVEAU})
        reponse = self.client.get(lien, follow=True)
        self.assertContains(reponse, reverse("accounts:password_reset"))
        self.assertNotContains(reponse, 'name="new_password1"')

    def test_lien_falsifie_refuse(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        url = reverse("accounts:password_reset_confirm", args=[uid, "abc-" + "x" * 20])
        reponse = self.client.get(url, follow=True)
        self.assertNotContains(reponse, 'name="new_password1"')

    def test_mot_de_passe_faible_refuse(self):
        self._demander()
        suite = self.client.get(self._lien(), follow=True).redirect_chain[-1][0]
        reponse = self.client.post(suite, {"new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(reponse.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(ANCIEN))

    def test_lien_expire_apres_une_heure(self):
        from django.conf import settings
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 3600)

    def test_reinitialisation_est_consignee_au_journal_d_audit(self):
        self._demander()
        suite = self.client.get(self._lien(), follow=True).redirect_chain[-1][0]
        self.client.post(suite, {"new_password1": NOUVEAU, "new_password2": NOUVEAU})
        entree = HistoriqueAction.objects.filter(objet_id=str(self.user.pk)).first()
        self.assertIsNotNone(entree)
        self.assertIn("réinitialisé", entree.description)

    def test_limite_par_adresse_email(self):
        for _ in range(5):
            self._demander()
        self.assertEqual(len(mail.outbox), 3)  # au-delà, silence (pas de bombardement)

    def test_limite_par_ip(self):
        for i in range(8):
            self._demander(f"inconnu{i}@x.ml")
        # les adresses inconnues ne consomment pas d'e-mail, mais la limite par IP
        # doit bloquer avant l'envoi pour un compte réel une fois atteinte
        self._demander()
        self.assertEqual(len(mail.outbox), 0)

    def test_deux_hopitaux_meme_email_chacun_recoit_son_lien(self):
        autre = Etablissement.objects.create(nom="Hôpital B", slug="hopital-b")
        u2 = Utilisateur(username="awa_b", email="awa@hopital-a.ml",
                         role=Utilisateur.Role.MEDECIN, etablissement=autre)
        u2.set_password(ANCIEN)
        u2.save()
        self._demander()
        self.assertEqual(len(mail.outbox), 2)

    def test_reinitialisation_deverrouille_le_compte(self):
        from axes.models import AccessAttempt
        AccessAttempt.objects.create(username="awa", ip_address="1.2.3.4", failures_since_start=9,
                                     user_agent="t", get_data="", post_data="")
        self._demander()
        suite = self.client.get(self._lien(), follow=True).redirect_chain[-1][0]
        self.client.post(suite, {"new_password1": NOUVEAU, "new_password2": NOUVEAU})
        self.assertFalse(AccessAttempt.objects.filter(username="awa").exists())
