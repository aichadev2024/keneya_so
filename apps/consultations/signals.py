"""Création de la dispensation dès qu'une ordonnance est transmise (CDC 4.3 -> 4.5)."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Ordonnance


@receiver(post_save, sender=Ordonnance)
def ouvrir_dispensation(sender, instance: Ordonnance, **kwargs):
    if instance.statut != Ordonnance.Statut.TRANSMISE:
        return
    from apps.pharmacie.models import Dispensation

    Dispensation.objects.get_or_create(ordonnance=instance)
