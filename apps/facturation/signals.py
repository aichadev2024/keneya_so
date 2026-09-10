"""
Génération automatique des factures à partir des actes réalisés (CDC 4.8).

Chaque acte, en atteignant son état terminal, déclenche la création d'une
facture **en brouillon** (le comptable l'émet ensuite). Désactivable via
``FACTURATION_AUTO = False``.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from . import services

logger = logging.getLogger("keneya.facturation")


def _auto() -> bool:
    return getattr(settings, "FACTURATION_AUTO", True)


def _tenter(fn, acte):
    try:
        facture = fn(acte)
        if facture:
            logger.info("Facture %s générée pour %s", facture.reference, acte)
    except services.ErreurFacturation as exc:
        logger.warning("Facturation auto ignorée pour %s : %s", acte, exc)


@receiver(post_save, sender="consultations.Consultation")
def facturer_consultation(sender, instance, **kwargs):
    if _auto() and instance.statut == instance.Statut.CLOTUREE:
        _tenter(lambda a: services.facturer_consultation(a), instance)


@receiver(post_save, sender="hospitalisation.Hospitalisation")
def facturer_hospitalisation(sender, instance, **kwargs):
    if _auto() and instance.statut == instance.Statut.SORTIE:
        _tenter(lambda a: services.facturer_hospitalisation(a), instance)


@receiver(post_save, sender="bloc_operatoire.Intervention")
def facturer_intervention(sender, instance, **kwargs):
    if _auto() and instance.statut == instance.Statut.TERMINEE:
        _tenter(lambda a: services.facturer_intervention(a), instance)


@receiver(post_save, sender="pharmacie.Dispensation")
def facturer_dispensation(sender, instance, **kwargs):
    etats = {instance.Statut.COMPLETE, instance.Statut.PARTIELLE}
    if _auto() and instance.statut in etats:
        _tenter(lambda a: services.facturer_dispensation(a), instance)
