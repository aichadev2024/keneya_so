"""Plans d'abonnement de départ (modifiables ensuite depuis la console propriétaire)."""

from django.db import migrations

PLANS = [
    # code, nom, prix mensuel (FCFA, à définir), utilisateurs maximum
    ("essai", "Essai gratuit", 0, 10),
    ("essentiel", "Essentiel", None, 15),
    ("standard", "Standard", None, 40),
    ("premium", "Premium", None, None),
]


def creer_plans(apps, schema_editor):
    Plan = apps.get_model("core", "Plan")
    for code, nom, prix, max_users in PLANS:
        Plan.objects.get_or_create(
            code=code, defaults={"nom": nom, "prix_mensuel": prix, "max_utilisateurs": max_users,
                                 "actif": code != "essai"})


class Migration(migrations.Migration):
    dependencies = [("core", "0006_plans")]
    operations = [migrations.RunPython(creer_plans, migrations.RunPython.noop)]
