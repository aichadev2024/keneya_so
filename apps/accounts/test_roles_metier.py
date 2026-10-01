"""Les droits de chaque rôle respectent le cahier des charges métier de l'hôpital."""

from django.test import TestCase

from .models import Utilisateur
from .roles import PERMISSIONS_PAR_ROLE, roles_avec_permission

Role = Utilisateur.Role

CONSULTER = ["consultations.add_consultation", "consultations.add_ordonnance",
             "laboratoire.add_demandeexamen", "laboratoire.view_resultat"]


def _a(role, perm):
    return role in roles_avec_permission(perm)


class RolesMetierTests(TestCase):
    def test_agent_accueil_cumule_accueil_facturation_pharmacie_comptabilite(self):
        for perm in ["patients.add_patient", "facturation.add_facture", "facturation.add_paiement",
                     "assurances.add_bordereauassurance", "pharmacie.add_dispensation",
                     "pharmacie.add_mouvementstock"]:
            self.assertTrue(_a(Role.AGENT_ACCUEIL, perm), perm)
        self.assertFalse(_a(Role.AGENT_ACCUEIL, "consultations.add_consultation"))

    def test_medecin(self):
        for perm in CONSULTER + ["patients.change_dossiermedical",
                                 "hospitalisation.add_hospitalisation",
                                 "bloc_operatoire.add_intervention"]:
            self.assertTrue(_a(Role.MEDECIN, perm), perm)

    def test_chirurgien(self):
        for perm in CONSULTER + ["patients.change_dossiermedical",
                                 "hospitalisation.add_hospitalisation",
                                 "bloc_operatoire.add_intervention",
                                 "bloc_operatoire.add_compterenduoperatoire",
                                 "hospitalisation.add_notesuivi"]:
            self.assertTrue(_a(Role.CHIRURGIEN, perm), perm)

    def test_infirmier_consulte_prescrit_et_soigne(self):
        for perm in CONSULTER + ["hospitalisation.add_notesuivi", "consultations.add_constantes"]:
            self.assertTrue(_a(Role.INFIRMIER, perm), perm)
        self.assertFalse(_a(Role.INFIRMIER, "hospitalisation.add_hospitalisation"))

    def test_anesthesiste_consulte_prescrit_et_participe_aux_interventions(self):
        for perm in CONSULTER + ["bloc_operatoire.view_intervention",
                                 "bloc_operatoire.change_intervention",
                                 "bloc_operatoire.add_etapechecklist"]:
            self.assertTrue(_a(Role.ANESTHESISTE, perm), perm)

    def test_sage_femme_peut_hospitaliser(self):
        for perm in CONSULTER + ["hospitalisation.add_hospitalisation",
                                 "maternite.add_dossiergrossesse"]:
            self.assertTrue(_a(Role.SAGE_FEMME, perm), perm)

    def test_laborantin_et_radiologue(self):
        for role in (Role.LABORANTIN, Role.RADIOLOGUE):
            for perm in ["laboratoire.add_resultat", "laboratoire.change_resultat",
                         "laboratoire.add_typeexamen"]:
                self.assertTrue(_a(role, perm), (role, perm))
            self.assertFalse(_a(role, "consultations.add_ordonnance"))

    def test_tous_les_roles_ont_une_entree(self):
        for role in Role.values:
            self.assertIn(role, PERMISSIONS_PAR_ROLE)
