"""Inscription d'un nouvel hôpital sur la plateforme (SaaS) — CDC 2.2."""

from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.text import slugify

from .models import Etablissement, HistoriqueAction, ParametresSysteme, Plan
from .referentiels import initialiser_referentiels
from .tenancy import pour_etablissement

Utilisateur = get_user_model()


def _slug_unique(nom: str) -> str:
    base = slugify(nom)[:50] or "hopital"
    slug, n = base, 2
    while Etablissement.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


@transaction.atomic
def inscrire_hopital(*, nom_hopital: str, prenom: str, nom: str, email: str,
                     username: str, password: str, adresse_ip: str | None = None):
    """Crée l'établissement (en période d'essai) et son premier administrateur."""
    etab = Etablissement.objects.create(
        nom=nom_hopital,
        slug=_slug_unique(nom_hopital),
        statut=Etablissement.Statut.ESSAI,
        essai_jusqu_au=date.today() + timedelta(days=settings.ESSAI_DUREE_JOURS),
        plan=Plan.objects.filter(code="essai").first(),
    )
    with pour_etablissement(etab):
        ParametresSysteme.objects.create(nom_etablissement=nom_hopital, email=email)
        initialiser_referentiels()
        admin = Utilisateur(
            username=username, first_name=prenom, last_name=nom, email=email,
            role=Utilisateur.Role.ADMIN, etablissement=etab,
        )
        admin.set_password(password)
        admin.save()
        HistoriqueAction.enregistrer(
            utilisateur=admin, action=HistoriqueAction.Action.CREATION, objet=etab,
            description=f"Inscription de l'hôpital « {nom_hopital} » (essai {settings.ESSAI_DUREE_JOURS} j)",
            adresse_ip=adresse_ip,
        )
    return etab, admin
