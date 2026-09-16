#!/bin/bash
# Démarrage en production (Railway) : migrations + fichiers statiques avant
# de lancer le serveur applicatif. `set -e` interrompt le déploiement si une
# étape échoue plutôt que de démarrer un serveur sur une base non à jour.
set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application --bind 0.0.0.0:"$PORT" --log-file -
