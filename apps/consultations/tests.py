"""Tests des règles de gestion du module consultations (CDC 4.2 / 4.3 / 7.5)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.patients.models import Allergie, Patient
from apps.pharmacie.models import InteractionMedicamenteuse, Medicament

from .models import Consultation, LigneOrdonnance, Ordonnance
from .services import alertes_prescription

Utilisateur = get_user_model()


class ReferencesTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(nom="Diallo", prenom="Awa", sexe="F")

    def test_reference_consultation_incrementee(self):
        c1 = Consultation.objects.create(patient=self.patient, motif="fièvre")
        c2 = Consultation.objects.create(patient=self.patient, motif="toux")
        annee = date.today().year
        self.assertEqual(c1.reference, f"CONS-{annee}-000001")
        self.assertEqual(c2.reference, f"CONS-{annee}-000002")

    def test_reference_ordonnance_incrementee(self):
        c = Consultation.objects.create(patient=self.patient, motif="x")
        o = Ordonnance.objects.create(consultation=c)
        self.assertTrue(o.reference.startswith("ORD-"))


class TransmissionOrdonnanceTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(nom="Ba", prenom="Modibo", sexe="M")
        self.consultation = Consultation.objects.create(patient=self.patient, motif="x")
        self.ordonnance = Ordonnance.objects.create(consultation=self.consultation)

    def test_transmettre_change_statut_et_horodate(self):
        self.assertEqual(self.ordonnance.statut, Ordonnance.Statut.BROUILLON)
        self.ordonnance.transmettre()
        self.ordonnance.refresh_from_db()
        self.assertEqual(self.ordonnance.statut, Ordonnance.Statut.TRANSMISE)
        self.assertIsNotNone(self.ordonnance.date_transmission)

    def test_transmettre_est_idempotent(self):
        self.ordonnance.transmettre()
        premiere_date = self.ordonnance.date_transmission
        self.ordonnance.transmettre()
        self.assertEqual(self.ordonnance.date_transmission, premiere_date)

    def test_transmission_ouvre_une_dispensation(self):
        from apps.pharmacie.models import Dispensation
        self.ordonnance.transmettre()
        self.assertTrue(Dispensation.objects.filter(ordonnance=self.ordonnance).exists())


class AlertesPrescriptionTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(nom="Keïta", prenom="Sira", sexe="F")
        self.penicilline = Medicament.objects.create(denomination="Pénicilline",
                                                     dosage="1 M UI")
        self.parac = Medicament.objects.create(denomination="Paracétamol", dosage="500 mg")
        self.consultation = Consultation.objects.create(patient=self.patient, motif="x")
        self.ordonnance = Ordonnance.objects.create(consultation=self.consultation)

    def test_alerte_allergie(self):
        Allergie.objects.create(dossier=self.patient.dossier_medical,
                                libelle="Pénicilline", severite=Allergie.Severite.SEVERE)
        LigneOrdonnance.objects.create(ordonnance=self.ordonnance,
                                       medicament=self.penicilline, posologie="1/j")
        alertes = alertes_prescription(self.ordonnance)
        self.assertTrue(any("Pénicilline" in a["message"] for a in alertes))
        self.assertTrue(any(a["niveau"] == "danger" for a in alertes))

    def test_alerte_interaction(self):
        InteractionMedicamenteuse.objects.create(
            medicament_a=self.penicilline, medicament_b=self.parac,
            gravite=InteractionMedicamenteuse.Gravite.MAJEURE,
        )
        LigneOrdonnance.objects.create(ordonnance=self.ordonnance,
                                       medicament=self.penicilline, posologie="1/j")
        LigneOrdonnance.objects.create(ordonnance=self.ordonnance,
                                       medicament=self.parac, posologie="3/j")
        alertes = alertes_prescription(self.ordonnance)
        self.assertTrue(any("Interaction" in a["message"] for a in alertes))

    def test_pas_d_alerte_sans_allergie_ni_interaction(self):
        LigneOrdonnance.objects.create(ordonnance=self.ordonnance,
                                       medicament=self.parac, posologie="3/j")
        self.assertEqual(alertes_prescription(self.ordonnance), [])


class AccesConsultationsTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(nom="Sow", prenom="Ali", sexe="M")

    def test_medecin_peut_ouvrir_le_formulaire_de_consultation(self):
        Utilisateur.objects.create_user("doc", password="x", role=Utilisateur.Role.MEDECIN)
        self.client.login(username="doc", password="x")
        r = self.client.get(reverse("consultations:creer", args=[self.patient.pk]))
        self.assertEqual(r.status_code, 200)

    def test_agent_accueil_ne_voit_pas_les_consultations(self):
        Utilisateur.objects.create_user("acc", password="x",
                                        role=Utilisateur.Role.AGENT_ACCUEIL)
        self.client.login(username="acc", password="x")
        r = self.client.get(reverse("consultations:liste"))
        self.assertEqual(r.status_code, 403)

    def test_infirmier_peut_saisir_les_constantes_pas_creer_de_consultation(self):
        inf = Utilisateur.objects.create_user("inf", password="x",
                                              role=Utilisateur.Role.INFIRMIER)
        inf = Utilisateur.objects.get(pk=inf.pk)
        self.assertTrue(inf.has_perm("consultations.change_constantes"))
        self.assertFalse(inf.has_perm("consultations.add_consultation"))
