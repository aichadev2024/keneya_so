"""Tests transverses : multilinguisme (CDC 4.11), notifications, exports (CDC 9)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import get_language_info, override

from django.utils.translation import gettext_lazy as _lazy

from .exports import exporter, exporter_excel, exporter_excel_multi, exporter_pdf, exporter_pdf_multi
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


class ExportsTests(TestCase):
    """CDC 9 — « Export PDF/Excel possible sur tous les modules »."""

    def test_pdf_generique_produit_un_pdf_valide(self):
        reponse = exporter_pdf(titre="Titre", colonnes=["A", "B"],
                               lignes=[["1", "2"], ["3", "4"]], nom_fichier="t")
        self.assertEqual(reponse["Content-Type"], "application/pdf")
        self.assertTrue(reponse.content.startswith(b"%PDF"))

    def test_pdf_avec_texte_arabe_ne_leve_pas_d_erreur(self):
        reponse = exporter_pdf(titre="عنوان", colonnes=["عمود"],
                               lignes=[["قيمة"]], nom_fichier="t")
        self.assertTrue(reponse.content.startswith(b"%PDF"))

    def test_excel_generique_produit_un_classeur_valide(self):
        reponse = exporter_excel(titre="Titre", colonnes=["A", "B"],
                                 lignes=[["1", "2"]], nom_fichier="t")
        self.assertEqual(
            reponse["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertTrue(reponse.content.startswith(b"PK"))  # signature ZIP/XLSX

    def test_dispatcher_sans_parametre_format_renvoie_none(self):
        from django.test import RequestFactory
        request = RequestFactory().get("/quelconque/")
        self.assertIsNone(exporter(request, titre="T", colonnes=[], lignes=[]))

    def test_excel_accepte_les_chaines_de_traduction_paresseuses(self):
        # Régression : gettext_lazy("...") n'est pas un str pour openpyxl et
        # levait ValueError("Cannot convert ... to Excel") avant coercion.
        reponse = exporter_excel(titre="Titre", colonnes=[_lazy("Colonne")],
                                 lignes=[[_lazy("Valeur")], [42]], nom_fichier="t")
        self.assertTrue(reponse.content.startswith(b"PK"))

    def test_pdf_multi_sections_produit_un_pdf_valide(self):
        reponse = exporter_pdf_multi(
            titre="Rapport", sections=[("Section A", ["X"], [[_lazy("y")]]),
                                       ("Section B", ["Z"], [])],
            nom_fichier="t")
        self.assertTrue(reponse.content.startswith(b"%PDF"))

    def test_excel_multi_sections_avec_traductions_paresseuses(self):
        reponse = exporter_excel_multi(
            sections=[("Section A", [_lazy("Col")], [[_lazy("Val"), 1]]),
                     ("Section A", ["Col2"], [["dup-title"]])],  # titres dupliqués
            nom_fichier="t")
        self.assertTrue(reponse.content.startswith(b"PK"))

    def test_liste_patients_exporte_le_meme_jeu_filtre_que_l_affichage(self):
        from apps.patients.models import Patient
        Patient.objects.create(nom="Exportable", prenom="Un", sexe="M")
        Patient.objects.create(nom="AutreCasFiltre", prenom="Deux", sexe="F")
        u = Utilisateur.objects.create_user("expu", password="x",
                                            role=Utilisateur.Role.AGENT_ACCUEIL)
        self.client.login(username="expu", password="x")

        html = self.client.get("/fr/patients/?q=Exportable")
        self.assertEqual(html.status_code, 200)
        self.assertContains(html, "Exportable")
        self.assertNotContains(html, "AutreCasFiltre")

        pdf = self.client.get("/fr/patients/?q=Exportable&format=pdf")
        self.assertEqual(pdf["Content-Type"], "application/pdf")

        xlsx = self.client.get("/fr/patients/?q=Exportable&format=xlsx")
        self.assertEqual(
            xlsx["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


class StatistiquesTests(TestCase):
    def test_reserve_a_l_administration_et_au_comptable(self):
        Utilisateur.objects.create_user("med_stat", password="x",
                                        role=Utilisateur.Role.MEDECIN)
        self.client.login(username="med_stat", password="x")
        self.assertEqual(self.client.get(reverse("core:statistiques")).status_code, 403)

    def test_accessible_au_comptable(self):
        Utilisateur.objects.create_user("cpt_stat", password="x",
                                        role=Utilisateur.Role.COMPTABLE)
        self.client.login(username="cpt_stat", password="x")
        self.assertEqual(self.client.get(reverse("core:statistiques")).status_code, 200)

    def test_export_pdf_des_statistiques(self):
        Utilisateur.objects.create_user("adm_stat", password="x",
                                        role=Utilisateur.Role.ADMIN)
        self.client.login(username="adm_stat", password="x")
        reponse = self.client.get(reverse("core:statistiques") + "?format=pdf")
        self.assertEqual(reponse["Content-Type"], "application/pdf")
        self.assertTrue(reponse.content.startswith(b"%PDF"))


class NavigationTests(TestCase):
    """Barre latérale (refonte visuelle) : un seul élément actif à la fois."""

    def test_statistiques_actif_seulement_sur_sa_propre_page(self):
        # Régression : le tableau de bord et /statistiques/ partagent le même
        # namespace "core" ; comparer seulement le namespace allumait "Statistiques"
        # même sur le tableau de bord.
        Utilisateur.objects.create_user("cpt_nav", password="x",
                                        role=Utilisateur.Role.COMPTABLE)
        self.client.login(username="cpt_nav", password="x")

        tableau = self.client.get(reverse("core:dashboard"))
        item_tb = next(i for i in tableau.context["navigation_principale"]
                       if i["url_name"] == "core:statistiques")
        self.assertFalse(item_tb["actif"])

        stats = self.client.get(reverse("core:statistiques"))
        item_stats = next(i for i in stats.context["navigation_principale"]
                          if i["url_name"] == "core:statistiques")
        self.assertTrue(item_stats["actif"])

    def test_module_actif_sur_ses_sous_pages(self):
        from apps.patients.models import Patient
        u = Utilisateur.objects.create_user("acc_nav", password="x",
                                            role=Utilisateur.Role.AGENT_ACCUEIL)
        self.client.login(username="acc_nav", password="x")
        p = Patient.objects.create(nom="Nav", prenom="Test", sexe="M")

        reponse = self.client.get(reverse("patients:detail", args=[p.pk]))
        item = next(i for i in reponse.context["navigation_principale"]
                   if i["url_name"] == "patients:liste")
        self.assertTrue(item["actif"])


class AccueilTests(TestCase):
    """Page racine : vitrine publique si anonyme, tableau de bord si connecté."""

    def test_visiteur_anonyme_voit_la_vitrine(self):
        reponse = self.client.get(reverse("core:accueil"))
        self.assertEqual(reponse.status_code, 200)
        self.assertTemplateUsed(reponse, "core/vitrine.html")

    def test_utilisateur_connecte_est_redirige_vers_le_tableau_de_bord(self):
        Utilisateur.objects.create_user("visiteur", password="x")
        self.client.login(username="visiteur", password="x")
        reponse = self.client.get(reverse("core:accueil"))
        self.assertRedirects(reponse, reverse("core:dashboard"))
