"""Tests des règles de gestion de la facturation (CDC 4.8 / 7.5)."""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.assurances.models import Assurance, ContratAssurance, PatientAssure
from apps.consultations.models import Consultation
from apps.patients.models import Patient

from . import services
from .models import Facture, Paiement, Tarif

Utilisateur = get_user_model()


class BaseFacturation(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(nom="Traoré", prenom="Awa", sexe="F")
        Tarif.objects.create(code="CONS", libelle="Consultation", categorie="CONSULTATION",
                             montant=Decimal("5000"))
        self.consultation = Consultation.objects.create(patient=self.patient, motif="fièvre")

    def _assurer(self, taux=70, plafond=None):
        a = Assurance.objects.create(nom="Assur")
        c = ContratAssurance.objects.create(assurance=a, libelle="G",
                                            taux_prise_en_charge=Decimal(taux),
                                            plafond_annuel=plafond)
        return PatientAssure.objects.create(patient=self.patient, contrat=c)


class GenerationTests(BaseFacturation):
    def test_facture_consultation_reprend_le_tarif(self):
        f = services.facturer_consultation(self.consultation)
        self.assertEqual(f.reference[:5], "FACT-")
        self.assertEqual(f.montant_total, Decimal("5000"))
        self.assertEqual(f.part_patient, Decimal("5000"))
        self.assertEqual(f.statut, Facture.Statut.BROUILLON)

    def test_pas_de_double_facturation(self):
        services.facturer_consultation(self.consultation)
        self.assertIsNone(services.facturer_consultation(self.consultation))

    def test_absence_de_tarif_leve_une_erreur(self):
        Tarif.objects.all().delete()
        with self.assertRaises(services.ErreurFacturation):
            services.facturer_consultation(self.consultation)


class CouvertureTests(BaseFacturation):
    def test_repartition_selon_le_taux(self):
        self._assurer(taux=70)
        f = services.facturer_consultation(self.consultation)
        self.assertEqual(f.taux_couverture_applique, Decimal("70.00"))
        self.assertEqual(f.part_assurance, Decimal("3500"))
        self.assertEqual(f.part_patient, Decimal("1500"))

    def test_plafond_annuel_limite_la_part_assurance(self):
        assure = self._assurer(taux=100, plafond=Decimal("2000"))
        f1 = services.facturer_consultation(self.consultation)
        self.assertEqual(f1.part_assurance, Decimal("2000"))  # 5000 plafonné à 2000
        self.assertEqual(f1.part_patient, Decimal("3000"))
        # 2e consultation : plafond déjà consommé
        c2 = Consultation.objects.create(patient=self.patient, motif="suivi")
        f2 = services.facturer_consultation(c2)
        self.assertEqual(f2.part_assurance, Decimal("0"))
        self.assertEqual(assure.consommation_annee(), Decimal("2000"))

    def test_sans_assurance_tout_est_a_la_charge_du_patient(self):
        f = services.facturer_consultation(self.consultation)
        self.assertEqual(f.part_patient, f.montant_total)


class EmissionEtPaiementTests(BaseFacturation):
    def setUp(self):
        super().setUp()
        self.facture = services.facturer_consultation(self.consultation)

    def test_emission(self):
        services.emettre_facture(facture=self.facture)
        self.facture.refresh_from_db()
        self.assertEqual(self.facture.statut, Facture.Statut.EMISE)
        with self.assertRaises(services.ErreurFacturation):
            services.emettre_facture(facture=self.facture)

    def test_paiement_partiel_puis_solde(self):
        services.emettre_facture(facture=self.facture)
        services.enregistrer_paiement(facture=self.facture, montant=2000,
                                      mode=Paiement.Mode.ESPECES)
        self.facture.refresh_from_db()
        self.assertEqual(self.facture.statut, Facture.Statut.PARTIELLE)
        services.enregistrer_paiement(facture=self.facture, montant=3000,
                                      mode=Paiement.Mode.MOBILE_MONEY)
        self.facture.refresh_from_db()
        self.assertEqual(self.facture.statut, Facture.Statut.REGLEE)
        self.assertEqual(self.facture.reste_a_payer, Decimal("0"))

    def test_paiement_superieur_au_reste_refuse(self):
        services.emettre_facture(facture=self.facture)
        with self.assertRaises(services.ErreurFacturation):
            services.enregistrer_paiement(facture=self.facture, montant=99999,
                                          mode=Paiement.Mode.ESPECES)

    def test_paiement_sur_brouillon_refuse(self):
        with self.assertRaises(services.ErreurFacturation):
            services.enregistrer_paiement(facture=self.facture, montant=100,
                                          mode=Paiement.Mode.ESPECES)

    def test_annulation_exige_motif_et_bloquee_si_paiement(self):
        services.emettre_facture(facture=self.facture)
        with self.assertRaises(services.ErreurFacturation):
            services.annuler_facture(facture=self.facture, motif="")
        services.enregistrer_paiement(facture=self.facture, montant=1000,
                                      mode=Paiement.Mode.ESPECES)
        with self.assertRaises(services.ErreurFacturation):
            services.annuler_facture(facture=self.facture, motif="erreur de saisie")


class ImpayesTests(BaseFacturation):
    def test_facture_echue_apparait_dans_les_impayes(self):
        f = services.facturer_consultation(self.consultation)
        services.emettre_facture(facture=f)
        f.date_echeance = date.today() - timedelta(days=5)
        f.save(update_fields=["date_echeance"])
        self.assertIn(f, services.factures_en_retard())
        self.assertTrue(f.en_retard)


class AutoFacturationTests(BaseFacturation):
    @override_settings(FACTURATION_AUTO=True)
    def test_cloture_consultation_genere_une_facture_brouillon(self):
        c = Consultation.objects.create(patient=self.patient, motif="auto")
        self.assertFalse(Facture.objects.filter(
            lignes__source_id=c.pk, lignes__type_source="CONSULTATION").exists())
        c.statut = Consultation.Statut.CLOTUREE
        c.save()
        self.assertTrue(Facture.objects.filter(
            lignes__source_id=c.pk, lignes__type_source="CONSULTATION",
            statut=Facture.Statut.BROUILLON).exists())

    @override_settings(FACTURATION_AUTO=False)
    def test_desactivation_de_l_auto_facturation(self):
        c = Consultation.objects.create(patient=self.patient, motif="manuel")
        c.statut = Consultation.Statut.CLOTUREE
        c.save()
        self.assertFalse(Facture.objects.filter(lignes__source_id=c.pk).exists())


class AccesFacturationTests(BaseFacturation):
    def test_roles(self):
        comptable = Utilisateur.objects.get_or_create(
            username="cpt", role=Utilisateur.Role.COMPTABLE)[0]
        accueil = Utilisateur.objects.get_or_create(
            username="acc", role=Utilisateur.Role.AGENT_ACCUEIL)[0]
        medecin = Utilisateur.objects.get_or_create(
            username="doc", role=Utilisateur.Role.MEDECIN)[0]
        comptable = Utilisateur.objects.get(pk=comptable.pk)
        accueil = Utilisateur.objects.get(pk=accueil.pk)
        medecin = Utilisateur.objects.get(pk=medecin.pk)
        self.assertTrue(comptable.has_perm("facturation.add_facture"))
        self.assertTrue(comptable.has_perm("facturation.add_paiement"))
        self.assertTrue(accueil.has_perm("facturation.view_facture"))
        self.assertFalse(accueil.has_perm("facturation.add_facture"))
        self.assertFalse(medecin.has_perm("facturation.add_facture"))
