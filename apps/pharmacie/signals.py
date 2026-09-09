"""Traçabilité automatique du stock à la création d'un lot."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import LotMedicament, MouvementStock


@receiver(post_save, sender=LotMedicament)
def journaliser_entree_lot(sender, instance: LotMedicament, created: bool, **kwargs):
    """Un lot nouvellement créé correspond à une entrée de stock (CDC 4.5)."""
    if not created:
        return
    MouvementStock.objects.create(
        medicament=instance.medicament,
        lot=instance,
        type=MouvementStock.Type.ENTREE,
        quantite=instance.quantite_initiale,
        motif=f"Réception lot {instance.numero_lot}",
    )
