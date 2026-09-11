"""
Applique les dictionnaires de traduction (scripts/i18n_translations_*.py) aux
fichiers .po, puis rapporte la couverture. N'écrase jamais une traduction déjà
saisie manuellement dans le .po (fusion non destructive).

Usage :
    python scripts/i18n_apply.py en
    python scripts/i18n_apply.py ar
    python scripts/i18n_apply.py en ar
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import polib

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))


def appliquer(langue: str) -> None:
    module = importlib.import_module(f"i18n_translations_{langue}")
    traductions = module.TRADUCTIONS
    traductions_pluriel = getattr(module, "TRADUCTIONS_PLURIEL", {})

    chemin = BASE_DIR / "locale" / langue / "LC_MESSAGES" / "django.po"
    po = polib.pofile(str(chemin))

    appliquees = 0
    for entry in po:
        if entry.msgid_plural:
            formes = traductions_pluriel.get((entry.msgid, entry.msgid_plural))
            if formes and not entry.translated():
                entry.msgstr_plural = {i: forme for i, forme in enumerate(formes)}
                appliquees += 1
        else:
            valeur = traductions.get(entry.msgid)
            if valeur and not entry.translated():
                entry.msgstr = valeur
                appliquees += 1

    po.save(str(chemin))

    total = len(po)
    traduites = len([e for e in po if e.translated()])
    manquantes = [e.msgid for e in po if not e.translated()]
    print(f"{langue} : {appliquees} nouvelle(s) traduction(s) appliquée(s) — "
          f"{traduites}/{total} au total.")
    if manquantes:
        print(f"  {len(manquantes)} chaîne(s) restant à traduire, ex. :")
        for m in manquantes[:10]:
            print(f"    - {m!r}")


def main(argv):
    langues = argv or ["en", "ar"]
    for langue in langues:
        appliquer(langue)


if __name__ == "__main__":
    main(sys.argv[1:])
