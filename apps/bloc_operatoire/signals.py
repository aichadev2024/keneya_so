"""Création automatique de la checklist de sécurité dès qu'une intervention est planifiée."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import EtapeChecklist, Intervention


@receiver(post_save, sender=Intervention)
def creer_checklist(sender, instance: Intervention, **kwargs):
    if instance.statut not in Intervention.STATUTS_ACTIFS:
        return
    if instance.checklist.exists():
        return
    EtapeChecklist.objects.bulk_create([
        EtapeChecklist(intervention=instance, temps=temps)
        for temps in EtapeChecklist.ORDRE
    ])
