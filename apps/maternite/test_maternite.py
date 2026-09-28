"""Module Maternité : rôle sage-femme, dossier de grossesse, consultations prénatales."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation

from apps.consultations.models import Constantes, Consultation, LigneOrdonnance, Ordonnance
from apps.core.models import Etablissement
from apps.core.tenancy import pour_etablissement
from apps.patients.models import Patient
from apps.pharmacie.models import Medicament

from .models import ConsultationPrenatale, DossierGrossesse
from .services import alertes_dossier, alertes_visite

Utilisateur = get_user_model()
Role = Utilisateur.Role


def aujourdhui():
    return date.today()


def creer_utilisateur(etab, username, role):
    u = Utilisateur(username=username, role=role, etablissement=etab)
    u.set_password("x")
    u.save()
    return u


class BaseMaternite(TestCase):
    def setUp(self):
        # Les messages sont vérifiés en français, quelle que soit la langue restée active ailleurs.
        self.enterContext(translation.override("fr"))
        self.etab = Etablissement.objects.create(nom="Maternité A", slug="mat-a", statut="ACTIF")
        self.sf = creer_utilisateur(self.etab, "sf", Role.SAGE_FEMME)
        with pour_etablissement(self.etab):
            self.patiente = Patient.objects.create(nom="Traoré", prenom="Awa", sexe="F")

    def connecter(self, username="sf"):
        self.client.login(username=username, password="x")

    def ouvrir_dossier(self, semaines=20, **over):
        with pour_etablissement(self.etab):
            donnees = dict(patient=self.patiente,
                           date_dernieres_regles=aujourdhui() - timedelta(weeks=semaines),
                           gestite=2, parite=1, sage_femme=self.sf)
            donnees.update(over)
            return DossierGrossesse.objects.create(**donnees)

    def donnees_visite(self, **over):
        d = {"poids_kg": "62.5", "tension_systolique": "110", "tension_diastolique": "70",
             "temperature_c": "36.8", "hauteur_uterine_cm": "22", "bruits_coeur_foetal": "PRESENTS",
             "frequence_bcf": "140", "presentation": "NON_DETERMINEE", "albuminurie": "NEGATIF",
             "glycosurie": "NEGATIF", "hemoglobine_g_dl": "11.5", "depistage_vih": "NON_FAIT",
             "depistage_syphilis": "NON_FAIT", "tpi_sp_donne": "on", "fer_acide_folique_donne": "on",
             "observations": "RAS"}
        d.update(over)
        return d


class RoleEtAccesTests(BaseMaternite):
    def test_la_sage_femme_accede_a_son_espace(self):
        self.connecter()
        self.assertEqual(self.client.get(reverse("maternite:accueil")).status_code, 200)

    def test_un_agent_d_accueil_n_a_pas_acces(self):
        creer_utilisateur(self.etab, "accueil", Role.AGENT_ACCUEIL)
        self.connecter("accueil")
        self.assertEqual(self.client.get(reverse("maternite:accueil")).status_code, 403)

    def test_un_medecin_peut_suivre_une_grossesse(self):
        creer_utilisateur(self.etab, "dr", Role.MEDECIN)
        self.connecter("dr")
        self.assertEqual(self.client.get(reverse("maternite:accueil")).status_code, 200)

    def test_l_infirmier_ne_fait_que_consulter(self):
        creer_utilisateur(self.etab, "inf", Role.INFIRMIER)
        dossier = self.ouvrir_dossier()
        self.connecter("inf")
        self.assertEqual(self.client.get(reverse("maternite:dossier", args=[dossier.pk])).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("maternite:visite_nouvelle", args=[dossier.pk])).status_code, 403)

    def test_a_la_connexion_la_sage_femme_arrive_dans_la_maternite(self):
        reponse = self.client.post(reverse("accounts:login"), {"username": "sf", "password": "x"})
        self.assertRedirects(reponse, reverse("maternite:accueil"), fetch_redirect_response=False)

    def test_les_autres_roles_arrivent_au_tableau_de_bord(self):
        creer_utilisateur(self.etab, "dr", Role.MEDECIN)
        reponse = self.client.post(reverse("accounts:login"), {"username": "dr", "password": "x"})
        self.assertRedirects(reponse, reverse("core:dashboard"), fetch_redirect_response=False)

    def test_le_menu_propose_la_maternite(self):
        self.connecter()
        self.assertContains(self.client.get(reverse("core:dashboard")), reverse("maternite:accueil"))


class TermeTests(SimpleTestCase):
    def test_date_prevue_d_accouchement_et_terme(self):
        ddr = aujourdhui() - timedelta(weeks=20, days=3)
        dossier = DossierGrossesse(date_dernieres_regles=ddr)
        self.assertEqual(dossier.date_prevue_accouchement, ddr + timedelta(days=280))
        self.assertEqual(dossier.terme(), (20, 3))
        self.assertEqual(dossier.terme_texte, "20 SA + 3 j")

    def test_terme_a_une_date_donnee(self):
        dossier = DossierGrossesse(date_dernieres_regles=date(2026, 1, 1))
        self.assertEqual(dossier.terme(date(2026, 2, 12)), (6, 0))

    def test_terme_jamais_negatif(self):
        dossier = DossierGrossesse(date_dernieres_regles=aujourdhui() + timedelta(days=5))
        self.assertEqual(dossier.terme(), (0, 0))


class DossierGrossesseTests(BaseMaternite):
    def setUp(self):
        super().setUp()
        self.connecter()
        self.url = reverse("maternite:dossier_nouveau", args=[self.patiente.pk])

    def _post(self, **over):
        donnees = {"date_dernieres_regles": (aujourdhui() - timedelta(weeks=12)).isoformat(),
                   "gestite": 2, "parite": 1, "antecedents": "", "facteurs_risque": ""}
        donnees.update(over)
        return self.client.post(self.url, donnees)

    def test_ouverture_d_un_dossier(self):
        reponse = self._post()
        dossier = DossierGrossesse.objects.get(patient=self.patiente)
        self.assertRedirects(reponse, reverse("maternite:dossier", args=[dossier.pk]))
        self.assertTrue(dossier.reference.startswith("GRO-"))
        self.assertEqual(dossier.sage_femme, self.sf)
        self.assertEqual(dossier.etablissement_id, self.etab.pk)

    def test_seulement_pour_une_patiente(self):
        with pour_etablissement(self.etab):
            homme = Patient.objects.create(nom="Diallo", prenom="Ali", sexe="M")
        reponse = self.client.get(reverse("maternite:dossier_nouveau", args=[homme.pk]))
        self.assertRedirects(reponse, reverse("patients:detail", args=[homme.pk]),
                             fetch_redirect_response=False)
        self.client.post(reverse("maternite:dossier_nouveau", args=[homme.pk]), {})
        self.assertFalse(DossierGrossesse.objects.filter(patient=homme).exists())

    def test_une_seule_grossesse_en_cours_par_patiente(self):
        self._post()
        self._post()
        self.assertEqual(DossierGrossesse.objects.filter(patient=self.patiente).count(), 1)

    def test_date_dans_le_futur_refusee(self):
        reponse = self._post(date_dernieres_regles=(aujourdhui() + timedelta(days=3)).isoformat())
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(DossierGrossesse.objects.exists())

    def test_date_trop_ancienne_refusee(self):
        reponse = self._post(date_dernieres_regles=(aujourdhui() - timedelta(days=400)).isoformat())
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(DossierGrossesse.objects.exists())

    def test_la_parite_doit_etre_inferieure_a_la_gestite(self):
        reponse = self._post(gestite=2, parite=2)
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(DossierGrossesse.objects.exists())

    def test_cloture_du_suivi(self):
        dossier = self.ouvrir_dossier(semaines=39)
        reponse = self.client.post(reverse("maternite:dossier_terminer", args=[dossier.pk]), {
            "statut": "TERMINEE", "date_fin": aujourdhui().isoformat(), "issue": "Garçon 3,2 kg"})
        self.assertRedirects(reponse, reverse("maternite:dossier", args=[dossier.pk]))
        dossier.refresh_from_db()
        self.assertEqual(dossier.statut, "TERMINEE")
        self.assertIsNone(dossier.prochain_rdv)

    def test_apres_cloture_plus_de_nouvelle_visite_et_nouvelle_grossesse_possible(self):
        dossier = self.ouvrir_dossier(semaines=39)
        self.client.post(reverse("maternite:dossier_terminer", args=[dossier.pk]), {
            "statut": "TERMINEE", "date_fin": aujourdhui().isoformat(), "issue": ""})
        reponse = self.client.get(reverse("maternite:visite_nouvelle", args=[dossier.pk]))
        self.assertRedirects(reponse, reverse("maternite:dossier", args=[dossier.pk]))
        self.assertEqual(self.client.get(self.url).status_code, 200)  # une autre grossesse peut s'ouvrir


class VisitePrenataleTests(BaseMaternite):
    def setUp(self):
        super().setUp()
        self.connecter()
        self.dossier = self.ouvrir_dossier(semaines=20)
        self.url = reverse("maternite:visite_nouvelle", args=[self.dossier.pk])

    def _post(self, **over):
        return self.client.post(self.url, self.donnees_visite(**over))

    def test_la_visite_cree_la_consultation_et_les_constantes(self):
        rdv = (aujourdhui() + timedelta(days=28)).isoformat()
        reponse = self._post(prochain_rdv=rdv)
        visite = ConsultationPrenatale.objects.get()
        self.assertRedirects(reponse, reverse("maternite:visite", args=[visite.pk]))
        self.assertEqual(visite.numero, 1)
        self.assertEqual(visite.terme_sa, 20)
        consultation = visite.consultation
        self.assertEqual(consultation.patient, self.patiente)
        self.assertEqual(consultation.praticien, self.sf)
        self.assertEqual(consultation.motif, "Consultation prénatale")
        constantes = Constantes.objects.get(consultation=consultation)
        self.assertEqual(constantes.tension_systolique, 110)
        self.assertEqual(constantes.poids_kg, Decimal("62.5"))

    def test_numerotation_et_prochain_rendez_vous_du_dossier(self):
        self._post(prochain_rdv=(aujourdhui() + timedelta(days=28)).isoformat())
        self._post(prochain_rdv=(aujourdhui() + timedelta(days=14)).isoformat())
        self.assertEqual(list(ConsultationPrenatale.objects.values_list("numero", flat=True)), [1, 2])
        self.dossier.refresh_from_db()
        self.assertEqual(self.dossier.prochain_rdv, aujourdhui() + timedelta(days=14))

    def test_rendez_vous_dans_le_passe_refuse(self):
        reponse = self._post(prochain_rdv=(aujourdhui() - timedelta(days=1)).isoformat())
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(ConsultationPrenatale.objects.exists())

    def test_diastolique_superieure_a_la_systolique_refusee(self):
        reponse = self._post(tension_systolique="100", tension_diastolique="120")
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(ConsultationPrenatale.objects.exists())

    def test_modification_tant_que_la_consultation_est_en_cours(self):
        self._post()
        visite = ConsultationPrenatale.objects.get()
        url = reverse("maternite:visite_modifier", args=[visite.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, self.donnees_visite(tension_systolique="150", tension_diastolique="95"))
        visite.consultation.constantes.refresh_from_db()
        self.assertEqual(visite.consultation.constantes.tension_systolique, 150)

    def test_plus_de_modification_apres_cloture_de_la_consultation(self):
        self._post()
        visite = ConsultationPrenatale.objects.get()
        Consultation.objects.filter(pk=visite.consultation_id).update(statut="CLOTUREE")
        reponse = self.client.get(reverse("maternite:visite_modifier", args=[visite.pk]))
        self.assertRedirects(reponse, reverse("maternite:visite", args=[visite.pk]))

    def test_la_page_de_la_visite_s_affiche_avec_ses_alertes(self):
        self._post(tension_systolique="150", tension_diastolique="95", albuminurie="PLUS2")
        visite = ConsultationPrenatale.objects.get()
        page = self.client.get(reverse("maternite:visite", args=[visite.pk]))
        self.assertContains(page, "pré-éclampsie")

    def test_la_consultation_prenatale_apparait_dans_les_consultations_generales(self):
        self._post()
        self.assertContains(self.client.get(reverse("consultations:liste")), "Consultation prénatale")


class AlertesTests(BaseMaternite):
    _n = 0

    def visite(self, sa=30, tension=None, temperature=None, **champs):
        # Une patiente neuve à chaque appel : une seule grossesse en cours par patiente.
        AlertesTests._n += 1
        with pour_etablissement(self.etab):
            patiente = Patient.objects.create(nom=f"P{self._n}", prenom="X", sexe="F")
        dossier = self.ouvrir_dossier(semaines=sa, patient=patiente)
        with pour_etablissement(self.etab):
            consultation = Consultation.objects.create(patient=patiente, motif="CPN")
            if tension or temperature:
                Constantes.objects.create(
                    consultation=consultation,
                    tension_systolique=tension[0] if tension else None,
                    tension_diastolique=tension[1] if tension else None,
                    temperature_c=temperature)
            return ConsultationPrenatale.objects.create(
                dossier=dossier, consultation=consultation, **champs)

    def niveaux(self, alertes):
        return [a["niveau"] for a in alertes]

    def test_visite_normale_sans_alerte(self):
        v = self.visite(tension=(110, 70), hemoglobine_g_dl=Decimal("12"),
                        bruits_coeur_foetal="PRESENTS", frequence_bcf=140)
        self.assertEqual(alertes_visite(v), [])

    def test_pre_eclampsie_suspectee(self):
        v = self.visite(tension=(150, 95), albuminurie="PLUS2")
        alertes = alertes_visite(v)
        self.assertEqual(alertes[0]["niveau"], "danger")
        self.assertIn("pré-éclampsie", str(alertes[0]["message"]))

    def test_hypertension_simple_est_une_attention(self):
        v = self.visite(tension=(145, 92))
        self.assertEqual(self.niveaux(alertes_visite(v)), ["warning"])

    def test_hypertension_severe(self):
        v = self.visite(tension=(170, 105))
        self.assertEqual(self.niveaux(alertes_visite(v)), ["danger"])

    def test_anemie_moderee_et_severe(self):
        self.assertEqual(self.niveaux(alertes_visite(self.visite(hemoglobine_g_dl=Decimal("9.5")))),
                         ["warning"])
        self.assertEqual(self.niveaux(alertes_visite(self.visite(hemoglobine_g_dl=Decimal("6.5")))),
                         ["danger"])

    def test_absence_de_bcf_dangereuse_seulement_apres_20_sa(self):
        self.assertEqual(self.niveaux(alertes_visite(self.visite(sa=30, bruits_coeur_foetal="ABSENTS"))),
                         ["danger"])
        self.assertEqual(alertes_visite(self.visite(sa=10, bruits_coeur_foetal="ABSENTS")), [])

    def test_frequence_cardiaque_foetale_anormale(self):
        self.assertEqual(self.niveaux(alertes_visite(self.visite(frequence_bcf=100))), ["warning"])
        self.assertEqual(self.niveaux(alertes_visite(self.visite(frequence_bcf=170))), ["warning"])

    def test_siege_a_terme(self):
        self.assertEqual(self.niveaux(alertes_visite(self.visite(sa=37, presentation="SIEGE"))), ["warning"])
        self.assertEqual(alertes_visite(self.visite(sa=30, presentation="SIEGE")), [])

    def test_fievre_glycosurie_vih_syphilis(self):
        v = self.visite(temperature=Decimal("38.5"), glycosurie="PLUS1", depistage_vih="POSITIF",
                        depistage_syphilis="POSITIF")
        self.assertEqual(len(alertes_visite(v)), 4)

    def test_les_alertes_les_plus_graves_d_abord(self):
        v = self.visite(tension=(150, 95), albuminurie="PLUS1", glycosurie="PLUS1")
        niveaux = self.niveaux(alertes_visite(v))
        self.assertEqual(niveaux, sorted(niveaux, key=["danger", "warning", "info"].index))

    def test_dpa_depassee_et_rendez_vous_manque(self):
        dossier = self.ouvrir_dossier(semaines=42)
        dossier.prochain_rdv = aujourdhui() - timedelta(days=3)
        dossier.save(update_fields=["prochain_rdv"])
        messages = [str(a["message"]) for a in alertes_dossier(dossier)]
        self.assertTrue(any("dépassée" in m for m in messages))
        self.assertTrue(any("manqué" in m for m in messages))


class TableauDeBordTests(BaseMaternite):
    def test_listes_de_la_page_d_accueil(self):
        self.connecter()
        with pour_etablissement(self.etab):
            autres = [Patient.objects.create(nom=f"P{i}", prenom="X", sexe="F") for i in range(4)]
        self.ouvrir_dossier(semaines=20, prochain_rdv=None)
        with pour_etablissement(self.etab):
            d1 = DossierGrossesse.objects.create(patient=autres[0], gestite=1, parite=0,
                                                 date_dernieres_regles=aujourdhui() - timedelta(weeks=14))
            d2 = DossierGrossesse.objects.create(patient=autres[1], gestite=1, parite=0,
                                                 date_dernieres_regles=aujourdhui() - timedelta(weeks=14))
            d3 = DossierGrossesse.objects.create(patient=autres[2], gestite=1, parite=0,
                                                 date_dernieres_regles=aujourdhui() - timedelta(weeks=37))
            DossierGrossesse.objects.filter(pk=d1.pk).update(prochain_rdv=aujourdhui())
            DossierGrossesse.objects.filter(pk=d2.pk).update(prochain_rdv=aujourdhui() - timedelta(days=2))
        reponse = self.client.get(reverse("maternite:accueil"))
        self.assertEqual(reponse.context["nb_en_cours"], 4)
        self.assertEqual([d.pk for d in reponse.context["rdv_aujourdhui"]], [d1.pk])
        self.assertEqual([d.pk for d in reponse.context["rdv_manques"]], [d2.pk])
        self.assertEqual([d.pk for d in reponse.context["accouchements_proches"]], [d3.pk])

    def test_liste_des_dossiers_avec_recherche(self):
        self.connecter()
        self.ouvrir_dossier()
        reponse = self.client.get(reverse("maternite:dossiers"), {"q": "Traoré"})
        self.assertContains(reponse, "Traoré")
        reponse = self.client.get(reverse("maternite:dossiers"), {"q": "Inconnue"})
        self.assertNotContains(reponse, "GRO-")


class PrescriptionSageFemmeTests(BaseMaternite):
    def setUp(self):
        super().setUp()
        self.connecter()
        with pour_etablissement(self.etab):
            self.fer = Medicament.objects.create(denomination="Fer + acide folique",
                                                 prescriptible_sage_femme=True)
            self.morphine = Medicament.objects.create(denomination="Tramadol injectable")
            consultation = Consultation.objects.create(patient=self.patiente, praticien=self.sf,
                                                       motif="CPN")
            self.ordonnance = Ordonnance.objects.create(consultation=consultation,
                                                        prescripteur=self.sf)

    def _ajouter(self, medicament):
        return self.client.post(
            reverse("consultations:ligne_ajouter", args=[self.ordonnance.pk]),
            {"medicament": medicament.pk, "posologie": "1/j", "duree_jours": 30,
             "quantite_prescrite": 30, "instructions": ""})

    def test_elle_prescrit_un_medicament_autorise(self):
        self._ajouter(self.fer)
        self.assertEqual(LigneOrdonnance.objects.filter(ordonnance=self.ordonnance).count(), 1)

    def test_elle_ne_peut_pas_prescrire_un_medicament_non_autorise(self):
        self._ajouter(self.morphine)
        self.assertFalse(LigneOrdonnance.objects.filter(ordonnance=self.ordonnance).exists())

    def test_la_liste_deroulante_ne_propose_que_les_medicaments_autorises(self):
        page = self.client.get(reverse("consultations:ordonnance", args=[self.ordonnance.pk]))
        self.assertContains(page, "Fer + acide folique")
        self.assertNotContains(page, "Tramadol injectable")

    def test_un_medecin_n_a_pas_cette_limite(self):
        creer_utilisateur(self.etab, "dr", Role.MEDECIN)
        self.client.logout()
        self.connecter("dr")
        page = self.client.get(reverse("consultations:ordonnance", args=[self.ordonnance.pk]))
        self.assertContains(page, "Tramadol injectable")

    def test_l_api_refuse_aussi_un_medicament_non_autorise(self):
        from types import SimpleNamespace

        from apps.consultations.serializers import LigneOrdonnanceSerializer

        contexte = {"request": SimpleNamespace(user=self.sf)}
        with pour_etablissement(self.etab):
            refuse = LigneOrdonnanceSerializer(
                data={"medicament": self.morphine.pk, "posologie": "1/j"}, context=contexte)
            accepte = LigneOrdonnanceSerializer(
                data={"medicament": self.fer.pk, "posologie": "1/j"}, context=contexte)
            self.assertFalse(refuse.is_valid())
            self.assertIn("medicament", refuse.errors)
            self.assertTrue(accepte.is_valid(), accepte.errors)


class IsolationMaterniteTests(BaseMaternite):
    def test_un_autre_hopital_ne_voit_pas_le_dossier(self):
        dossier = self.ouvrir_dossier()
        autre = Etablissement.objects.create(nom="Autre", slug="autre", statut="ACTIF")
        creer_utilisateur(autre, "sf_b", Role.SAGE_FEMME)
        self.connecter("sf_b")
        self.assertEqual(self.client.get(reverse("maternite:dossier", args=[dossier.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("maternite:dossiers")), "Traoré")
        self.assertEqual(
            self.client.get(reverse("maternite:visite_nouvelle", args=[dossier.pk])).status_code, 404)
