"""Le laborantin joint un PDF/une image à un résultat (biologie comprise) et ajoute des analyses."""

import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from . import services
from .models import Categorie, Resultat, TypeExamen
from .tests import BaseLabo

PDF = b"%PDF-1.4\n%fichier de test\n"


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class PieceJointeBiologieTests(BaseLabo):
    def setUp(self):
        super().setUp()
        self.demande = services.creer_demande(
            patient=self.patient, prescripteur=self.medecin,
            categorie=Categorie.BIOLOGIE, types_examens=[self.gly])
        self.ligne = self.demande.lignes.get()
        self.client.login(username="lab", password="x")
        self.url = reverse("laboratoire:saisir_resultat", args=[self.demande.pk, self.ligne.pk])

    def test_pdf_joint_a_une_analyse_biologique(self):
        self.client.post(self.url, {"valeur": "0.95",
                                    "fichier": SimpleUploadedFile("res.pdf", PDF)})
        r = Resultat.objects.get(ligne=self.ligne)
        self.assertTrue(r.fichier.name.endswith(".pdf"))
        dl = self.client.get(reverse("laboratoire:telecharger_resultat",
                                     args=[self.demande.pk, self.ligne.pk]))
        self.assertEqual(dl.status_code, 200)

    def test_pdf_seul_sans_valeur_est_accepte(self):
        self.client.post(self.url, {"fichier": SimpleUploadedFile("res.pdf", PDF)})
        self.assertTrue(Resultat.objects.filter(ligne=self.ligne).exists())

    def test_ni_valeur_ni_fichier_refuse(self):
        self.client.post(self.url, {"valeur": ""})
        self.assertFalse(Resultat.objects.filter(ligne=self.ligne).exists())

    def test_fichier_deguise_refuse(self):
        self.client.post(self.url, {"valeur": "1",
                                    "fichier": SimpleUploadedFile("x.pdf", b"MZ pas un pdf")})
        self.assertFalse(Resultat.objects.filter(ligne=self.ligne).exists())


class AjoutAnalyseTests(BaseLabo):
    def test_laborantin_ajoute_une_analyse(self):
        self.client.login(username="lab", password="x")
        r = self.client.post(reverse("laboratoire:typeexamen_ajouter"), {
            "code": "crp", "libelle": "CRP", "categorie": Categorie.BIOLOGIE,
            "unite": "mg/L", "valeurs_reference": "0 - 5", "delai_rendu_heures": 4})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(TypeExamen.objects.filter(code="CRP").exists())

    def test_code_deja_utilise_refuse(self):
        self.client.login(username="lab", password="x")
        self.client.post(reverse("laboratoire:typeexamen_ajouter"), {
            "code": "GLY", "libelle": "Doublon", "categorie": Categorie.BIOLOGIE,
            "delai_rendu_heures": 4})
        self.assertEqual(TypeExamen.objects.filter(code="GLY").count(), 1)

    def test_medecin_ne_peut_pas_ajouter(self):
        self.client.login(username="doc", password="x")
        r = self.client.get(reverse("laboratoire:typeexamen_ajouter"))
        self.assertEqual(r.status_code, 403)
