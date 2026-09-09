"""Tests des règles de gestion de la pharmacie (CDC 4.5 / 7.5)."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.consultations.models import Consultation, LigneOrdonnance, Ordonnance
from apps.patients.models import Patient

from .models import Dispensation, LotMedicament, Medicament, MouvementStock
from .services import ErreurStock, dispenser_ordonnance, enregistrer_entree, retirer_perimes

Utilisateur = get_user_model()

DANS_UN_AN = date.today() + timedelta(days=365)
HIER = date.today() - timedelta(days=1)


class StockTests(TestCase):
    def setUp(self):
        self.med = Medicament.objects.create(denomination="Amoxicilline", dosage="500 mg",
                                             seuil_alerte=20)

    def test_creation_lot_journalise_une_entree(self):
        enregistrer_entree(medicament=self.med, numero_lot="L1", quantite=100,
                           date_peremption=DANS_UN_AN)
        mvt = MouvementStock.objects.get(medicament=self.med)
        self.assertEqual(mvt.type, MouvementStock.Type.ENTREE)
        self.assertEqual(mvt.quantite, 100)
        self.assertEqual(self.med.quantite_utilisable, 100)

    def test_seuil_alerte(self):
        enregistrer_entree(medicament=self.med, numero_lot="L1", quantite=15,
                           date_peremption=DANS_UN_AN)
        self.assertTrue(self.med.en_alerte)
        enregistrer_entree(medicament=self.med, numero_lot="L2", quantite=10,
                           date_peremption=DANS_UN_AN)
        self.assertFalse(self.med.en_alerte)

    def test_lot_perime_exclu_du_stock_utilisable(self):
        LotMedicament.objects.create(medicament=self.med, numero_lot="P", quantite=50,
                                     quantite_initiale=50, date_peremption=HIER)
        self.assertEqual(self.med.quantite_en_stock, 50)
        self.assertEqual(self.med.quantite_utilisable, 0)

    def test_retirer_perimes(self):
        LotMedicament.objects.create(medicament=self.med, numero_lot="P", quantite=50,
                                     quantite_initiale=50, date_peremption=HIER)
        total = retirer_perimes()
        self.assertEqual(total, 50)
        self.assertEqual(self.med.quantite_en_stock, 0)
        self.assertTrue(MouvementStock.objects.filter(
            type=MouvementStock.Type.RETRAIT_PEREMPTION).exists())


class DispensationFEFOTests(TestCase):
    def setUp(self):
        self.pharma = Utilisateur.objects.create_user(
            "ph", password="x", role=Utilisateur.Role.PHARMACIEN)
        self.med = Medicament.objects.create(denomination="Ibuprofène", dosage="400 mg")
        # Lot A périme plus tôt que lot B
        self.lot_a = LotMedicament.objects.create(
            medicament=self.med, numero_lot="A", quantite=30, quantite_initiale=30,
            date_peremption=date.today() + timedelta(days=30))
        self.lot_b = LotMedicament.objects.create(
            medicament=self.med, numero_lot="B", quantite=30, quantite_initiale=30,
            date_peremption=date.today() + timedelta(days=300))

        patient = Patient.objects.create(nom="Cissé", prenom="Bou", sexe="M")
        consultation = Consultation.objects.create(patient=patient, motif="douleur")
        self.ordo = Ordonnance.objects.create(consultation=consultation)
        self.ligne = LigneOrdonnance.objects.create(
            ordonnance=self.ordo, medicament=self.med, posologie="1x3/j",
            quantite_prescrite=40)
        self.ordo.transmettre()

    def test_allocation_fefo_consomme_le_lot_le_plus_proche_de_peremption(self):
        dispenser_ordonnance(ordonnance=self.ordo, pharmacien=self.pharma,
                             quantites={self.ligne.id: 40})
        self.lot_a.refresh_from_db()
        self.lot_b.refresh_from_db()
        self.assertEqual(self.lot_a.quantite, 0)   # 30 pris en premier
        self.assertEqual(self.lot_b.quantite, 20)  # 10 pris ensuite

    def test_statut_complete_quand_tout_est_delivre(self):
        dispensation = dispenser_ordonnance(
            ordonnance=self.ordo, pharmacien=self.pharma,
            quantites={self.ligne.id: 40})
        self.assertEqual(dispensation.statut, Dispensation.Statut.COMPLETE)
        self.ordo.refresh_from_db()
        self.assertEqual(self.ordo.statut, Ordonnance.Statut.DISPENSEE)

    def test_dispensation_partielle(self):
        dispensation = dispenser_ordonnance(
            ordonnance=self.ordo, pharmacien=self.pharma,
            quantites={self.ligne.id: 10})
        self.assertEqual(dispensation.statut, Dispensation.Statut.PARTIELLE)
        self.ordo.refresh_from_db()
        self.assertEqual(self.ordo.statut, Ordonnance.Statut.DISPENSEE_PARTIELLE)

    def test_stock_insuffisant_leve_une_erreur_sans_rien_modifier(self):
        with self.assertRaises(ErreurStock):
            dispenser_ordonnance(ordonnance=self.ordo, pharmacien=self.pharma,
                                 quantites={self.ligne.id: 999})
        self.lot_a.refresh_from_db()
        self.lot_b.refresh_from_db()
        self.assertEqual(self.lot_a.quantite, 30)
        self.assertEqual(self.lot_b.quantite, 30)
        self.assertEqual(self.ligne.quantite_dispensee, 0)


class AccesPharmacieTests(TestCase):
    def test_pharmacien_accede_a_la_file_de_dispensation(self):
        Utilisateur.objects.create_user("ph", password="x",
                                        role=Utilisateur.Role.PHARMACIEN)
        self.client.login(username="ph", password="x")
        r = self.client.get("/fr/pharmacie/dispensations/")
        self.assertEqual(r.status_code, 200)

    def test_medecin_ne_dispense_pas(self):
        doc = Utilisateur.objects.create_user("doc", password="x",
                                              role=Utilisateur.Role.MEDECIN)
        doc = Utilisateur.objects.get(pk=doc.pk)
        self.assertFalse(doc.has_perm("pharmacie.add_lignedispensation"))
        self.assertTrue(doc.has_perm("pharmacie.view_medicament"))
