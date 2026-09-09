"""Tests des règles de gestion de l'hospitalisation (CDC 4.4 / 7.5)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from apps.patients.models import Patient

from .models import Chambre, Hospitalisation, Lit, Service
from .services import ErreurHospitalisation, admettre, prononcer_sortie, transferer

Utilisateur = get_user_model()


class BaseHospit(TestCase):
    def setUp(self):
        self.service = Service.objects.create(nom="Médecine")
        self.chambre = Chambre.objects.create(service=self.service, numero="01")
        self.lit1 = Lit.objects.create(chambre=self.chambre, numero="1")
        self.lit2 = Lit.objects.create(chambre=self.chambre, numero="2")
        self.patient = Patient.objects.create(nom="Traoré", prenom="Awa", sexe="F")


class AdmissionTests(BaseHospit):
    def test_reference_generee(self):
        h = admettre(patient=self.patient, service=self.service, lit=self.lit1,
                     motif="obs")
        self.assertEqual(h.reference, f"HOSP-{date.today().year}-000001")

    def test_lit_devient_occupe(self):
        self.assertTrue(self.lit1.est_disponible)
        admettre(patient=self.patient, service=self.service, lit=self.lit1, motif="x")
        self.assertFalse(self.lit1.est_disponible)
        self.assertTrue(self.lit1.est_occupe)

    def test_admission_enregistre_un_mouvement_de_lit(self):
        h = admettre(patient=self.patient, service=self.service, lit=self.lit1, motif="x")
        self.assertEqual(h.mouvements_lit.count(), 1)
        self.assertEqual(h.mouvements_lit.first().lit_nouveau, self.lit1)

    def test_impossible_d_admettre_dans_un_lit_occupe(self):
        admettre(patient=self.patient, service=self.service, lit=self.lit1, motif="x")
        autre = Patient.objects.create(nom="Ba", prenom="Ali", sexe="M")
        with self.assertRaises(ErreurHospitalisation):
            admettre(patient=autre, service=self.service, lit=self.lit1, motif="y")

    def test_impossible_d_admettre_dans_un_lit_hors_service(self):
        self.lit1.statut = Lit.Statut.HORS_SERVICE
        self.lit1.save()
        with self.assertRaises(ErreurHospitalisation):
            admettre(patient=self.patient, service=self.service, lit=self.lit1, motif="x")

    def test_lit_hors_service_du_mauvais_service_refuse(self):
        autre_service = Service.objects.create(nom="Chirurgie")
        with self.assertRaises(ErreurHospitalisation):
            admettre(patient=self.patient, service=autre_service, lit=self.lit1, motif="x")

    def test_contrainte_un_seul_sejour_en_cours_par_lit(self):
        admettre(patient=self.patient, service=self.service, lit=self.lit1, motif="x")
        autre = Patient.objects.create(nom="Sow", prenom="Bou", sexe="M")
        with self.assertRaises(IntegrityError):
            Hospitalisation.objects.create(
                patient=autre, service=self.service, lit=self.lit1, motif="doublon")


class TransfertEtSortieTests(BaseHospit):
    def setUp(self):
        super().setUp()
        self.h = admettre(patient=self.patient, service=self.service, lit=self.lit1,
                          motif="x")

    def test_transfert_libere_l_ancien_lit_et_occupe_le_nouveau(self):
        transferer(hospitalisation=self.h, nouveau_lit=self.lit2, motif="rapprochement")
        self.h.refresh_from_db()
        self.assertEqual(self.h.lit, self.lit2)
        self.assertTrue(self.lit1.est_disponible)
        self.assertTrue(self.lit2.est_occupe)
        self.assertEqual(self.h.mouvements_lit.count(), 2)

    def test_transfert_vers_lit_occupe_refuse(self):
        autre = Patient.objects.create(nom="Cissé", prenom="Fanta", sexe="F")
        admettre(patient=autre, service=self.service, lit=self.lit2, motif="y")
        with self.assertRaises(ErreurHospitalisation):
            transferer(hospitalisation=self.h, nouveau_lit=self.lit2)

    def test_sortie_cloture_le_sejour_et_libere_le_lit(self):
        prononcer_sortie(hospitalisation=self.h,
                         mode_sortie=Hospitalisation.ModeSortie.DOMICILE,
                         compte_rendu="Évolution favorable.")
        self.h.refresh_from_db()
        self.assertEqual(self.h.statut, Hospitalisation.Statut.SORTIE)
        self.assertIsNotNone(self.h.date_sortie)
        self.assertTrue(self.lit1.est_disponible)

    def test_sortie_deja_close_refuse(self):
        prononcer_sortie(hospitalisation=self.h,
                         mode_sortie=Hospitalisation.ModeSortie.DOMICILE, compte_rendu="x")
        with self.assertRaises(ErreurHospitalisation):
            prononcer_sortie(hospitalisation=self.h,
                             mode_sortie=Hospitalisation.ModeSortie.DOMICILE,
                             compte_rendu="y")

    def test_lit_libere_reutilisable(self):
        prononcer_sortie(hospitalisation=self.h,
                         mode_sortie=Hospitalisation.ModeSortie.DOMICILE, compte_rendu="x")
        autre = Patient.objects.create(nom="Diallo", prenom="Modibo", sexe="M")
        h2 = admettre(patient=autre, service=self.service, lit=self.lit1, motif="z")
        self.assertEqual(h2.lit, self.lit1)


class OccupationServiceTests(BaseHospit):
    def test_taux_occupation(self):
        self.assertEqual(self.service.taux_occupation, 0)
        admettre(patient=self.patient, service=self.service, lit=self.lit1, motif="x")
        self.assertEqual(self.service.nb_lits_occupes, 1)
        self.assertEqual(self.service.taux_occupation, 50)  # 1 / 2 lits


class AccesHospitalisationTests(BaseHospit):
    def test_infirmier_voit_l_occupation_mais_n_admet_pas(self):
        inf = Utilisateur.objects.create_user("inf", password="x",
                                              role=Utilisateur.Role.INFIRMIER)
        inf = Utilisateur.objects.get(pk=inf.pk)
        self.assertTrue(inf.has_perm("hospitalisation.view_hospitalisation"))
        self.assertTrue(inf.has_perm("hospitalisation.add_notesuivi"))
        self.assertFalse(inf.has_perm("hospitalisation.add_hospitalisation"))

        self.client.login(username="inf", password="x")
        r = self.client.get(reverse("hospitalisation:occupation"))
        self.assertEqual(r.status_code, 200)

    def test_agent_accueil_peut_admettre(self):
        acc = Utilisateur.objects.create_user("acc", password="x",
                                              role=Utilisateur.Role.AGENT_ACCUEIL)
        acc = Utilisateur.objects.get(pk=acc.pk)
        self.assertTrue(acc.has_perm("hospitalisation.add_hospitalisation"))

    def test_agent_sterilisation_refuse(self):
        Utilisateur.objects.create_user("ster", password="x",
                                        role=Utilisateur.Role.AGENT_STERILISATION)
        self.client.login(username="ster", password="x")
        r = self.client.get(reverse("hospitalisation:occupation"))
        self.assertEqual(r.status_code, 403)
