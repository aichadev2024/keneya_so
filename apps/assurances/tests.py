"""Tests des règles de gestion des assurances (CDC 4.9 / 7.5)."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.consultations.models import Consultation
from apps.facturation import services as facturation_services
from apps.facturation.models import Tarif
from apps.patients.models import Patient

from . import services
from .models import Assurance, ContratAssurance, PatientAssure

Utilisateur = get_user_model()


class PatientAssureTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(nom="Ba", prenom="Awa", sexe="F")
        self.assurance = Assurance.objects.create(nom="Mutuelle X")
        self.contrat = ContratAssurance.objects.create(
            assurance=self.assurance, libelle="Base",
            taux_prise_en_charge=Decimal("60"), plafond_annuel=Decimal("100000"))

    def test_taux_effectif_surcharge_le_contrat(self):
        pa = PatientAssure.objects.create(patient=self.patient, contrat=self.contrat)
        self.assertEqual(pa.taux_effectif, Decimal("60"))
        pa.taux_prise_en_charge = Decimal("85")
        pa.save()
        self.assertEqual(pa.taux_effectif, Decimal("85"))

    def test_couverture_selon_les_dates(self):
        pa = PatientAssure.objects.create(
            patient=self.patient, contrat=self.contrat,
            date_debut=date.today() - timedelta(days=10),
            date_fin=date.today() - timedelta(days=1))
        self.assertFalse(pa.couvert_a())
        pa.date_fin = date.today() + timedelta(days=30)
        pa.save()
        self.assertTrue(pa.couvert_a())

    def test_plafond_restant_diminue_avec_la_consommation(self):
        Tarif.objects.create(code="C", libelle="Consultation",
                             categorie="CONSULTATION", montant=Decimal("20000"))
        pa = PatientAssure.objects.create(patient=self.patient, contrat=self.contrat)
        self.assertEqual(pa.plafond_restant(), Decimal("100000"))
        c = Consultation.objects.create(patient=self.patient, motif="x")
        facturation_services.facturer_consultation(c)  # part assurance = 12000
        self.assertEqual(pa.consommation_annee(), Decimal("12000"))
        self.assertEqual(pa.plafond_restant(), Decimal("88000"))


class BordereauTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(nom="Ka", prenom="M", sexe="M")
        self.assurance = Assurance.objects.create(nom="INPS")
        contrat = ContratAssurance.objects.create(
            assurance=self.assurance, libelle="G", taux_prise_en_charge=Decimal("80"))
        PatientAssure.objects.create(patient=self.patient, contrat=contrat)
        Tarif.objects.create(code="C", libelle="Consultation",
                             categorie="CONSULTATION", montant=Decimal("10000"))
        c = Consultation.objects.create(patient=self.patient, motif="x")
        self.facture = facturation_services.facturer_consultation(c)
        facturation_services.emettre_facture(facture=self.facture)

    def test_generation_regroupe_les_parts_assurance(self):
        bordereau = services.generer_bordereau(
            assurance=self.assurance,
            periode_debut=date.today() - timedelta(days=1),
            periode_fin=date.today() + timedelta(days=1))
        self.assertEqual(bordereau.reference[:5], "BORD-")
        self.assertEqual(bordereau.lignes.count(), 1)
        self.assertEqual(bordereau.montant_total, Decimal("8000"))

    def test_facture_deja_sur_un_bordereau_est_exclue(self):
        services.generer_bordereau(
            assurance=self.assurance,
            periode_debut=date.today() - timedelta(days=1),
            periode_fin=date.today() + timedelta(days=1))
        with self.assertRaises(services.ErreurBordereau):
            services.generer_bordereau(
                assurance=self.assurance,
                periode_debut=date.today() - timedelta(days=1),
                periode_fin=date.today() + timedelta(days=1))

    def test_periode_sans_facture_leve_une_erreur(self):
        with self.assertRaises(services.ErreurBordereau):
            services.generer_bordereau(
                assurance=self.assurance,
                periode_debut=date.today() + timedelta(days=10),
                periode_fin=date.today() + timedelta(days=20))


class AccesAssurancesTests(TestCase):
    def test_roles(self):
        comptable = Utilisateur.objects.get(
            pk=Utilisateur.objects.create_user("cpt", role=Utilisateur.Role.COMPTABLE).pk)
        accueil = Utilisateur.objects.get(
            pk=Utilisateur.objects.create_user("acc",
                                               role=Utilisateur.Role.AGENT_ACCUEIL).pk)
        self.assertTrue(comptable.has_perm("assurances.add_bordereauassurance"))
        self.assertTrue(accueil.has_perm("assurances.add_patientassure"))
        self.assertFalse(accueil.has_perm("assurances.add_bordereauassurance"))
