#!/usr/bin/env python
"""Utilitaire en ligne de commande de Django pour le projet Kènèya Sô."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django est introuvable. L'environnement virtuel est-il activé et "
            "les dépendances installées (pip install -r requirements.txt) ?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
