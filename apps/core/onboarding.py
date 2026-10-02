"""Inscription d'un nouvel hôpital sur la plateforme (SaaS) — CDC 2.2."""

from __future__ import annotations

import secrets
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import slugify

from .models import Etablissement, HistoriqueAction, ParametresSysteme, Plan
from .referentiels import initialiser_referentiels
from .tenancy import pour_etablissement

Utilisateur = get_user_model()


def slug_unique(nom: str) -> str:
    base = slugify(nom)[:50] or "hopital"
    slug, n = base, 2
    while Etablissement.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def initialiser_etablissement(etab, *, prenom, nom, email, username, password=None,
                              adresse_ip=None, utilisateur_journal=None, description=""):
    """Prépare un établissement neuf : paramètres, référentiels de départ, premier administrateur.

    Sans mot de passe, le compte reçoit un mot de passe aléatoire inconnu de tous :
    l'administrateur choisira le sien via le lien d'invitation envoyé par e-mail.
    """
    with pour_etablissement(etab):
        ParametresSysteme.objects.create(nom_etablissement=etab.nom, email=email)
        initialiser_referentiels()
        admin = Utilisateur(
            username=username, first_name=prenom, last_name=nom, email=email,
            role=Utilisateur.Role.ADMIN, etablissement=etab,
        )
        admin.set_password(password or secrets.token_urlsafe(32))
        admin.save()
        HistoriqueAction.enregistrer(
            utilisateur=utilisateur_journal or admin, action=HistoriqueAction.Action.CREATION,
            objet=etab,
            description=description or f"Création de l'hôpital « {etab.nom} »",
            adresse_ip=adresse_ip,
        )
    return admin


@transaction.atomic
def inscrire_hopital(*, nom_hopital: str, prenom: str, nom: str, email: str,
                     username: str, password: str, adresse_ip: str | None = None):
    """Inscription libre-service : crée l'établissement (en essai) et son premier administrateur."""
    etab = Etablissement.objects.create(
        nom=nom_hopital,
        slug=slug_unique(nom_hopital),
        statut=Etablissement.Statut.ESSAI,
        essai_jusqu_au=date.today() + timedelta(days=settings.ESSAI_DUREE_JOURS),
        plan=Plan.objects.filter(code="essai").first(),
    )
    admin = initialiser_etablissement(
        etab, prenom=prenom, nom=nom, email=email, username=username, password=password,
        adresse_ip=adresse_ip,
        description=f"Inscription de l'hôpital « {nom_hopital} » (essai {settings.ESSAI_DUREE_JOURS} j)",
    )
    return etab, admin


@transaction.atomic
def creer_hopital_client(form, *, request):
    """Crée un hôpital à l'initiative du propriétaire, à partir d'un ``CreationHopitalForm``
    déjà validé (``forms.is_valid()``) : établissement + premier administrateur invité par
    e-mail. Utilisé à la fois par l'admin Django et par la console propriétaire.

    Renvoie ``(etablissement, administrateur, invitation_envoyee)``.
    """
    from apps.accounts.invitations import tenter_invitation

    etab = form.save(commit=False)
    etab.slug = slug_unique(etab.nom)
    if etab.statut == Etablissement.Statut.ESSAI and not etab.essai_jusqu_au:
        etab.essai_jusqu_au = date.today() + timedelta(days=settings.ESSAI_DUREE_JOURS)
    etab.save()
    form.save_m2m()

    d = form.cleaned_data
    admin = initialiser_etablissement(
        etab, prenom=d["admin_prenom"], nom=d["admin_nom"], email=d["admin_email"],
        username=d["admin_username"], utilisateur_journal=request.user,
        description=f"Hôpital « {etab.nom} » créé par le propriétaire de la plateforme",
    )
    invitation_envoyee = tenter_invitation(admin, request)
    return etab, admin, invitation_envoyee
