"""
Isolation multi-établissements (SaaS) : un établissement ne voit jamais les
données d'un autre.

Principe : chaque requête HTTP s'exécute dans un « contexte d'établissement »
posé par ``EtablissementMiddleware`` à partir de l'utilisateur connecté. Les
modèles rattachés à un établissement (``TenantOwnedModel``) exposent un
gestionnaire ``objects`` qui filtre automatiquement sur ce contexte — un oubli
de filtre dans une vue ne peut donc pas provoquer de fuite entre hôpitaux.

Valeurs possibles du contexte :

- un ``int``      : identifiant de l'établissement de l'utilisateur ;
- ``AUCUN``       : visiteur anonyme ou compte sans établissement — rien de visible ;
- ``TOUS``        : super-administrateur de la plateforme — aucune restriction ;
- ``HORS_REQUETE``: code exécuté hors requête HTTP (commande, test) — aucune
  restriction, et les créations sont rattachées à l'établissement par défaut.
"""

from __future__ import annotations

from contextvars import ContextVar

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models.sql.query import Query


class _Sentinelle:
    def __init__(self, nom: str):
        self.nom = nom

    def __repr__(self) -> str:
        return f"<{self.nom}>"


AUCUN = _Sentinelle("AUCUN")
TOUS = _Sentinelle("TOUS")
HORS_REQUETE = _Sentinelle("HORS_REQUETE")

_courant: ContextVar = ContextVar("etablissement_courant", default=HORS_REQUETE)


def contexte_courant():
    return _courant.get()


def activer(valeur):
    """Pose le contexte ; renvoie un jeton à passer à ``desactiver``."""
    if hasattr(valeur, "pk"):
        valeur = valeur.pk
    return _courant.set(valeur)


def desactiver(jeton) -> None:
    _courant.reset(jeton)


class pour_etablissement:
    """Gestionnaire de contexte : ``with pour_etablissement(etab): ...``."""

    def __init__(self, valeur):
        self.valeur = valeur

    def __enter__(self):
        self.jeton = activer(self.valeur)

    def __exit__(self, *exc):
        desactiver(self.jeton)


def etablissement_pour_creation() -> int:
    """Établissement auquel rattacher un nouvel objet créé sans établissement explicite."""
    valeur = _courant.get()
    if isinstance(valeur, int):
        return valeur
    if valeur is HORS_REQUETE:
        from .models import Etablissement

        return Etablissement.defaut().pk
    raise ImproperlyConfigured(
        "Impossible de créer cet objet : aucun établissement actif dans le contexte "
        "courant (compte sans établissement ou super-administrateur de la plateforme)."
    )


class TenantQuery(Query):
    """Requête SQL qui applique le filtre d'établissement AU MOMENT DE L'EXÉCUTION.

    Filtrer à la création du queryset ne suffit pas : un ``queryset =
    Modele.objects.all()`` écrit au niveau d'une classe (vue DRF, champ de
    formulaire) est construit à l'import, avant qu'aucun établissement ne soit
    connu. En appliquant le filtre à la compilation SQL, chaque exécution est
    filtrée selon la requête HTTP en cours, quelle que soit l'origine du queryset.
    """

    def _avec_portee(self):
        valeur = _courant.get()
        if valeur is AUCUN:
            q = self.clone()
            q.set_empty()
            return q
        if isinstance(valeur, int):
            q = self.clone()
            q.add_q(models.Q(etablissement_id=valeur))
            return q
        return self

    def get_compiler(self, using=None, connection=None, elide_empty=True):
        return super(TenantQuery, self._avec_portee()).get_compiler(
            using, connection, elide_empty)


class TenantQuerySet(models.QuerySet):
    """QuerySet filtré par établissement à l'exécution (voir ``TenantQuery``)."""

    def __init__(self, model=None, query=None, using=None, hints=None):
        if query is None and model is not None:
            query = TenantQuery(model)
        super().__init__(model=model, query=query, using=using, hints=hints)

    def _filtre(self):
        qs = self._chain()
        qs.query = self.query._avec_portee()
        return qs

    def update(self, **kwargs):
        # update()/delete() changent la classe de la requête (UpdateQuery/DeleteQuery),
        # qui échappe alors à TenantQuery : on applique le filtre avant.
        return super(TenantQuerySet, self._filtre()).update(**kwargs)

    def delete(self):
        return super(TenantQuerySet, self._filtre()).delete()


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    """Gestionnaire par défaut des modèles rattachés à un établissement."""


def gestionnaire_pour(queryset_class):
    """Gestionnaire filtré construit sur un queryset métier (ex. ``PatientQuerySet``)."""
    base = type(
        f"{queryset_class.__name__}Tenant", (queryset_class, TenantQuerySet), {}
    )
    return TenantManager.from_queryset(base)()


class EtablissementMiddleware:
    """Pose le contexte d'établissement de chaque requête (après l'authentification)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        utilisateur = getattr(request, "user", None)
        if utilisateur is not None and utilisateur.is_authenticated:
            if utilisateur.etablissement_id:
                valeur = utilisateur.etablissement_id
            elif utilisateur.is_superuser:
                valeur = TOUS
            else:
                valeur = AUCUN
        else:
            valeur = AUCUN
        jeton = _courant.set(valeur)
        try:
            return self.get_response(request)
        finally:
            _courant.reset(jeton)
