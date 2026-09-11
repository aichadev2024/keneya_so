"""
Extraction des chaînes traduisibles sans les outils GNU gettext (CDC 4.11).

Cet environnement de développement ne dispose pas de `xgettext`/`msgfmt`
(indisponibles sur cette machine Windows, et leur installation nécessite des
droits d'administration). Ce script est un **substitut minimal** à
`django-admin makemessages`, spécifique aux formes utilisées dans ce projet :

- Python  : appels ``_("...")`` / ``_('...')`` (alias de ``gettext_lazy``).
- Gabarits : ``{% translate "..." %}`` et
  ``{% blocktranslate [with ...] [count x=y] %}...{% endblocktranslate %}``
  (avec gestion du pluriel via ``{% plural %}``).

Il régénère `locale/<lang>/LC_MESSAGES/django.po` pour chaque langue listée,
en conservant les traductions déjà saisies (fusion par msgid), puis
`scripts/i18n_compile.py` compile les .po en .mo en pur Python (``polib``,
sans ``msgfmt``).

Si l'environnement de déploiement dispose de GNU gettext, préférer les
commandes standard : ``manage.py makemessages`` / ``manage.py compilemessages``.

Usage :
    python scripts/i18n_extract.py
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALE_DIR = BASE_DIR / "locale"
LANGUES = ["en", "ar", "bm", "ff", "snk"]  # fr = langue source, pas de .po nécessaire

EXCLURE = {".venv", "migrations", "node_modules", "staticfiles", "media", "locale"}

PY_STR = r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\''
RE_PY_GETTEXT = re.compile(r"(?<![\w.])_\(\s*(" + PY_STR + r")\s*\)")
RE_TPL_TRANSLATE = re.compile(
    r"{%-?\s*translate\s+(" + PY_STR + r")(?:\s+as\s+\w+)?\s*-?%}"
)
RE_TPL_BLOCK = re.compile(
    r"{%-?\s*blocktranslate([^%}]*)-?%}(.*?){%-?\s*endblocktranslate\s*-?%}",
    re.DOTALL,
)
RE_COUNT_VAR = re.compile(r"\bcount\s+(\w+)=")
RE_VAR_REF = re.compile(r"{{\s*(\w+)\s*}}")
RE_PLURAL_TAG = re.compile(r"{%-?\s*plural\s*-?%}")


def _strip_py_quotes(raw: str) -> str:
    """Dévalue un littéral chaîne Python capturé tel quel (gère \\", \\n, unicode…)."""
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return raw[1:-1]


@dataclass
class Entree:
    msgid: str
    msgid_plural: str | None = None
    occurrences: list[tuple[str, int]] = field(default_factory=list)


def _rel(path: Path) -> str:
    return str(path.relative_to(BASE_DIR)).replace("\\", "/")


def _fichiers(motif: str):
    for p in BASE_DIR.rglob(motif):
        if any(part in EXCLURE for part in p.parts):
            continue
        yield p


def extraire_python(entrees: dict) -> None:
    for fichier in _fichiers("*.py"):
        texte = fichier.read_text(encoding="utf-8")
        for i, ligne in enumerate(texte.splitlines(), start=1):
            for m in RE_PY_GETTEXT.finditer(ligne):
                msgid = _strip_py_quotes(m.group(1))
                if not msgid:
                    continue
                cle = (msgid, None)
                entree = entrees.setdefault(cle, Entree(msgid=msgid))
                entree.occurrences.append((_rel(fichier), i))


def _corps_vers_msgid(corps: str) -> str:
    return RE_VAR_REF.sub(lambda m: f"%({m.group(1)})s", corps).strip()


def extraire_gabarits(entrees: dict) -> None:
    for fichier in _fichiers("*.html"):
        texte = fichier.read_text(encoding="utf-8")

        for m in RE_TPL_TRANSLATE.finditer(texte):
            msgid = _strip_py_quotes(m.group(1))
            if not msgid:
                continue
            ligne = texte.count("\n", 0, m.start()) + 1
            cle = (msgid, None)
            entree = entrees.setdefault(cle, Entree(msgid=msgid))
            entree.occurrences.append((_rel(fichier), ligne))

        for m in RE_TPL_BLOCK.finditer(texte):
            args, corps = m.group(1), m.group(2)
            ligne = texte.count("\n", 0, m.start()) + 1
            plural_split = RE_PLURAL_TAG.split(corps)
            if len(plural_split) == 2:
                singulier = _corps_vers_msgid(plural_split[0])
                pluriel = _corps_vers_msgid(plural_split[1])
                cle = (singulier, pluriel)
                entree = entrees.setdefault(
                    cle, Entree(msgid=singulier, msgid_plural=pluriel))
            else:
                msgid = _corps_vers_msgid(corps)
                if not msgid:
                    continue
                cle = (msgid, None)
                entree = entrees.setdefault(cle, Entree(msgid=msgid))
            entree.occurrences.append((_rel(fichier), ligne))


def construire_catalogue() -> dict:
    entrees: dict = {}
    extraire_python(entrees)
    extraire_gabarits(entrees)
    return entrees


def ecrire_po(langue: str, entrees: dict) -> tuple[int, int]:
    import polib

    chemin = LOCALE_DIR / langue / "LC_MESSAGES" / "django.po"
    chemin.parent.mkdir(parents=True, exist_ok=True)

    existant = polib.pofile(str(chemin)) if chemin.exists() else None
    traductions = {}
    if existant:
        for e in existant:
            traductions[(e.msgid, e.msgid_plural or None)] = e

    po = polib.POFile()
    po.metadata = {
        "Project-Id-Version": "Kenya So",
        "Report-Msgid-Bugs-To": "",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "Language": langue,
        "Plural-Forms": _plural_forms(langue),
    }

    nouveaux = 0
    for cle, entree in sorted(entrees.items(), key=lambda kv: kv[1].occurrences[0]):
        ancien = traductions.get(cle)
        entry = polib.POEntry(
            msgid=entree.msgid,
            msgid_plural=entree.msgid_plural,
            occurrences=entree.occurrences,
        )
        if entree.msgid_plural:
            entry.msgstr_plural = (ancien.msgstr_plural if ancien
                                   else {0: "", 1: ""})
        else:
            entry.msgstr = ancien.msgstr if ancien else ""
        if ancien is None:
            nouveaux += 1
        po.append(entry)

    po.save(str(chemin))
    return len(po), nouveaux


def _plural_forms(langue: str) -> str:
    # Règles standard CLDR/gettext.
    return {
        "en": "nplurals=2; plural=(n != 1);",
        "ar": ("nplurals=6; plural=(n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : "
              "n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5);"),
        "bm": "nplurals=2; plural=(n != 1);",
        "ff": "nplurals=2; plural=(n != 1);",
        "snk": "nplurals=2; plural=(n != 1);",
    }.get(langue, "nplurals=2; plural=(n != 1);")


def main():
    entrees = construire_catalogue()
    print(f"{len(entrees)} chaîne(s) unique(s) extraite(s).\n")
    for langue in LANGUES:
        total, nouveaux = ecrire_po(langue, entrees)
        print(f"  locale/{langue}/LC_MESSAGES/django.po : {total} entrée(s)"
              f"{f', {nouveaux} nouvelle(s)' if nouveaux else ''}")


if __name__ == "__main__":
    sys.exit(main())
