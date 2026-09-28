"""Recale le compteur d'identifiants de ParametresSysteme.

L'ancien code forçait ``pk = 1`` (singleton) : les lignes existantes ont été
insérées avec un identifiant explicite, sans faire avancer la séquence
PostgreSQL. Avec un paramétrage par établissement, le premier ajout suivant
entrerait en collision avec l'identifiant 1.
"""

from django.core.management.color import no_style
from django.db import migrations


def recaler(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return
    Modele = apps.get_model("core", "ParametresSysteme")
    with connection.cursor() as curseur:
        for sql in connection.ops.sequence_reset_sql(no_style(), [Modele]):
            curseur.execute(sql)


class Migration(migrations.Migration):
    dependencies = [("core", "0007_plans_par_defaut")]
    operations = [migrations.RunPython(recaler, migrations.RunPython.noop)]
