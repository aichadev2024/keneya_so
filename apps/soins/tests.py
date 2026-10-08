"""Soins (injections, pansements) : droits par rôle et enregistrement."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.roles import roles_avec_permission
from apps.patients.models import Patient

from .models import Soin

Utilisateur = get_user_model()
Role = Utilisateur.Role


class DroitsSoinsTests(TestCase):
    def test_infirmier_et_chirurgien_realisent_les_soins(self):
        for role in (Role.INFIRMIER, Role.CHIRURGIEN):
            self.assertIn(role, roles_avec_permission("soins.add_soin"), role)

    def test_medecin_et_anesthesiste_consultent_sans_creer(self):
        for role in (Role.MEDECIN, Role.ANESTHESISTE):
            self.assertIn(role, roles_avec_permission("soins.view_soin"), role)
            self.assertNotIn(role, roles_avec_permission("soins.add_soin"), role)

    def test_les_autres_roles_n_y_ont_pas_acces(self):
        autorises = roles_avec_permission("soins.view_soin")
        for role in (Role.AGENT_ACCUEIL, Role.COMPTABLE, Role.PHARMACIEN,
                     Role.LABORANTIN, Role.RADIOLOGUE):
            self.assertNotIn(role, autorises, role)


class EnregistrementSoinTests(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(nom="Traoré", prenom="Awa", sexe="F")
        Utilisateur.objects.create_user("inf", password="x", role=Role.INFIRMIER)

    def test_l_infirmier_enregistre_une_injection(self):
        self.client.login(username="inf", password="x")
        r = self.client.post(reverse("soins:creer", args=[self.patient.pk]), {
            "type_soin": Soin.Type.INJECTION, "description": "Ceftriaxone 1 g IM fesse droite",
            "date_soin": "2026-10-08T10:30"})
        self.assertEqual(r.status_code, 302)
        soin = Soin.objects.get()
        self.assertTrue(soin.reference.startswith("SOIN-"))
        self.assertEqual(soin.soignant.username, "inf")
        self.assertIsNone(soin.hospitalisation)

    def test_pansement_post_operatoire_pour_le_chirurgien(self):
        Utilisateur.objects.create_user("chir", password="x", role=Role.CHIRURGIEN)
        self.client.login(username="chir", password="x")
        r = self.client.post(reverse("soins:creer", args=[self.patient.pk]), {
            "type_soin": Soin.Type.PANSEMENT_POSTOP, "description": "Plaie propre, sèche",
            "date_soin": "2026-10-08T11:00"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Soin.objects.get().type_soin, Soin.Type.PANSEMENT_POSTOP)

    def test_l_accueil_ne_peut_pas_enregistrer(self):
        Utilisateur.objects.create_user("acc", password="x", role=Role.AGENT_ACCUEIL)
        self.client.login(username="acc", password="x")
        r = self.client.get(reverse("soins:creer", args=[self.patient.pk]))
        self.assertEqual(r.status_code, 403)

    def test_liste_et_detail(self):
        self.client.login(username="inf", password="x")
        soin = Soin.objects.create(patient=self.patient, type_soin=Soin.Type.PANSEMENT,
                                   description="Pansement jambe")
        self.assertContains(self.client.get(reverse("soins:liste")), soin.reference)
        self.assertContains(self.client.get(reverse("soins:detail", args=[soin.pk])),
                            "Pansement jambe")
        page = self.client.get(reverse("patients:detail", args=[self.patient.pk]))
        self.assertContains(page, reverse("soins:creer", args=[self.patient.pk]))
