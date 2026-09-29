"""Inscription en libre-service d'un hôpital et cycle de vie de l'abonnement (SaaS)."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Etablissement
from apps.core.tenancy import pour_etablissement
from apps.patients.models import Patient

Utilisateur = get_user_model()

MDP = "UnMotDePasseSolide2026!"


def donnees(**over):
    d = {"nom_hopital": "Hôpital du Point G", "prenom": "Awa", "nom": "Traoré",
         "email": "awa@pointg.ml", "username": "awa_admin", "password1": MDP,
         "password2": MDP, "site_web": ""}
    d.update(over)
    return d


@override_settings(INSCRIPTION_LIBRE=True)
class InscriptionHopitalTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("accounts:inscription_hopital")

    def test_page_accessible_sans_connexion(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_inscription_cree_l_hopital_en_essai_et_son_administrateur(self):
        reponse = self.client.post(self.url, donnees())
        self.assertRedirects(reponse, reverse("core:dashboard"), fetch_redirect_response=False)
        etab = Etablissement.objects.get(nom="Hôpital du Point G")
        self.assertEqual(etab.statut, Etablissement.Statut.ESSAI)
        self.assertEqual(etab.essai_jusqu_au, date.today() + timedelta(days=30))
        admin = Utilisateur.tous.get(username="awa_admin")
        self.assertEqual(admin.etablissement_id, etab.pk)
        self.assertEqual(admin.role, Utilisateur.Role.ADMIN)
        self.assertFalse(admin.is_superuser)
        self.assertTrue(admin.is_staff)  # accès à l'administration de SON hôpital
        # Connecté d'emblée, sur son tableau de bord.
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)

    def test_le_nouvel_hopital_ne_voit_aucune_donnee_existante(self):
        autre = Etablissement.objects.create(nom="Existant", slug="existant", statut="ACTIF")
        with pour_etablissement(autre):
            Patient.objects.create(nom="DejaLa", prenom="X", sexe="M")
        self.client.post(self.url, donnees())
        reponse = self.client.get(reverse("patients:liste"))
        self.assertNotContains(reponse, "DEJALA")

    def test_le_nouvel_hopital_recoit_un_catalogue_de_depart_isole(self):
        from apps.facturation.models import Tarif
        from apps.laboratoire.models import TypeExamen
        self.client.post(self.url, donnees())
        self.client.logout()
        self.client.post(self.url, donnees(nom_hopital="Second", username="second"))
        with pour_etablissement(Etablissement.objects.get(nom="Hôpital du Point G")):
            self.assertEqual(TypeExamen.objects.count(), 6)
            self.assertEqual(Tarif.objects.count(), 4)
        with pour_etablissement(Etablissement.objects.get(nom="Second")):
            self.assertEqual(TypeExamen.objects.count(), 6)

    def test_identifiant_deja_pris_refuse(self):
        Utilisateur.objects.create_user("awa_admin", password="x")
        reponse = self.client.post(self.url, donnees())
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Etablissement.objects.filter(nom="Hôpital du Point G").exists())

    def test_mot_de_passe_faible_refuse(self):
        reponse = self.client.post(self.url, donnees(password1="12345678", password2="12345678"))
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Etablissement.objects.filter(nom="Hôpital du Point G").exists())

    def test_mots_de_passe_differents_refuses(self):
        reponse = self.client.post(self.url, donnees(password2="UneAutreValeur2026!"))
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Utilisateur.tous.filter(username="awa_admin").exists())

    def test_robot_pris_au_piege(self):
        reponse = self.client.post(self.url, donnees(site_web="http://spam.example"))
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(Etablissement.objects.filter(nom="Hôpital du Point G").exists())

    def test_limite_d_inscriptions_par_adresse(self):
        for i in range(5):
            self.client.logout()
            self.client.post(self.url, donnees(nom_hopital=f"Hôpital {i}", username=f"u{i}"))
        self.client.logout()
        self.client.post(self.url, donnees(nom_hopital="Hôpital de trop", username="trop"))
        self.assertFalse(Etablissement.objects.filter(nom="Hôpital de trop").exists())

    def test_deux_hopitaux_de_meme_nom_ont_des_identifiants_courts_distincts(self):
        self.client.post(self.url, donnees())
        self.client.logout()
        self.client.post(self.url, donnees(username="autre_admin"))
        slugs = list(Etablissement.objects.filter(nom="Hôpital du Point G")
                     .values_list("slug", flat=True))
        self.assertEqual(len(set(slugs)), 2)

    def test_utilisateur_connecte_redirige(self):
        Utilisateur.objects.create_user("deja", password="x")
        self.client.login(username="deja", password="x")
        self.assertEqual(self.client.get(self.url).status_code, 302)


class CycleDeVieAbonnementTests(TestCase):
    def _hopital(self, statut, essai=None, username="u"):
        etab = Etablissement.objects.create(nom=f"H-{username}", slug=username, statut=statut,
                                            essai_jusqu_au=essai)
        Utilisateur.objects.create_user(username, password="x", etablissement=etab,
                                        role=Utilisateur.Role.MEDECIN)
        self.client.login(username=username, password="x")
        return etab

    def test_essai_en_cours_donne_acces_et_affiche_un_bandeau(self):
        self._hopital("ESSAI", date.today() + timedelta(days=10), "essai_ok")
        reponse = self.client.get(reverse("core:dashboard"))
        self.assertEqual(reponse.status_code, 200)
        self.assertContains(reponse, "essai")

    def test_essai_termine_bloque_l_acces(self):
        self._hopital("ESSAI", date.today() - timedelta(days=1), "essai_fini")
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("patients:liste")).status_code, 403)

    def test_compte_suspendu_bloque_l_acces(self):
        self._hopital("SUSPENDU", None, "suspendu")
        reponse = self.client.get(reverse("core:dashboard"))
        self.assertEqual(reponse.status_code, 403)
        self.assertContains(reponse, "conserv", status_code=403)

    def test_un_utilisateur_bloque_peut_se_deconnecter(self):
        self._hopital("SUSPENDU", None, "suspendu2")
        reponse = self.client.post(reverse("accounts:logout"))
        self.assertEqual(reponse.status_code, 302)

    def test_api_renvoie_un_403_json_pour_un_compte_inactif(self):
        self._hopital("SUSPENDU", None, "suspendu3")
        reponse = self.client.get("/api/v1/patients/")
        self.assertEqual(reponse.status_code, 403)
        self.assertIn("Abonnement inactif", reponse.json()["detail"])

    def test_hopital_actif_sans_bandeau_d_essai(self):
        self._hopital("ACTIF", None, "actif")
        reponse = self.client.get(reverse("core:dashboard"))
        self.assertEqual(reponse.status_code, 200)
        self.assertNotContains(reponse, "Période d'essai")

    def test_le_blocage_d_un_hopital_n_affecte_pas_les_autres(self):
        actif = Etablissement.objects.create(nom="Actif", slug="actif2", statut="ACTIF")
        Utilisateur.objects.create_user("ok", password="x", etablissement=actif,
                                        role=Utilisateur.Role.MEDECIN)
        self._hopital("SUSPENDU", None, "bloque")
        self.client.logout()
        self.client.login(username="ok", password="x")
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)

    def test_le_super_admin_plateforme_n_est_jamais_bloque(self):
        Etablissement.objects.create(nom="S", slug="s", statut="SUSPENDU")
        Utilisateur.objects.create_superuser("plateforme", password="x")
        self.client.login(username="plateforme", password="x")
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)


class PlansEtLimitesTests(TestCase):
    def setUp(self):
        from apps.core.models import Plan
        self.petit = Plan.objects.create(code="mini", nom="Mini", max_utilisateurs=2)
        self.etab = Etablissement.objects.create(nom="Petit", slug="petit", statut="ACTIF",
                                                 plan=self.petit)
        self.admin = Utilisateur.objects.create_user(
            "adm", password="x", etablissement=self.etab, role=Utilisateur.Role.ADMIN)
        Utilisateur.objects.create_user("u2", password="x", etablissement=self.etab,
                                        role=Utilisateur.Role.MEDECIN)

    def test_places_restantes_calculees_sur_les_comptes_actifs(self):
        self.assertEqual(self.etab.places_utilisateurs_restantes(), 0)
        Utilisateur.tous.filter(username="u2").update(is_active=False)
        self.assertEqual(self.etab.places_utilisateurs_restantes(), 1)

    def test_sans_plan_aucune_limite(self):
        libre = Etablissement.objects.create(nom="Libre", slug="libre", statut="ACTIF")
        self.assertIsNone(libre.places_utilisateurs_restantes())

    def test_limite_atteinte_refuse_un_nouveau_compte_dans_l_administration(self):
        self.client.login(username="adm", password="x")
        url = reverse("admin:accounts_utilisateur_add")
        reponse = self.client.post(url, {
            "username": "u3", "email": "u3@hopital.ml", "role": "MEDECIN",
            "langue_preferee": "fr"})
        self.assertEqual(reponse.status_code, 200)  # formulaire réaffiché avec l'erreur
        self.assertContains(reponse, "limite d")
        self.assertFalse(Utilisateur.tous.filter(username="u3").exists())

    def test_sous_la_limite_le_compte_est_cree_dans_l_hopital_de_l_admin(self):
        Utilisateur.tous.filter(username="u2").update(is_active=False)
        self.client.login(username="adm", password="x")
        self.client.post(reverse("admin:accounts_utilisateur_add"), {
            "username": "u3", "email": "u3@hopital.ml", "role": "MEDECIN",
            "langue_preferee": "fr"})
        nouveau = Utilisateur.tous.get(username="u3")
        self.assertEqual(nouveau.etablissement_id, self.etab.pk)

    @override_settings(INSCRIPTION_LIBRE=True)
    def test_l_inscription_attribue_le_plan_d_essai(self):
        cache.clear()
        self.client.post(reverse("accounts:inscription_hopital"), donnees())
        etab = Etablissement.objects.get(nom="Hôpital du Point G")
        self.assertEqual(etab.plan.code, "essai")

    def test_un_admin_d_hopital_ne_gere_ni_plans_ni_etablissements(self):
        self.client.login(username="adm", password="x")
        for nom in ("admin:core_plan_changelist", "admin:core_etablissement_changelist"):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 403, nom)


class ConsoleProprietaireTests(TestCase):
    def setUp(self):
        Utilisateur.objects.create_superuser("plateforme", password="x")
        self.client.login(username="plateforme", password="x")
        self.etab = Etablissement.objects.create(
            nom="Client", slug="client", statut="ESSAI",
            essai_jusqu_au=date.today() - timedelta(days=3))

    def _action(self, nom):
        return self.client.post(reverse("admin:core_etablissement_changelist"), {
            "action": nom, "_selected_action": [self.etab.pk]}, follow=True)

    def test_activer_debloque_un_hopital_dont_l_essai_est_termine(self):
        self.assertFalse(self.etab.acces_autorise)
        self._action("activer")
        self.etab.refresh_from_db()
        self.assertEqual(self.etab.statut, "ACTIF")
        self.assertTrue(self.etab.acces_autorise)

    def test_suspendre_bloque_l_acces(self):
        self._action("suspendre")
        self.etab.refresh_from_db()
        self.assertFalse(self.etab.acces_autorise)

    def test_prolonger_l_essai_de_30_jours_a_partir_d_aujourd_hui(self):
        self._action("prolonger_essai")
        self.etab.refresh_from_db()
        self.assertEqual(self.etab.essai_jusqu_au, date.today() + timedelta(days=30))
        self.assertTrue(self.etab.acces_autorise)


class NomDeLHopitalDansLeMenuTests(TestCase):
    def test_le_menu_affiche_le_nom_de_l_hopital_connecte(self):
        etab = Etablissement.objects.create(nom="Clinique Bon Secours", slug="bon-secours",
                                            statut="ACTIF")
        u = Utilisateur(username="adm", role=Utilisateur.Role.ADMIN, etablissement=etab)
        u.set_password("x")
        u.save()
        self.client.login(username="adm", password="x")
        page = self.client.get(reverse("core:dashboard")).content.decode()
        marque = page[page.index('class="sidebar-brand"'):page.index('class="sidebar-nav"')]
        self.assertIn("Clinique Bon Secours", marque)
        self.assertNotIn("Gestion hospitalière", marque)

    def test_le_proprietaire_sans_hopital_n_a_pas_de_menu_lateral(self):
        # Il n'a aucun module clinique : sa console n'a pas de barre latérale.
        Utilisateur.tous.create_superuser("proprio", "p@k.ml", "x")
        self.client.login(username="proprio", password="x")
        page = self.client.get(reverse("core:dashboard")).content.decode()
        self.assertNotIn('class="sidebar-brand"', page)
        self.assertNotIn('class="app-sidebar"', page)
        self.assertIn("Kènèya", page)
        self.assertIn("Console propriétaire", page)


class ConsoleProprietaireEcranTests(TestCase):
    """L'écran d'accueil du propriétaire : chiffres de la plateforme et accès au socle commun."""

    def setUp(self):
        Utilisateur.tous.create_superuser("proprio", "p@k.ml", "x")
        self.client.login(username="proprio", password="x")
        Etablissement.objects.create(nom="Actif A", slug="actif-a", statut="ACTIF")
        Etablissement.objects.create(nom="Essai A", slug="essai-a", statut="ESSAI",
                                     essai_jusqu_au=date.today() + timedelta(days=20))
        Etablissement.objects.create(nom="Essai bientôt fini", slug="essai-b", statut="ESSAI",
                                     essai_jusqu_au=date.today() + timedelta(days=3))
        Etablissement.objects.create(nom="Suspendu A", slug="suspendu-a", statut="SUSPENDU")

    def test_un_utilisateur_d_hopital_garde_le_tableau_de_bord_habituel(self):
        etab = Etablissement.objects.create(nom="Hôpital ordinaire", slug="hopital-ordinaire",
                                            statut="ACTIF")
        u = Utilisateur(username="adm", role=Utilisateur.Role.ADMIN, etablissement=etab)
        u.set_password("x")
        u.save()
        self.client.logout()
        self.client.login(username="adm", password="x")
        reponse = self.client.get(reverse("core:dashboard"))
        self.assertTemplateUsed(reponse, "core/dashboard.html")
        self.assertTemplateNotUsed(reponse, "core/console_proprietaire.html")

    def test_le_proprietaire_voit_sa_propre_console(self):
        reponse = self.client.get(reverse("core:dashboard"))
        self.assertTemplateUsed(reponse, "core/console_proprietaire.html")

    def test_les_chiffres_de_la_plateforme_sont_justes(self):
        stats = self.client.get(reverse("core:dashboard")).context["stats"]
        self.assertEqual(stats["total"], 4)
        self.assertEqual(stats["actifs"], 1)
        self.assertEqual(stats["essai"], 2)
        self.assertEqual(stats["suspendus"], 1)
        self.assertEqual(stats["essais_expirant"], 1)  # seul « Essai bientôt fini » est sous 7 jours

    def test_l_alerte_d_essais_qui_expirent_ne_s_affiche_que_s_il_y_en_a(self):
        reponse = self.client.get(reverse("core:dashboard"))
        self.assertContains(reponse, "se termine dans les 7 prochains jours")
        Etablissement.objects.filter(slug="essai-b").update(essai_jusqu_au=date.today() + timedelta(days=20))
        reponse = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(reponse, "prochains jours")

    def test_les_raccourcis_pointent_vers_les_ecrans_dedies_du_socle_commun(self):
        reponse = self.client.get(reverse("core:dashboard"))
        self.assertContains(reponse, reverse("core:proprietaire_etablissements"))
        self.assertContains(reponse, reverse("core:proprietaire_etablissement_creer"))
        self.assertContains(reponse, reverse("core:proprietaire_plans"))
        self.assertContains(reponse, reverse("core:proprietaire_utilisateurs"))
        self.assertContains(reponse, reverse("core:proprietaire_journal"))
        # L'admin Django reste accessible en secours, sans être mis en avant.
        self.assertContains(reponse, reverse("admin:index"))


class AdminSocleCommunProprietaireTests(TestCase):
    """Dans /admin/, le propriétaire ne voit que le socle commun de la plateforme."""

    def setUp(self):
        Utilisateur.tous.create_superuser("proprio", "p@k.ml", "x")
        self.client.login(username="proprio", password="x")

    def test_seuls_les_modeles_du_socle_commun_apparaissent(self):
        page = self.client.get(reverse("admin:index"))
        self.assertContains(page, "Établissements")
        self.assertContains(page, "Plans d")
        self.assertContains(page, "Utilisateurs")
        self.assertContains(page, "Journal d&#x27;audit")
        self.assertNotContains(page, "Patients")
        self.assertNotContains(page, "Médicaments")
        self.assertNotContains(page, "Consultations")
        self.assertNotContains(page, "Notifications")
        self.assertNotContains(page, "Paramètres système")
        self.assertNotContains(page, "Groupes")

    def test_un_administrateur_d_hopital_garde_la_liste_complete(self):
        etab = Etablissement.objects.create(nom="Hôpital X", slug="hopital-x", statut="ACTIF")
        adm = Utilisateur(username="adm", role=Utilisateur.Role.ADMIN, etablissement=etab)
        adm.set_password("x")
        adm.save()
        self.client.logout()
        self.client.login(username="adm", password="x")
        page = self.client.get(reverse("admin:index"))
        self.assertContains(page, "Patients")
        self.assertContains(page, "Médicaments")

    def test_l_acces_direct_par_url_reste_possible_pour_depanner(self):
        # La navigation est simplifiée, pas verrouillée : utile en cas de dépannage.
        reponse = self.client.get(reverse("admin:patients_patient_changelist"))
        self.assertEqual(reponse.status_code, 200)

