"""Garde-fous d'adaptation aux appareils : ce qui doit rester vrai quand on ajoute un écran."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES = Path(settings.BASE_DIR) / "templates"


class GabaritsResponsiveTests(SimpleTestCase):
    def test_les_gabarits_racines_declarent_un_viewport_adapte(self):
        for nom in ("base.html", "base_auth.html", "core/vitrine.html"):
            html = (TEMPLATES / nom).read_text(encoding="utf-8")
            self.assertIn("width=device-width", html, nom)
            self.assertIn("initial-scale=1", html, nom)

    def test_tout_tableau_est_dans_un_conteneur_defilant(self):
        """Sans `.table-responsive`, un tableau large fait déborder toute la page sur téléphone."""
        fautifs = []
        for chemin in TEMPLATES.rglob("*.html"):
            html = chemin.read_text(encoding="utf-8")
            if len(re.findall(r"<table\b", html)) != html.count("table-responsive"):
                fautifs.append(str(chemin.relative_to(TEMPLATES)))
        self.assertEqual(fautifs, [])

    def test_aucune_largeur_fixe_en_pixels_dans_les_gabarits(self):
        fautifs = [
            str(c.relative_to(TEMPLATES)) for c in TEMPLATES.rglob("*.html")
            if re.search(r'style="[^"]*\b(min-)?width:\s*\d+px', c.read_text(encoding="utf-8"))
        ]
        self.assertEqual(fautifs, [])
