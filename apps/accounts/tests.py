"""Tests des règles de gestion critiques du contrôle d'accès (CDC 7.5)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import groupe_pour_role
from .roles import PERMISSIONS_PAR_ROLE

Utilisateur = get_user_model()


class GroupesDeRolesTests(TestCase):
    def test_un_groupe_par_role_est_cree_par_post_migrate(self):
        for role in PERMISSIONS_PAR_ROLE:
            self.assertTrue(
                Group.objects.filter(name=groupe_pour_role(role)).exists(),
                msg=f"Groupe manquant pour le rôle {role}",
            )

    def test_admin_possede_toutes_les_permissions_patients(self):
        groupe = Group.objects.get(name=groupe_pour_role(Utilisateur.Role.ADMIN))
        codenames = set(
            groupe.permissions.values_list("codename", flat=True)
        )
        for attendu in ("add_patient", "change_patient", "delete_patient", "view_patient"):
            self.assertIn(attendu, codenames)

    def test_agent_sterilisation_n_a_aucune_permission_patient(self):
        groupe = Group.objects.get(
            name=groupe_pour_role(Utilisateur.Role.AGENT_STERILISATION)
        )
        self.assertFalse(
            groupe.permissions.filter(content_type__app_label="patients").exists()
        )


class AffectationGroupeUtilisateurTests(TestCase):
    def test_changement_de_role_reaffecte_le_groupe(self):
        u = Utilisateur.objects.create_user("awa", password="x", role=Utilisateur.Role.INFIRMIER)
        self.assertEqual(
            list(u.groups.values_list("name", flat=True)),
            [groupe_pour_role(Utilisateur.Role.INFIRMIER)],
        )

        u.role = Utilisateur.Role.MEDECIN
        u.save()
        self.assertEqual(
            list(u.groups.values_list("name", flat=True)),
            [groupe_pour_role(Utilisateur.Role.MEDECIN)],
        )

    def test_agent_accueil_peut_creer_un_patient_pas_un_infirmier(self):
        accueil = Utilisateur.objects.create_user(
            "acc", password="x", role=Utilisateur.Role.AGENT_ACCUEIL
        )
        infirmier = Utilisateur.objects.create_user(
            "inf", password="x", role=Utilisateur.Role.INFIRMIER
        )
        # Rechargement pour recalculer le cache de permissions.
        accueil = Utilisateur.objects.get(pk=accueil.pk)
        infirmier = Utilisateur.objects.get(pk=infirmier.pk)
        self.assertTrue(accueil.has_perm("patients.add_patient"))
        self.assertFalse(infirmier.has_perm("patients.add_patient"))
        self.assertTrue(infirmier.has_perm("patients.view_patient"))

    def test_role_admin_est_staff(self):
        u = Utilisateur.objects.create_user("boss", password="x", role=Utilisateur.Role.ADMIN)
        u = Utilisateur.objects.get(pk=u.pk)
        self.assertTrue(u.is_staff)


@override_settings(SETUP_TOKEN="jeton-de-test")
class PremiereConfigurationTests(TestCase):
    """Création du tout premier compte administrateur (bootstrap public, CDC 7.1)."""

    def setUp(self):
        self.url = reverse("accounts:premiere_configuration")

    def _donnees(self, **overrides):
        d = {
            "username": "premier_admin", "first_name": "Awa", "last_name": "Diarra",
            "email": "awa@example.com", "password1": "UnMotDePasseSolide2026!",
            "password2": "UnMotDePasseSolide2026!", "jeton": "jeton-de-test",
        }
        d.update(overrides)
        return d

    @override_settings(SETUP_TOKEN="")
    def test_desactivee_sans_jeton_configure(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_desactivee_si_un_superutilisateur_existe_deja(self):
        Utilisateur.objects.create_superuser("dej_admin", password="x")
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_accessible_tant_qu_aucun_superutilisateur_n_existe(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_jeton_incorrect_rejete(self):
        reponse = self.client.post(self.url, self._donnees(jeton="mauvais-jeton"))
        self.assertEqual(reponse.status_code, 200)  # réaffiche le formulaire, pas de redirection
        self.assertFalse(Utilisateur.objects.filter(username="premier_admin").exists())

    def test_creation_reussie_avec_le_bon_jeton(self):
        reponse = self.client.post(self.url, self._donnees())
        self.assertRedirects(reponse, reverse("accounts:login"))
        u = Utilisateur.objects.get(username="premier_admin")
        self.assertTrue(u.is_superuser)
        self.assertTrue(u.is_staff)
        self.assertEqual(u.role, Utilisateur.Role.ADMIN)

    def test_deuxieme_creation_bloquee_apres_la_premiere(self):
        self.client.post(self.url, self._donnees())
        # La page est maintenant verrouillée : un deuxième essai est refusé (404),
        # même avec le bon jeton.
        self.assertEqual(self.client.get(self.url).status_code, 404)
