"""Tests des règles de gestion du laboratoire / imagerie (CDC 4.6 / 7.5)."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Notification
from apps.facturation.models import Facture, Tarif
from apps.patients.models import Patient

from . import services
from .models import Categorie, DemandeExamen, Resultat, TypeExamen

Utilisateur = get_user_model()


class BaseLabo(TestCase):
    def setUp(self):
        self.patient = Patient.objects.create(nom="Traoré", prenom="Awa", sexe="F")
        self.medecin = Utilisateur.objects.create_user("doc", password="x",
                                                       role=Utilisateur.Role.MEDECIN)
        self.laborantin = Utilisateur.objects.create_user("lab", password="x",
                                                          role=Utilisateur.Role.LABORANTIN)
        self.gly = TypeExamen.objects.create(code="GLY", libelle="Glycémie",
                                             categorie=Categorie.BIOLOGIE, unite="g/L",
                                             valeurs_reference="0.70 - 1.10")
        self.nfs = TypeExamen.objects.create(code="NFS", libelle="NFS",
                                             categorie=Categorie.BIOLOGIE)
        self.rx = TypeExamen.objects.create(code="RX", libelle="Radio thorax",
                                            categorie=Categorie.IMAGERIE)


class InterpretationTests(TestCase):
    def test_plage_numerique(self):
        self.assertEqual(services.interpreter_valeur("0.9", "0.70 - 1.10"), "NORMAL")
        self.assertEqual(services.interpreter_valeur("0.5", "0.70 - 1.10"), "BAS")
        self.assertEqual(services.interpreter_valeur("1.4", "0.70 - 1.10"), "HAUT")
        self.assertEqual(services.interpreter_valeur("positif", "0.70 - 1.10"), "")
        self.assertEqual(services.interpreter_valeur("5", "présence/absence"), "")


class DemandeTests(BaseLabo):
    def test_reference_et_lignes(self):
        d = services.creer_demande(patient=self.patient, prescripteur=self.medecin,
                                   categorie=Categorie.BIOLOGIE,
                                   types_examens=[self.gly, self.nfs])
        self.assertTrue(d.reference.startswith("EXAM-"))
        self.assertEqual(d.lignes.count(), 2)
        ligne_gly = d.lignes.get(type_examen=self.gly)
        self.assertEqual(ligne_gly.valeurs_reference, "0.70 - 1.10")  # instantané

    def test_examen_hors_categorie_refuse(self):
        with self.assertRaises(services.ErreurLaboratoire):
            services.creer_demande(patient=self.patient, prescripteur=self.medecin,
                                   categorie=Categorie.BIOLOGIE, types_examens=[self.rx])

    def test_demande_vide_refusee(self):
        with self.assertRaises(services.ErreurLaboratoire):
            services.creer_demande(patient=self.patient, prescripteur=self.medecin,
                                   categorie=Categorie.BIOLOGIE, types_examens=[])


class ResultatTests(BaseLabo):
    def setUp(self):
        super().setUp()
        self.demande = services.creer_demande(
            patient=self.patient, prescripteur=self.medecin,
            categorie=Categorie.BIOLOGIE, types_examens=[self.gly, self.nfs])
        self.l_gly = self.demande.lignes.get(type_examen=self.gly)
        self.l_nfs = self.demande.lignes.get(type_examen=self.nfs)

    def test_saisie_partielle_puis_complete(self):
        services.saisir_resultat(ligne=self.l_gly, par=self.laborantin, valeur="0.95")
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, DemandeExamen.Statut.EN_COURS)
        services.saisir_resultat(ligne=self.l_nfs, par=self.laborantin, valeur="RAS")
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut,
                         DemandeExamen.Statut.RESULTATS_DISPONIBLES)

    def test_interpretation_automatique(self):
        r = services.saisir_resultat(ligne=self.l_gly, par=self.laborantin, valeur="1.6")
        self.assertEqual(r.interpretation, Resultat.Interpretation.HAUT)
        self.assertTrue(r.est_anormal)

    def test_validation_exige_tous_les_resultats(self):
        services.saisir_resultat(ligne=self.l_gly, par=self.laborantin, valeur="0.9")
        with self.assertRaises(services.ErreurLaboratoire):
            services.valider_demande(demande=self.demande, par=self.laborantin)

    def test_validation_notifie_le_prescripteur(self):
        services.saisir_resultat(ligne=self.l_gly, par=self.laborantin, valeur="0.9")
        services.saisir_resultat(ligne=self.l_nfs, par=self.laborantin, valeur="RAS")
        services.valider_demande(demande=self.demande, par=self.laborantin)
        self.demande.refresh_from_db()
        self.assertEqual(self.demande.statut, DemandeExamen.Statut.VALIDEE)
        self.assertTrue(Resultat.objects.get(ligne=self.l_gly).valide)
        notif = Notification.objects.filter(destinataire=self.medecin).first()
        self.assertIsNotNone(notif)
        self.assertIn(self.demande.reference, notif.message)

    def test_saisie_impossible_apres_validation(self):
        for l in (self.l_gly, self.l_nfs):
            services.saisir_resultat(ligne=l, par=self.laborantin, valeur="x")
        services.valider_demande(demande=self.demande, par=self.laborantin)
        with self.assertRaises(services.ErreurLaboratoire):
            services.saisir_resultat(ligne=self.l_gly, par=self.laborantin, valeur="y")


class AnnulationTests(BaseLabo):
    def test_motif_obligatoire_et_pas_apres_validation(self):
        d = services.creer_demande(patient=self.patient, prescripteur=self.medecin,
                                   categorie=Categorie.IMAGERIE, types_examens=[self.rx])
        with self.assertRaises(services.ErreurLaboratoire):
            services.annuler_demande(demande=d, motif="")
        services.annuler_demande(demande=d, motif="Demande en double")
        d.refresh_from_db()
        self.assertEqual(d.statut, DemandeExamen.Statut.ANNULEE)


class AutoFactureExamenTests(BaseLabo):
    @override_settings(FACTURATION_AUTO=True)
    def test_validation_genere_une_facture_brouillon(self):
        Tarif.objects.create(code="AN", libelle="Analyse", categorie="ANALYSE",
                             montant=Decimal("3000"))
        d = services.creer_demande(patient=self.patient, prescripteur=self.medecin,
                                   categorie=Categorie.BIOLOGIE, types_examens=[self.gly])
        services.saisir_resultat(ligne=d.lignes.first(), par=self.laborantin,
                                 valeur="0.9")
        services.valider_demande(demande=d, par=self.laborantin)
        self.assertTrue(Facture.objects.filter(
            lignes__type_source="EXAMEN", lignes__source_id=d.pk,
            statut=Facture.Statut.BROUILLON).exists())


class AccesLaboTests(BaseLabo):
    def test_roles(self):
        med = Utilisateur.objects.get(pk=self.medecin.pk)
        lab = Utilisateur.objects.get(pk=self.laborantin.pk)
        radio = Utilisateur.objects.get(pk=Utilisateur.objects.create_user(
            "rad", role=Utilisateur.Role.RADIOLOGUE).pk)
        self.assertTrue(med.has_perm("laboratoire.add_demandeexamen"))
        self.assertFalse(lab.has_perm("laboratoire.add_demandeexamen"))
        self.assertTrue(lab.has_perm("laboratoire.add_resultat"))
        self.assertTrue(lab.has_perm("laboratoire.change_demandeexamen"))
        self.assertTrue(radio.has_perm("laboratoire.add_resultat"))

    def test_laborantin_ne_voit_que_la_biologie(self):
        services.creer_demande(patient=self.patient, prescripteur=self.medecin,
                               categorie=Categorie.BIOLOGIE, types_examens=[self.gly])
        services.creer_demande(patient=self.patient, prescripteur=self.medecin,
                               categorie=Categorie.IMAGERIE, types_examens=[self.rx])
        self.client.login(username="lab", password="x")
        r = self.client.get(reverse("laboratoire:liste"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "EXAM-")            # au moins une demande de biologie
        self.assertNotContains(r, "Radio thorax")  # imagerie masquée pour le laborantin
