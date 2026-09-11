"""
Compile les catalogues locale/<lang>/LC_MESSAGES/django.po en .mo, en pur
Python (``polib``), sans dépendre de ``msgfmt`` (GNU gettext indisponible sur
cette machine — voir ``scripts/i18n_extract.py``).

Usage :
    python scripts/i18n_compile.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import polib

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALE_DIR = BASE_DIR / "locale"


def main():
    po_files = sorted(LOCALE_DIR.glob("*/LC_MESSAGES/django.po"))
    if not po_files:
        print("Aucun fichier .po trouvé. Lancer d'abord scripts/i18n_extract.py.")
        return 1

    for po_path in po_files:
        po = polib.pofile(str(po_path))
        mo_path = po_path.with_suffix(".mo")
        po.save_as_mofile(str(mo_path))
        traduites = len([e for e in po if e.translated()])
        total = len(po)
        langue = po_path.parent.parent.name
        print(f"  {langue} : {mo_path.relative_to(BASE_DIR)} "
              f"({traduites}/{total} traduites)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
