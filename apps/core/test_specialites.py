"""Spécialités activables par hôpital (ophtalmologie, pédiatrie, odontologie)."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.consultations.forms import ConsultationForm
from apps.consultations.models import Consultation
from apps.core.models import Etablissement, Plan, Specialite
from apps.core.tenancy import pour_etablissement
from apps.patients.models import Patient

Utilisateur = get_user_model()


class CatalogueTests(TestCase):
    def test_catalogue_par_defaut(self):
        codes = set(Specialite.objects.values_list("code", flat=True))
        self.assertEqual(codes, {"ophtalmologie", "pediatrie", "odontologie"})


class ChoixALaCreationTests(TestCase):
    def setUp(self):
        cache.clear()
        Utilisateur.tous.create_superuser("proprio", "p@keneya.ml", "x")
        self.client.login(username="proprio", password="x")
        self.plan = Plan.objects.get(code="essentiel")

    def _creer(self, specialites):
        return self.client.post(reverse("core:proprietaire_etablissement_creer"), {
            "nom": "Clinique des Yeux", "plan": self.plan.pk, "statut": "ESSAI",
            "essai_jusqu_au": "", "admin_prenom": "A", "admin_nom": "B",
            "admin_email": "a@yeux.ml", "admin_username": "yeux_admin",
            "specialites": specialites})

    def test_le_formulaire_propose_les_specialites(self):
        page = self.client.get(reverse("core:proprietaire_etablissement_creer"))
        for nom in ("Ophtalmologie", "Pédiatrie", "Odontologie"):
            self.assertContains(page, nom)

    def test_les_specialites_cochees_sont_enregistrees(self):
        oph = Specialite.objects.get(code="ophtalmologie")
        ped = Specialite.objects.get(code="pediatrie")
        self.assertEqual(self._creer([oph.pk, ped.pk]).status_code, 302)
        etab = Etablissement.objects.get(nom="Clinique des Yeux")
        self.assertEqual(set(etab.specialites.all()), {oph, ped})

    def test_modification_ulterieure(self):
        self._creer([])
        etab = Etablissement.objects.get(nom="Clinique des Yeux")
        dent = Specialite.objects.get(code="odontologie")
        r = self.client.post(
            reverse("core:proprietaire_etablissement_modifier", args=[etab.pk]),
            {"nom": etab.nom, "plan": self.plan.pk, "statut": "ESSAI", "essai_jusqu_au": "",
             "specialites": [dent.pk]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(list(etab.specialites.all()), [dent])


class ConsultationParSpecialiteTests(TestCase):
    def setUp(self):
        self.etab = Etablissement.defaut()
        self.oph = Specialite.objects.get(code="ophtalmologie")

    def test_champ_absent_si_l_hopital_n_a_aucune_specialite(self):
        with pour_etablissement(self.etab):
            self.assertNotIn("specialite", ConsultationForm().fields)

    def test_champ_limite_aux_specialites_de_l_hopital(self):
        self.etab.specialites.add(self.oph)
        with pour_etablissement(self.etab):
            champ = ConsultationForm().fields["specialite"]
            self.assertEqual(list(champ.queryset), [self.oph])

    def test_filtre_de_la_liste_par_specialite(self):
        self.etab.specialites.add(self.oph)
        patient = Patient.objects.create(nom="Traoré", prenom="Awa", sexe="F")
        Consultation.objects.create(patient=patient, motif="vue floue", specialite=self.oph)
        Consultation.objects.create(patient=patient, motif="toux")
        Utilisateur.objects.create_user("doc", password="x",
                                        role=Utilisateur.Role.MEDECIN)
        self.client.login(username="doc", password="x")
        page = self.client.get(reverse("consultations:liste"), {"specialite": self.oph.pk})
        self.assertContains(page, "vue floue")
        self.assertNotContains(page, "toux")


class AffichageCasesTests(TestCase):
    def test_la_classe_bootstrap_est_sur_chaque_case_et_pas_sur_le_conteneur(self):
        from apps.core.forms import EtablissementModifierForm
        html = str(EtablissementModifierForm()["specialites"])
        self.assertEqual(html.count("form-check-input"), Specialite.objects.count())
        self.assertNotIn('<div id="id_specialites" class="form-check-input', html)
