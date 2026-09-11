"""Tests transverses : multilinguisme (CDC 4.11) et notifications."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import get_language_info, override

from .models import Notification

Utilisateur = get_user_model()


class TraductionsTests(TestCase):
    """
    Vérifie que les catalogues compilés (.mo) sont chargés et appliqués.

    Ces .mo sont générés par scripts/i18n_extract.py + scripts/i18n_apply.py +
    scripts/i18n_compile.py (substitut pur Python à makemessages/compilemessages,
    voir README « Internationalisation »).
    """

    def test_bascule_anglais(self):
        with override("en"):
            from django.utils.translation import gettext as _
            self.assertEqual(_("Mot de passe"), "Password")

    def test_bascule_arabe_et_rtl(self):
        with override("ar"):
            from django.utils.translation import gettext as _
            self.assertEqual(_("Tableau de bord"), "لوحة التحكم")
            self.assertTrue(get_language_info("ar")["bidi"])

    def test_pluriel_arabe_zero(self):
        with override("ar"):
            from django.utils.translation import ngettext
            self.assertEqual(
                ngettext("%(n)s impayé", "%(n)s impayés", 0) % {"n": 0},
                "لا فاتورة غير مسددة",
            )

    def test_langues_locales_maliennes_retombent_sur_le_francais(self):
        # bm/ff/snk : catalogues encore vides (traduction humaine à venir,
        # CDC 4.11 / 12.5) — gettext doit alors afficher la chaîne source.
        with override("bm"):
            from django.utils.translation import gettext as _
            self.assertEqual(_("Tableau de bord"), "Tableau de bord")

    def test_page_de_connexion_en_anglais(self):
        response = self.client.get("/en/comptes/connexion/")
        self.assertContains(response, "Username")
        self.assertContains(response, "Password")

    def test_page_de_connexion_en_arabe_est_rtl(self):
        response = self.client.get("/ar/comptes/connexion/")
        self.assertContains(response, 'dir="rtl"')
        self.assertContains(response, "اسم المستخدم")


class NotificationsTests(TestCase):
    def test_badge_non_lues_sur_le_tableau_de_bord(self):
        u = Utilisateur.objects.create_user("u", password="x",
                                            role=Utilisateur.Role.MEDECIN)
        Notification.notifier(destinataire=u, titre="Test", message="…")
        self.client.login(username="u", password="x")
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, "1")

    def test_marquer_comme_lu(self):
        u = Utilisateur.objects.create_user("u2", password="x",
                                            role=Utilisateur.Role.MEDECIN)
        n = Notification.notifier(destinataire=u, titre="Test")
        self.client.login(username="u2", password="x")
        self.client.post(reverse("core:notification_lire", args=[n.pk]))
        n.refresh_from_db()
        self.assertTrue(n.lu)

    def test_une_notification_n_est_visible_que_par_son_destinataire(self):
        u1 = Utilisateur.objects.create_user("u3", password="x",
                                             role=Utilisateur.Role.MEDECIN)
        u2 = Utilisateur.objects.create_user("u4", password="x",
                                             role=Utilisateur.Role.MEDECIN)
        Notification.notifier(destinataire=u1, titre="Pour u3 seulement")
        self.client.login(username="u4", password="x")
        response = self.client.get(reverse("core:notifications"))
        self.assertNotContains(response, "Pour u3 seulement")
