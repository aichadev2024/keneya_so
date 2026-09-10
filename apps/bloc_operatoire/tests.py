"""Tests des règles de gestion du bloc opératoire (CDC section 5, en particulier 5.4)."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.patients.models import Patient

from . import services
from .models import (
    EtapeChecklist,
    Intervention,
    MembreEquipe,
    SalleOperatoire,
    TypeIntervention,
)

Utilisateur = get_user_model()


def _dt(jours=0, h=8, m=0):
    return timezone.make_aware(
        timezone.datetime.combine(date.today() + timedelta(days=jours),
                                  timezone.datetime.min.time()).replace(hour=h, minute=m)
    )


class BaseBloc(TestCase):
    def setUp(self):
        self.salle = SalleOperatoire.objects.create(nom="Salle 1", duree_nettoyage_min=30)
        self.type = TypeIntervention.objects.create(libelle="Appendicectomie",
                                                    duree_standard_min=60)
        self.chir = Utilisateur.objects.create_user("chir", password="x",
                                                    role=Utilisateur.Role.CHIRURGIEN)
        self.patient = Patient.objects.create(nom="Ba", prenom="Awa", sexe="F")

    def _intervention(self, urgence=Intervention.Urgence.PROGRAMMEE, patient=None):
        return Intervention.objects.create(
            patient=patient or self.patient, type_intervention=self.type,
            chirurgien_principal=self.chir, motif_operation="x",
            niveau_urgence=urgence, duree_estimee_min=60,
        )


class ReferenceTests(BaseBloc):
    def test_reference_incrementee(self):
        i1 = self._intervention()
        i2 = self._intervention(patient=Patient.objects.create(nom="Ka", prenom="M", sexe="M"))
        annee = date.today().year
        self.assertEqual(i1.reference, f"BLOC-{annee}-000001")
        self.assertEqual(i2.reference, f"BLOC-{annee}-000002")


class ConflitSalleTests(BaseBloc):
    def test_double_reservation_bloquee(self):
        i1 = self._intervention()
        services.planifier(intervention=i1, salle=self.salle, debut=_dt(1, 8, 0),
                           duree_estimee_min=60)
        i2 = self._intervention(patient=Patient.objects.create(nom="Zo", prenom="P", sexe="M"))
        # i1 : 08:00–09:00 + 30 min nettoyage => salle occupée jusqu'à 09:30
        with self.assertRaises(services.ErreurBloc):
            services.planifier(intervention=i2, salle=self.salle, debut=_dt(1, 9, 0),
                               duree_estimee_min=60)

    def test_creneau_apres_nettoyage_accepte(self):
        i1 = self._intervention()
        services.planifier(intervention=i1, salle=self.salle, debut=_dt(1, 8, 0),
                           duree_estimee_min=60)
        i2 = self._intervention(patient=Patient.objects.create(nom="Zo", prenom="P", sexe="M"))
        res = services.planifier(intervention=i2, salle=self.salle, debut=_dt(1, 9, 30),
                                 duree_estimee_min=60)
        self.assertEqual(res["intervention"].statut, Intervention.Statut.PLANIFIEE)

    def test_checklist_creee_a_la_planification(self):
        i = self._intervention()
        services.planifier(intervention=i, salle=self.salle, debut=_dt(1), duree_estimee_min=60)
        self.assertEqual(i.checklist.count(), 3)


class ExtremeUrgenceTests(BaseBloc):
    def test_extreme_urgence_reporte_les_programmees_en_conflit(self):
        prog = self._intervention()
        services.planifier(intervention=prog, salle=self.salle, debut=_dt(1, 8, 0),
                           duree_estimee_min=60)
        urg = self._intervention(urgence=Intervention.Urgence.EXTREME_URGENCE,
                                 patient=Patient.objects.create(nom="Ur", prenom="G", sexe="M"))
        res = services.planifier(intervention=urg, salle=self.salle, debut=_dt(1, 8, 0),
                                 duree_estimee_min=60, forcer=True)
        prog.refresh_from_db()
        self.assertEqual(prog.statut, Intervention.Statut.REPORTEE)
        self.assertIn("extrême urgence", prog.motif_annulation)
        self.assertEqual(len(res["reports"]), 1)

    def test_conflit_avec_une_urgente_exige_un_arbitrage_manuel(self):
        autre = self._intervention(urgence=Intervention.Urgence.URGENTE)
        services.planifier(intervention=autre, salle=self.salle, debut=_dt(1, 8, 0),
                           duree_estimee_min=60)
        urg = self._intervention(urgence=Intervention.Urgence.EXTREME_URGENCE,
                                 patient=Patient.objects.create(nom="Ur", prenom="G", sexe="M"))
        with self.assertRaises(services.ErreurBloc):
            services.planifier(intervention=urg, salle=self.salle, debut=_dt(1, 8, 0),
                               duree_estimee_min=60, forcer=True)


class ConflitEquipeTests(BaseBloc):
    def test_membre_deja_engage_sur_creneau_chevauchant(self):
        i1 = self._intervention()
        services.planifier(intervention=i1, salle=self.salle, debut=_dt(1, 8, 0),
                           duree_estimee_min=60)
        ibode = Utilisateur.objects.create_user("ib", password="x",
                                                role=Utilisateur.Role.IBODE)
        services.ajouter_membre(intervention=i1, utilisateur=ibode, role="IBODE")

        salle2 = SalleOperatoire.objects.create(nom="Salle 2")
        i2 = self._intervention(patient=Patient.objects.create(nom="Zo", prenom="P", sexe="M"))
        services.planifier(intervention=i2, salle=salle2, debut=_dt(1, 8, 30),
                           duree_estimee_min=60)
        with self.assertRaises(services.ErreurBloc):
            services.ajouter_membre(intervention=i2, utilisateur=ibode, role="IBODE")

    def test_forcer_ignore_le_conflit_equipe(self):
        i1 = self._intervention()
        services.planifier(intervention=i1, salle=self.salle, debut=_dt(1, 8, 0),
                           duree_estimee_min=60)
        anesth = Utilisateur.objects.create_user("an", password="x",
                                                 role=Utilisateur.Role.ANESTHESISTE)
        services.ajouter_membre(intervention=i1, utilisateur=anesth, role="ANESTHESISTE")
        salle2 = SalleOperatoire.objects.create(nom="Salle 2")
        i2 = self._intervention(patient=Patient.objects.create(nom="Zo", prenom="P", sexe="M"))
        services.planifier(intervention=i2, salle=salle2, debut=_dt(1, 8, 30),
                           duree_estimee_min=60)
        m = services.ajouter_membre(intervention=i2, utilisateur=anesth,
                                    role="ANESTHESISTE", forcer=True)
        self.assertIsInstance(m, MembreEquipe)


class ChecklistEtPeroperatoireTests(BaseBloc):
    def setUp(self):
        super().setUp()
        self.i = self._intervention()
        services.planifier(intervention=self.i, salle=self.salle, debut=_dt(0, 8, 0),
                           duree_estimee_min=60)
        self.i.faisabilite_anesthesique_validee = True
        self.i.save()

    def test_checklist_doit_respecter_l_ordre_des_temps(self):
        with self.assertRaises(services.ErreurBloc):
            services.valider_etape(intervention=self.i,
                                   temps=EtapeChecklist.Temps.AVANT_INCISION,
                                   utilisateur=self.chir)

    def test_entree_salle_exige_checklist_induction(self):
        with self.assertRaises(services.ErreurBloc):
            services.entree_en_salle(intervention=self.i, par=self.chir)
        services.valider_etape(intervention=self.i,
                               temps=EtapeChecklist.Temps.AVANT_INDUCTION,
                               utilisateur=self.chir)
        services.entree_en_salle(intervention=self.i, par=self.chir)
        self.i.refresh_from_db()
        self.assertEqual(self.i.statut, Intervention.Statut.EN_COURS)
        self.assertIsNotNone(self.i.heure_entree_salle)

    def test_terminer_exige_checklist_sortie(self):
        for temps in (EtapeChecklist.Temps.AVANT_INDUCTION,
                      EtapeChecklist.Temps.AVANT_INCISION):
            services.valider_etape(intervention=self.i, temps=temps, utilisateur=self.chir)
        services.entree_en_salle(intervention=self.i, par=self.chir)
        with self.assertRaises(services.ErreurBloc):
            services.terminer(intervention=self.i, par=self.chir)
        services.valider_etape(intervention=self.i,
                               temps=EtapeChecklist.Temps.AVANT_SORTIE_SALLE,
                               utilisateur=self.chir)
        services.terminer(intervention=self.i, par=self.chir)
        self.i.refresh_from_db()
        self.assertEqual(self.i.statut, Intervention.Statut.TERMINEE)
        self.assertIsNotNone(self.i.heure_sortie_salle)

    def test_salle_occupee_pendant_intervention(self):
        for temps in (EtapeChecklist.Temps.AVANT_INDUCTION,):
            services.valider_etape(intervention=self.i, temps=temps, utilisateur=self.chir)
        services.entree_en_salle(intervention=self.i, par=self.chir)
        self.assertEqual(self.salle.statut_effectif,
                         SalleOperatoire.StatutEffectif.OCCUPEE)


class AnnulationTests(BaseBloc):
    def test_annulation_exige_un_motif(self):
        i = self._intervention()
        with self.assertRaises(services.ErreurBloc):
            services.annuler(intervention=i, motif="  ", par=self.chir)

    def test_report_libere_la_salle_et_le_creneau(self):
        i = self._intervention()
        services.planifier(intervention=i, salle=self.salle, debut=_dt(1), duree_estimee_min=60)
        services.annuler(intervention=i, motif="Patient non à jeun", par=self.chir,
                         reporter=True)
        i.refresh_from_db()
        self.assertEqual(i.statut, Intervention.Statut.REPORTEE)
        self.assertIsNone(i.salle)
        self.assertIsNone(i.date_heure_debut_prevue)


class AccesBlocTests(BaseBloc):
    def test_chirurgien_demande_infirmier_non(self):
        chir = Utilisateur.objects.get(pk=self.chir.pk)
        inf = Utilisateur.objects.create_user("inf", password="x",
                                              role=Utilisateur.Role.INFIRMIER)
        inf = Utilisateur.objects.get(pk=inf.pk)
        self.assertTrue(chir.has_perm("bloc_operatoire.add_intervention"))
        self.assertFalse(inf.has_perm("bloc_operatoire.add_intervention"))

    def test_anesthesiste_valide_faisabilite(self):
        an = Utilisateur.objects.create_user("an", password="x",
                                             role=Utilisateur.Role.ANESTHESISTE)
        an = Utilisateur.objects.get(pk=an.pk)
        self.assertTrue(an.has_perm("bloc_operatoire.change_intervention"))
        self.assertTrue(an.has_perm("bloc_operatoire.change_etapechecklist"))

    def test_agent_sterilisation_gere_le_materiel_pas_les_interventions(self):
        st = Utilisateur.objects.create_user("st", password="x",
                                             role=Utilisateur.Role.AGENT_STERILISATION)
        st = Utilisateur.objects.get(pk=st.pk)
        self.assertTrue(st.has_perm("bloc_operatoire.change_materielbloc"))
        self.assertFalse(st.has_perm("bloc_operatoire.add_intervention"))

    def test_planning_accessible_au_cadre_de_bloc(self):
        Utilisateur.objects.create_user("cadre", password="x",
                                        role=Utilisateur.Role.CADRE_BLOC)
        self.client.login(username="cadre", password="x")
        r = self.client.get(reverse("bloc_operatoire:planning"))
        self.assertEqual(r.status_code, 200)
