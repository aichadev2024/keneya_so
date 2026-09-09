"""Création automatique du dossier médical à l'enregistrement d'un patient."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import DossierMedical, Patient


@receiver(post_save, sender=Patient)
def creer_dossier_medical(sender, instance: Patient, created: bool, **kwargs):
    if created:
        DossierMedical.objects.get_or_create(patient=instance)
