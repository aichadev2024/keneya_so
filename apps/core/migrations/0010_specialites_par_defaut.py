from django.db import migrations

SPECIALITES = [
    ("ophtalmologie", "Ophtalmologie", 10),
    ("pediatrie", "Pédiatrie", 20),
    ("odontologie", "Odontologie (dentisterie)", 30),
]


def creer(apps, schema_editor):
    Specialite = apps.get_model("core", "Specialite")
    for code, nom, ordre in SPECIALITES:
        Specialite.objects.get_or_create(code=code, defaults={"nom": nom, "ordre": ordre})


class Migration(migrations.Migration):
    dependencies = [("core", "0009_specialite_etablissement_specialites")]
    operations = [migrations.RunPython(creer, migrations.RunPython.noop)]
